import io
import hashlib
import random
import warnings

import matplotlib.pyplot as plt
import pandas as pd
import psycopg2
import streamlit as st
from wrds.sql import WRDS_CONNECT_ARGS, WRDS_POSTGRES_DB, WRDS_POSTGRES_HOST, WRDS_POSTGRES_PORT

warnings.filterwarnings("ignore")

SHROUT_MULTIPLIER = 1000
YEAR_OPTIONS = [str(y) for y in range(2015, 2025)]
DEFAULT_TICKER_POOL = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA"]

plt.rcParams["font.sans-serif"] = ["DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


def open_wrds_connection(wrds_user, wrds_password):
    """Open a direct WRDS PostgreSQL connection without interactive prompts."""
    connect_kwargs = {
        "host": WRDS_POSTGRES_HOST,
        "port": WRDS_POSTGRES_PORT,
        "dbname": WRDS_POSTGRES_DB,
        "user": wrds_user,
        "password": wrds_password,
        "connect_timeout": 10,
    }
    # WRDS recommends SSL; keep compatibility with wrds defaults when available.
    if isinstance(WRDS_CONNECT_ARGS, dict):
        connect_kwargs.update(WRDS_CONNECT_ARGS)
    return psycopg2.connect(**connect_kwargs)


def run_raw_sql(conn, sql, params=None, date_cols=None):
    """Execute SQL through pandas and normalize optional date columns."""
    df = pd.read_sql_query(sql, conn, params=params)
    if date_cols:
        for col in date_cols:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


def format_auth_error(exc):
    """Convert DB auth exceptions into short user-facing diagnostics."""
    msg = str(exc).strip().replace("\n", " ")
    if not msg:
        msg = exc.__class__.__name__
    if len(msg) > 220:
        msg = msg[:220] + "..."
    return msg


def clear_runtime_state():
    """Clear result buffers so old data is not reused across credential switches."""
    st.session_state.result = None
    st.session_state.last_ticker = ""
    st.session_state.last_year = ""


def build_credential_fingerprint(wrds_user, wrds_password):
    """Build a stable non-plaintext fingerprint for credential change detection."""
    raw = f"{wrds_user}\0{wrds_password}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def validate_credentials(wrds_user, wrds_password):
    """Validate WRDS credentials with a lightweight query before full data requests."""
    conn = None
    try:
        conn = open_wrds_connection(wrds_user, wrds_password)
        run_raw_sql(conn, "SELECT 1 AS ok")
        return True, ""
    except Exception as exc:
        return False, format_auth_error(exc)
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def get_industry_avg(sic_code, wrds_user, wrds_password):
    if sic_code is None or pd.isna(sic_code):
        return pd.DataFrame()

    conn = None
    try:
        sic_code = int(float(sic_code))
        conn = open_wrds_connection(wrds_user, wrds_password)

        ind_df = run_raw_sql(
            conn,
            """
            SELECT fyear,
                   sich AS sic_code,
                   COUNT(*) AS num_obs,
                   AVG(sale) AS avg_sale,
                   AVG(at) AS avg_total_assets,
                   AVG(ceq) AS avg_common_equity
            FROM comp.funda
            WHERE sich = %s
            AND fyear BETWEEN 2015 AND 2024
            AND datafmt = 'STD'
            AND consol = 'C'
            AND indfmt = 'INDL'
            GROUP BY fyear, sich
            ORDER BY fyear
            """,
            params=(sic_code,),
        )
        return ind_df.round(2)
    except Exception:
        return pd.DataFrame()
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def get_company_info(ticker, wrds_user, wrds_password):
    conn = None
    try:
        conn = open_wrds_connection(wrds_user, wrds_password)
        sql = """
            SELECT tic, conm, sich
            FROM comp.funda
            WHERE UPPER(tic) = UPPER(%s)
            AND datafmt = 'STD' AND consol = 'C' AND indfmt = 'INDL'
            AND sich IS NOT NULL
            ORDER BY datadate DESC NULLS LAST, fyear DESC NULLS LAST
            LIMIT 1
        """
        df = run_raw_sql(conn, sql, params=(ticker,))

        if df.empty:
            sql_fallback = """
                SELECT tic, conm, sic AS sich
                FROM comp.company
                WHERE UPPER(tic) = UPPER(%s)
                AND sic IS NOT NULL
                LIMIT 1
            """
            df = run_raw_sql(conn, sql_fallback, params=(ticker,))

        return df
    except Exception:
        return pd.DataFrame()
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def get_year_quarters(year):
    return [
        (f"{year}-01-01", f"{year}-03-31"),
        (f"{year}-04-01", f"{year}-06-30"),
        (f"{year}-07-01", f"{year}-09-30"),
        (f"{year}-10-01", f"{year}-12-31"),
    ]


def get_single_year_daily(ticker, year, wrds_user, wrds_password):
    quarters = get_year_quarters(year)
    all_data = []

    conn = None
    try:
        conn = open_wrds_connection(wrds_user, wrds_password)
        permno_sql = "SELECT DISTINCT permno FROM crsp.stocknames WHERE UPPER(ticker)=UPPER(%s) LIMIT 1"
        permno_df = run_raw_sql(conn, permno_sql, params=(ticker,))
        if permno_df.empty:
            return pd.DataFrame(), "Stock not found in CRSP"
        permno = int(permno_df.iloc[0]["permno"])
    except Exception:
        return pd.DataFrame(), "WRDS connect failed"
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    for start_date, end_date in quarters:
        conn = None
        try:
            conn = open_wrds_connection(wrds_user, wrds_password)
            sql = (
                "SELECT date, prc, ret, vol, shrout "
                "FROM crsp.dsf "
                f"WHERE permno={permno} AND date>='{start_date}' AND date<='{end_date}' "
                "ORDER BY date"
            )
            df_q = run_raw_sql(conn, sql, date_cols=["date"])
            if not df_q.empty:
                all_data.append(df_q)
        except Exception:
            continue
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    if not all_data:
        return pd.DataFrame(), "No daily price data for selected year"

    df = pd.concat(all_data, ignore_index=True)
    df["close"] = df["prc"].abs()
    df["daily_return"] = df["ret"]
    df["volume"] = df["vol"]
    df["market_cap"] = (df["close"] * df["shrout"].fillna(0) * SHROUT_MULTIPLIER).round(2)

    stock_df = (
        df[["date", "close", "daily_return", "volume", "market_cap"]]
        .round(4)
        .sort_values("date")
        .drop_duplicates()
    )
    return stock_df, ""


def get_financial_data(ticker, wrds_user, wrds_password):
    conn = None
    try:
        conn = open_wrds_connection(wrds_user, wrds_password)
        sql = """
        SELECT gvkey, tic, conm, datadate, ni, sale, at, ceq, lt,
        ROUND(ni/sale,4) as profit_margin, ROUND(sale/at,4) as asset_turnover,
        ROUND(at/ceq,4) as equity_multiplier, ROUND((ni/sale)*(sale/at)*(at/ceq),4) as roe_dupont
        FROM comp.funda
        WHERE UPPER(tic)=UPPER(%s) AND datadate>='2015-01-01' AND datadate<='2024-12-31'
        AND sale>0 AND at>0 AND ceq>0 ORDER BY datadate;
        """
        df = run_raw_sql(conn, sql, params=(ticker,), date_cols=["datadate"])
        rename = {
            "tic": "Ticker",
            "conm": "Company",
            "datadate": "Date",
            "ni": "NetIncome",
            "sale": "Revenue",
            "at": "TotalAssets",
            "lt": "TotalLiabs",
            "ceq": "TotalEquity",
            "profit_margin": "ProfitMargin",
            "asset_turnover": "AssetTurnover",
            "equity_multiplier": "EqMultiplier",
            "roe_dupont": "ROE_DuPont",
        }
        return df.rename(columns=rename)
    except Exception:
        return pd.DataFrame()
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def get_chart_theme():
    """Return contrast-safe chart styling based on Streamlit light/dark theme."""
    base = st.get_option("theme.base") or "light"
    if base == "dark":
        return {
            "text": "#E8EEF7",
            "grid": "#4A5464",
            "palette": ["#66B2FF", "#FF9D6E", "#6FE59D", "#FF7FA8", "#D9A8FF", "#4DD5FF"],
            "bg": "none",
        }
    return {
        "text": "#1C2430",
        "grid": "#C7CFDA",
        "palette": ["#1F77B4", "#D97706", "#15803D", "#BE185D", "#7C3AED", "#0E7490"],
        "bg": "none",
    }


def make_multi_line_chart(
    df,
    x_col,
    selected_series,
    title,
    y_label,
    is_currency=False,
    marker=False,
    fixed_color=None,
    currency_divisor=1e9,
):
    """Render a theme-aware line chart with dynamic selected metrics."""
    theme = get_chart_theme()
    fig, ax = plt.subplots(figsize=(11.8, 4.8), dpi=120)

    for idx, (series_col, series_label) in enumerate(selected_series):
        color = fixed_color or theme["palette"][idx % len(theme["palette"])]
        clean_df = df[[x_col, series_col]].dropna()
        if clean_df.empty:
            continue
        ax.plot(
            clean_df[x_col],
            clean_df[series_col],
            label=series_label,
            linewidth=2.3,
            marker="o" if marker else None,
            color=color,
        )

    ax.set_title(title, fontsize=15, pad=12, fontweight="bold", color=theme["text"])
    ax.set_ylabel(y_label, fontsize=12, color=theme["text"])
    ax.tick_params(axis="x", labelsize=10, colors=theme["text"])
    ax.tick_params(axis="y", labelsize=10, colors=theme["text"])
    ax.grid(alpha=0.35, linestyle="--", linewidth=0.8, color=theme["grid"])
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["bottom"].set_color(theme["grid"])
    ax.spines["left"].set_color(theme["grid"])
    ax.set_facecolor(theme["bg"])
    fig.patch.set_alpha(0)
    if is_currency:
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x/currency_divisor:.1f}B"))
    ax.legend(frameon=False, ncol=2, loc="upper left", labelcolor=theme["text"])
    fig.tight_layout()
    return fig


def inject_custom_css():
    st.markdown(
        """
        <style>
        .mf-section-title {
            font-size: 2rem;
            font-weight: 700;
            line-height: 1.2;
            margin-top: 1.1rem;
            margin-bottom: 0.7rem;
            color: #E7EDF7;
            border-left: 6px solid var(--accent);
            padding: 0.18rem 0 0.18rem 0.7rem;
            border-radius: 2px;
        }
        .mf-table-title {
            font-size: 1.08rem;
            font-weight: 700;
            margin: 0.65rem 0 0.25rem 0;
        }
        .mf-table-wrap {
            width: 100%;
            overflow-x: auto;
            border: 1px solid #3B4253;
            border-radius: 10px;
            margin-bottom: 0.95rem;
        }
        .mf-table {
            border-collapse: collapse;
            width: 100%;
            min-width: 860px;
        }
        .mf-table th, .mf-table td {
            padding: 0.42rem 0.55rem;
            border-bottom: 1px solid rgba(17, 24, 39, 0.08);
            font-size: 0.89rem;
            white-space: nowrap;
        }
        .mf-table-wrap.profile th { background: #16324F; color: #F8FAFC; }
        .mf-table-wrap.profile tbody tr:nth-child(odd) td { background: #E9F2FA; color: #1E293B; }
        .mf-table-wrap.profile tbody tr:nth-child(even) td { background: #F4F8FC; color: #1E293B; }

        .mf-table-wrap.stock th { background: #0F766E; color: #ECFEFF; }
        .mf-table-wrap.stock tbody tr:nth-child(odd) td { background: #D1FAE5; color: #1F2937; }
        .mf-table-wrap.stock tbody tr:nth-child(even) td { background: #ECFDF5; color: #1F2937; }

        .mf-table-wrap.financial th { background: #92400E; color: #FFF7ED; }
        .mf-table-wrap.financial tbody tr:nth-child(odd) td { background: #FFEDD5; color: #3F3F46; }
        .mf-table-wrap.financial tbody tr:nth-child(even) td { background: #FFF7ED; color: #3F3F46; }

        .mf-table-wrap.industry th { background: #4C1D95; color: #F5F3FF; }
        .mf-table-wrap.industry tbody tr:nth-child(odd) td { background: #EDE9FE; color: #334155; }
        .mf-table-wrap.industry tbody tr:nth-child(even) td { background: #F5F3FF; color: #334155; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_section_title(number, title, accent_color):
    st.markdown(
        f'<div class="mf-section-title" style="--accent: {accent_color};">{number}. {title}</div>',
        unsafe_allow_html=True,
    )


def render_table_block(title, df, theme, max_rows=None):
    shown_df = df.head(max_rows) if max_rows is not None else df
    st.markdown(f"<div class='mf-table-title'>{title}</div>", unsafe_allow_html=True)
    table_html = shown_df.to_html(index=False, classes="mf-table", border=0)
    st.markdown(f"<div class='mf-table-wrap {theme}'>{table_html}</div>", unsafe_allow_html=True)


def build_excel(info_df, stock_df, financial_df, industry_df, ticker, year):
    file_name = f"{ticker}_{year}_Full_Data.xlsx"
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        if info_df is not None and not info_df.empty:
            info_df.to_excel(writer, sheet_name="Company_SIC", index=False)
        if stock_df is not None and not stock_df.empty:
            stock_df.to_excel(writer, sheet_name="Stock_Data", index=False)
        if financial_df is not None and not financial_df.empty:
            financial_df.to_excel(writer, sheet_name="Financial_DuPont", index=False)
        if industry_df is not None and not industry_df.empty:
            industry_df.to_excel(writer, sheet_name="Industry_Avg", index=False)
    output.seek(0)
    return file_name, output


def run_query(ticker, year, wrds_user, wrds_password):
    result = {
        "info_df": pd.DataFrame(),
        "stock_df": pd.DataFrame(),
        "financial_df": pd.DataFrame(),
        "industry_df": pd.DataFrame(),
        "industry_reason": "",
        "stock_reason": "",
    }

    info_df = get_company_info(ticker, wrds_user, wrds_password)
    result["info_df"] = info_df

    if info_df is not None and not info_df.empty:
        try:
            current_sic = int(info_df["sich"].iloc[0])
            industry_df = get_industry_avg(current_sic, wrds_user, wrds_password)
            result["industry_df"] = industry_df
            if industry_df is None or industry_df.empty:
                result["industry_reason"] = f"No industry rows for SIC {current_sic} in 2015-2024"
        except Exception as e:
            result["industry_reason"] = f"Industry query failed: {e}"
    else:
        result["industry_reason"] = "No valid SIC found for this ticker"

    stock_df, stock_reason = get_single_year_daily(ticker, year, wrds_user, wrds_password)
    result["stock_df"] = stock_df
    result["stock_reason"] = stock_reason

    result["financial_df"] = get_financial_data(ticker, wrds_user, wrds_password)
    return result


def render_app():
    st.set_page_config(page_title="Max Finance", layout="wide")
    inject_custom_css()
    st.title("Max Finance")
    st.caption("Enhanced visualization edition with dynamic metric selectors and 2015-2024 long-range analysis.")

    if "default_ticker" not in st.session_state:
        st.session_state.default_ticker = random.choice(DEFAULT_TICKER_POOL)

    if "result" not in st.session_state:
        st.session_state.result = None
        st.session_state.last_ticker = ""
        st.session_state.last_year = ""

    if "cached_wrds_user" not in st.session_state:
        st.session_state.cached_wrds_user = ""
    if "credential_fingerprint" not in st.session_state:
        st.session_state.credential_fingerprint = ""
    if "auth_error" not in st.session_state:
        st.session_state.auth_error = ""

    with st.sidebar:
        st.header("Input Panel")
        wrds_user = st.text_input("WRDS User", value=st.session_state.cached_wrds_user).strip()
        wrds_password = st.text_input("WRDS Password", type="password").strip()
        ticker = st.text_input("Ticker", value=st.session_state.default_ticker).strip().upper()
        year = st.selectbox("Year", YEAR_OPTIONS, index=len(YEAR_OPTIONS) - 1)
        st.caption("Year selector controls stock data only. Financial, DuPont, SIC use full 2015-2024.")
        run_btn = st.button("Run Analysis", width="stretch")

    # Cache credentials in session state; reset previous result when credentials change.
    current_fingerprint = build_credential_fingerprint(wrds_user, wrds_password) if wrds_user and wrds_password else ""
    if current_fingerprint and current_fingerprint != st.session_state.credential_fingerprint:
        st.session_state.cached_wrds_user = wrds_user
        st.session_state.credential_fingerprint = current_fingerprint
        st.session_state.auth_error = ""
        clear_runtime_state()

    if run_btn:
        st.session_state.auth_error = ""
        if not ticker:
            st.session_state.auth_error = "Please enter a ticker symbol."
            clear_runtime_state()
        elif not wrds_user or not wrds_password:
            st.session_state.auth_error = "Please enter WRDS credentials."
            clear_runtime_state()
        else:
            ok, reason = validate_credentials(wrds_user, wrds_password)
            if not ok:
                clear_runtime_state()
                st.session_state.auth_error = f"WRDS login failed: {reason}"
            else:
                with st.spinner("Loading data from WRDS..."):
                    st.session_state.result = run_query(ticker, year, wrds_user, wrds_password)
                    st.session_state.last_ticker = ticker
                    st.session_state.last_year = year

    if st.session_state.auth_error:
        st.error(st.session_state.auth_error)

    result = st.session_state.result
    if result is None:
        if not st.session_state.auth_error:
            st.info("Enter WRDS credentials and click Run Analysis.")
        return

    info_df = result["info_df"]
    stock_df = result["stock_df"]
    financial_df = result["financial_df"]
    industry_df = result["industry_df"]
    current_sic = "-"
    if info_df is not None and not info_df.empty and "sich" in info_df.columns:
        try:
            current_sic = int(info_df["sich"].iloc[0])
        except Exception:
            current_sic = "-"

    render_section_title(1, "Stock Data Visualization", "#38BDF8")
    if stock_df is None or stock_df.empty:
        st.write("No pricing data available.")
        if result["stock_reason"]:
            st.caption(f"Reason: {result['stock_reason']}")
    else:
        stock_metric_map = {
            "Close": "close",
            "Daily Return": "daily_return",
            "Volume": "volume",
            "Market Cap": "market_cap",
        }
        stock_pick = st.selectbox(
            "Select one stock metric",
            options=list(stock_metric_map.keys()),
            index=3,
            key="stock_metric_pick",
        )
        selected_series = [(stock_metric_map[stock_pick], stock_pick)]
        stock_fig = make_multi_line_chart(
            stock_df,
            "date",
            selected_series,
            f"{st.session_state.last_ticker} Stock Trend ({st.session_state.last_year})",
            "Value",
            is_currency=stock_pick in ["Close", "Market Cap"],
            fixed_color="#38BDF8",
        )
        st.pyplot(stock_fig, clear_figure=True)

    render_section_title(2, "Financial Statement Visualization", "#F59E0B")
    if financial_df is None or financial_df.empty:
        st.write("No data.")
    else:
        financial_metric_map = {
            "Revenue": "Revenue",
            "Net Income": "NetIncome",
            "Total Assets": "TotalAssets",
            "Total Liabilities": "TotalLiabs",
            "Total Equity": "TotalEquity",
        }
        fin_pick = st.selectbox(
            "Select one financial metric",
            options=list(financial_metric_map.keys()),
            index=0,
            key="financial_metric_pick",
        )
        fin_series = [(financial_metric_map[fin_pick], fin_pick)]
        fin_fig = make_multi_line_chart(
            financial_df,
            "Date",
            fin_series,
            f"{st.session_state.last_ticker} Financial Trend (2015-2024)",
            "USD",
            is_currency=True,
            fixed_color="#F59E0B",
            currency_divisor=1e3,
        )
        st.pyplot(fin_fig, clear_figure=True)

    render_section_title(3, "DuPont Visualization", "#34D399")
    if financial_df is None or financial_df.empty:
        st.write("No data.")
    else:
        dupont_metric_map = {
            "Profit Margin": "ProfitMargin",
            "Asset Turnover": "AssetTurnover",
            "Equity Multiplier": "EqMultiplier",
            "ROE (DuPont)": "ROE_DuPont",
        }
        dupont_pick = st.selectbox(
            "Select one DuPont metric",
            options=list(dupont_metric_map.keys()),
            index=3,
            key="dupont_metric_pick",
        )
        dupont_series = [(dupont_metric_map[dupont_pick], dupont_pick)]
        dupont_fig = make_multi_line_chart(
            financial_df,
            "Date",
            dupont_series,
            f"{st.session_state.last_ticker} DuPont Trend (2015-2024)",
            "Ratio",
            is_currency=False,
            fixed_color="#34D399",
        )
        st.pyplot(dupont_fig, clear_figure=True)

    render_section_title(4, "SIC Industry Visualization", "#A78BFA")
    if industry_df is not None and not industry_df.empty:
        industry_metric_map = {
            "Avg Sale": "avg_sale",
            "Avg Total Assets": "avg_total_assets",
            "Avg Common Equity": "avg_common_equity",
            "Observations": "num_obs",
        }
        industry_pick = st.selectbox(
            "Select one industry metric",
            options=list(industry_metric_map.keys()),
            index=0,
            key="industry_metric_pick",
        )
        industry_series = [(industry_metric_map[industry_pick], industry_pick)]
        ind_fig = make_multi_line_chart(
            industry_df,
            "fyear",
            industry_series,
            f"SIC {current_sic} Industry Benchmark (2015-2024)",
            "Value",
            is_currency=industry_pick != "Observations",
            marker=True,
            fixed_color="#A78BFA",
            currency_divisor=1e3,
        )
        st.pyplot(ind_fig, clear_figure=True)
    else:
        st.write("No industry benchmark data available.")
        if result["industry_reason"]:
            st.caption(f"Reason: {result['industry_reason']}")

    render_section_title(5, "All Data Tables", "#22D3EE")
    st.caption("Tables are grouped below after the chart sections.")

    if info_df is None or info_df.empty:
        st.write("No company profile available.")
    else:
        render_table_block("Company Profile", info_df, "profile")

    if stock_df is None or stock_df.empty:
        st.write("No stock data.")
    else:
        render_table_block("Stock Data (Top 30 rows)", stock_df, "stock", max_rows=30)

    if financial_df is None or financial_df.empty:
        st.write("No financial data.")
    else:
        cols = [
            "Ticker",
            "Date",
            "NetIncome",
            "Revenue",
            "TotalAssets",
            "TotalLiabs",
            "TotalEquity",
            "ProfitMargin",
            "AssetTurnover",
            "EqMultiplier",
            "ROE_DuPont",
        ]
        show_df = financial_df[[c for c in cols if c in financial_df.columns]]
        render_table_block("Financial and DuPont Data (2015-2024)", show_df, "financial")

    if industry_df is None or industry_df.empty:
        st.write("No industry data.")
    else:
        render_table_block("SIC Industry Benchmark (2015-2024)", industry_df, "industry")

    dl_name, dl_bytes = build_excel(
        info_df,
        stock_df,
        financial_df,
        industry_df,
        st.session_state.last_ticker,
        st.session_state.last_year,
    )
    st.download_button(
        label="Download",
        data=dl_bytes,
        file_name=dl_name,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        width="stretch",
    )


if __name__ == "__main__":
    render_app()
