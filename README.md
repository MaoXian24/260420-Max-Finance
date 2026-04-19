# Max Finance

Max Finance is a WRDS-based financial analysis toolkit with two deliverable interfaces:

1. Web App (Streamlit)
2. Desktop App (Tkinter)

Both versions query WRDS and provide stock, financial statement, DuPont, and SIC industry analysis, with Excel export support.

## 1. Project Scope

### 1.1 Data Sources
- WRDS / CRSP daily stock data (`crsp.dsf`, `crsp.stocknames`)
- WRDS / Compustat fundamentals (`comp.funda`, `comp.company`)

### 1.2 Analysis Coverage
- Stock daily metrics (selected year)
- Financial statement trends (2015-2024)
- DuPont ratio trends (2015-2024)
- SIC industry benchmark trends (2015-2024)

## 2. Two Versions

### 2.1 Web Version (Recommended for Presentation)
- Entry file: [streamlit_app.py](streamlit_app.py)
- One-click launcher: [start_web_app.bat](start_web_app.bat)
- UI style: dashboard layout, chart-first, tables below charts
- Download behavior: browser download button

### 2.2 Desktop Version (Standalone Local GUI)
- Entry file: [max_finance_desktop.py](max_finance_desktop.py)
- UI style: scrollable sections with metric selectors and charts
- Download behavior: saves `*_Full_Data.xlsx` to the current working directory

## 3. Feature Matrix

| Feature | Web Version | Desktop Version |
|---|---|---|
| WRDS login in UI | Yes | Yes |
| Stock metric selector | Yes | Yes |
| Financial metric selector | Yes | Yes |
| DuPont metric selector | Yes | Yes |
| Industry metric selector | Yes | Yes |
| Company info table | Yes | Yes |
| Stock table preview | Yes (Top 30) | Yes (Top 10) |
| Financial/DuPont full table | Yes | Yes |
| Industry table | Yes | Yes |
| Export to Excel | Yes | Yes |

## 4. Requirements

### 4.1 Software
- Python 3.10+
- Windows (batch scripts included)

### 4.2 Account
- Valid WRDS account credentials

### 4.3 Dependencies
- See [requirements.txt](requirements.txt)

## 5. Installation

### 5.1 Fast Install
1. Open project folder.
2. Run [install_streamlit.bat](install_streamlit.bat) once.

### 5.2 Manual Install (Optional)
```bash
python -m pip install -r requirements.txt
```

## 6. How To Run

### 6.1 Run Web Version
1. Double-click [start_web_app.bat](start_web_app.bat).
2. Browser opens Streamlit page automatically.
3. Enter WRDS credentials, ticker, and year.
4. Click `Run Analysis`.

### 6.2 Run Desktop Version
Use terminal in this folder:

```bash
python max_finance_desktop.py
```

Then in the app:
1. Enter WRDS username/password.
2. Enter ticker and year (2015-2024).
3. Click `Query`.
4. Use metric dropdowns for each section.
5. Click `Download` to export Excel.

## 7. Output Files

### 7.1 Excel Export Name
- `{TICKER}_{YEAR}_Full_Data.xlsx`

### 7.2 Excel Sheets
- `Company_SIC`
- `Stock_Data`
- `Financial_DuPont`
- `Industry_Avg`

### 7.3 Save Location (Desktop Version)
- Saved to the process current working directory.
- Best practice: run desktop app from project folder so output is easy to find.

## 8. Operational Notes

1. Year selector controls stock data only.
2. Financial, DuPont, and SIC use full 2015-2024 range.
3. WRDS login errors are shown in UI.
4. Empty charts usually indicate no available rows for selected ticker/metric combination.

## 9. Project Structure

- [README.md](README.md): project documentation
- [streamlit_app.py](streamlit_app.py): web app main entry
- [max_finance_desktop.py](max_finance_desktop.py): desktop app main entry
- [start_web_app.bat](start_web_app.bat): web one-click launcher
- [install_streamlit.bat](install_streamlit.bat): dependency setup helper
- [requirements.txt](requirements.txt): Python package list

## 10. Submission Guidance

For final submission, provide this folder as a single final version of Max Finance.

Suggested demo order:
1. Run web app and show full chart workflow.
2. Run desktop app and show equivalent analysis sections.
3. Demonstrate Excel export.

---

<details>
<summary>中文说明</summary>

### 1. 项目说明
Max Finance 是一个基于 WRDS 的金融分析程序，提供两个可交付版本：
1. 网页版（Streamlit）
2. 桌面版（Tkinter）

两个版本都支持股票、财务、杜邦和行业基准分析，以及 Excel 导出。

### 2. 运行方式

#### 2.1 网页版
- 入口：[streamlit_app.py](streamlit_app.py)
- 一键启动：[start_web_app.bat](start_web_app.bat)

#### 2.2 桌面版
- 入口：[max_finance_desktop.py](max_finance_desktop.py)
- 终端运行：

```bash
python max_finance_desktop.py
```

### 3. 主要功能
- 公司信息查询
- 股票指标图（选定年份）
- 财务指标图（2015-2024）
- 杜邦指标图（2015-2024）
- SIC 行业指标图（2015-2024）
- 表格预览与 Excel 导出

### 4. 导出说明
- 文件名：`{TICKER}_{YEAR}_Full_Data.xlsx`
- 工作表：`Company_SIC`、`Stock_Data`、`Financial_DuPont`、`Industry_Avg`
- 桌面版默认保存到程序当前运行目录。

### 5. 注意事项
1. 年份选择只影响股票数据。
2. 财务、杜邦、行业模块固定使用 2015-2024。
3. 若图为空，通常是该指标在当前数据下无可用值。

</details>