import streamlit as st
import requests
import pandas as pd
import io
from datetime import datetime, timedelta

st.set_page_config(page_title="沪深成交数据查询", page_icon="📈", layout="centered")

st.title("📈 沪深交易所日成交数据")
st.caption("数据来源：上海证券交易所 & 深圳证券交易所")

SSE_HEADERS = {
    "Referer": "https://www.sse.com.cn/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
}

SZSE_HEADERS = {
    "Referer": "https://www.szse.cn/market/overview/index.html",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
}

SSE_URL = "https://query.sse.com.cn/commonQuery.do"
SZSE_URL = "http://www.szse.cn/api/report/ShowReport"

@st.cache_data(ttl=3600)
def fetch_sse_stock(date_str):
    params = {
        "sqlId": "COMMON_SSE_SJ_GPSJ_CJGK_MRGK_C",
        "PRODUCT_CODE": "17",
        "type": "inParams",
        "SEARCH_DATE": date_str
    }
    r = requests.get(SSE_URL, params=params, headers=SSE_HEADERS, timeout=15)
    data = r.json()
    if data["result"]:
        return float(data["result"][0]["TRADE_AMT"])
    return None

@st.cache_data(ttl=3600)
def fetch_sse_fund(date_str):
    params = {
        "sqlId": "COMMON_SSE_SJ_GPSJ_CJGK_MRGK_C",
        "PRODUCT_CODE": "05",
        "type": "inParams",
        "SEARCH_DATE": date_str
    }
    r = requests.get(SSE_URL, params=params, headers=SSE_HEADERS, timeout=15)
    data = r.json()
    if data["result"]:
        return float(data["result"][0]["TRADE_AMT"])
    return None

@st.cache_data(ttl=3600)
def fetch_szse_data(date_str):
    params = {
        "SHOWTYPE": "xlsx",
        "CATALOGID": "1803_sczm",
        "TABKEY": "tab1",
        "txtQueryDate": date_str,
        "random": "0.39339437497296137"
    }
    r = requests.get(SZSE_URL, params=params, headers=SZSE_HEADERS, timeout=15)
    df = pd.read_excel(io.BytesIO(r.content), engine="openpyxl")
    df["证券类别"] = df["证券类别"].str.strip()
    df.iloc[:, 2:] = df.iloc[:, 2:].map(lambda x: str(x).replace(",", ""))
    result = {}
    for _, row in df.iterrows():
        cat = str(row.iloc[0])
        amt = float(str(row.iloc[2]).replace(",", "")) / 1e8
        if cat == "股票":
            result["stock"] = round(amt, 2)
        elif cat == "基金":
            result["fund"] = round(amt, 2)
    return result.get("stock"), result.get("fund")

tab1, tab2 = st.tabs(["📅 单日查询", "📊 批量查询"])

with tab1:
    today = datetime.now()
    default_date = today - timedelta(days=1) if today.weekday() == 0 else today
    date_input = st.date_input("选择日期", value=today, max_value=today)

    if st.button("查询", type="primary", use_container_width=True):
        date_str = date_input.strftime("%Y-%m-%d")
        with st.spinner(f"正在获取 {date_str} 数据..."):
            sse_stock = fetch_sse_stock(date_str)
            sse_fund = fetch_sse_fund(date_str)
            sz_stock, sz_fund = fetch_szse_data(date_str)

        if sse_stock is None and sse_fund is None and sz_stock is None and sz_fund is None:
            st.warning("该日无数据，可能为非交易日。")
        else:
            data = {
                "交易所": ["上交所", "深交所"],
                "股票成交额(亿元)": [sse_stock if sse_stock else "-", sz_stock if sz_stock else "-"],
                "基金成交额(亿元)": [sse_fund if sse_fund else "-", sz_fund if sz_fund else "-"]
            }
            if sse_stock and sz_stock:
                total = round(sse_stock + sz_stock, 2)
                data["股票成交额(亿元)"].append(total)
                data["基金成交额(亿元)"].append("-")
                data["交易所"].append("沪深合计")
            df = pd.DataFrame(data)
            st.dataframe(df, hide_index=True, use_container_width=True)

            csv = df.to_csv(index=False, encoding="utf-8-sig")
            st.download_button("下载 CSV", data=csv, file_name=f"stock_data_{date_str}.csv", mime="text/csv")

with tab2:
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("开始日期", value=today - timedelta(days=30), max_value=today, key="start")
    with col2:
        end_date = st.date_input("结束日期", value=today, max_value=today, key="end")

    if st.button("批量查询", type="primary", use_container_width=True, key="batch"):
        if start_date > end_date:
            st.error("开始日期不能晚于结束日期")
        else:
            dates = pd.bdate_range(start=start_date, end=end_date)
            results = []
            progress = st.progress(0)
            status = st.empty()
            for i, d in enumerate(dates):
                date_str = d.strftime("%Y-%m-%d")
                status.text(f"正在查询 {date_str}...")
                sse_s = fetch_sse_stock(date_str)
                sse_f = fetch_sse_fund(date_str)
                sz_s, sz_f = fetch_szse_data(date_str)
                if sse_s or sse_f or sz_s or sz_f:
                    results.append({
                        "日期": date_str,
                        "上交所股票(亿元)": sse_s if sse_s else "-",
                        "上交所基金(亿元)": sse_f if sse_f else "-",
                        "深交所股票(亿元)": sz_s if sz_s else "-",
                        "深交所基金(亿元)": sz_f if sz_f else "-"
                    })
                progress.progress((i + 1) / len(dates))
            status.empty()
            progress.empty()

            if results:
                df = pd.DataFrame(results)
                st.dataframe(df, hide_index=True, use_container_width=True)
                csv = df.to_csv(index=False, encoding="utf-8-sig")
                st.download_button("下载 CSV", data=csv, file_name=f"batch_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}.csv", mime="text/csv")
            else:
                st.warning("所选日期范围内无数据。")

st.markdown("---")
st.caption("数据仅供参考，不构成投资建议。交易日数据需在收盘后获取。")
