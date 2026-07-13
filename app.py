import streamlit as st
import requests
import pandas as pd
import io
from datetime import datetime, timedelta

def is_trading_day(dt):
    if dt.weekday() >= 5:
        return False
    y, m, d = dt.year, dt.month, dt.day
    holidays = {
        (2026, 1, 1), (2026, 1, 2), (2026, 1, 3),
        (2026, 1, 26), (2026, 1, 27), (2026, 1, 28), (2026, 1, 29), (2026, 1, 30),
        (2026, 2, 2), (2026, 2, 3), (2026, 2, 4), (2026, 2, 5), (2026, 2, 6),
        (2026, 4, 6), (2026, 4, 7),
        (2026, 5, 1), (2026, 5, 2), (2026, 5, 3),
        (2026, 5, 28), (2026, 5, 29),
        (2026, 10, 1), (2026, 10, 2), (2026, 10, 3), (2026, 10, 4), (2026, 10, 5),
        (2026, 10, 6), (2026, 10, 7), (2026, 10, 8), (2026, 10, 9),
    }
    return (y, m, d) not in holidays

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
SZSE_URLS = [
    "https://www.szse.cn/api/report/ShowReport",
    "http://www.szse.cn/api/report/ShowReport"
]

@st.cache_data(ttl=3600)
def fetch_sse_stock(date_str):
    try:
        params = {"sqlId": "COMMON_SSE_SJ_GPSJ_CJGK_MRGK_C", "PRODUCT_CODE": "17", "type": "inParams", "SEARCH_DATE": date_str}
        r = requests.get(SSE_URL, params=params, headers=SSE_HEADERS, timeout=15)
        data = r.json()
        if data.get("result"):
            return float(data["result"][0]["TRADE_AMT"])
    except Exception:
        pass
    return None

@st.cache_data(ttl=3600)
def fetch_sse_fund(date_str):
    try:
        params = {"sqlId": "COMMON_SSE_SJ_GPSJ_CJGK_MRGK_C", "PRODUCT_CODE": "05", "type": "inParams", "SEARCH_DATE": date_str}
        r = requests.get(SSE_URL, params=params, headers=SSE_HEADERS, timeout=15)
        data = r.json()
        if data.get("result"):
            return float(data["result"][0]["TRADE_AMT"])
    except Exception:
        pass
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
    for url in SZSE_URLS:
        try:
            r = requests.get(url, params=params, headers=SZSE_HEADERS, timeout=15)
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
        except Exception:
            continue
    return None, None

tab1, tab2 = st.tabs(["📅 单日查询", "📊 批量查询"])

with tab1:
    today = datetime.now()
    date_input = st.date_input("选择日期", value=today, max_value=today)

    if st.button("查询", type="primary", use_container_width=True):
        date_str = date_input.strftime("%Y-%m-%d")

        if not is_trading_day(date_input):
            st.warning(f"{date_str} 为非交易日（周末或法定节假日），当日无成交数据。")
        else:
            with st.spinner(f"正在获取 {date_str} 数据..."):
                sse_stock = fetch_sse_stock(date_str)
                sse_fund = fetch_sse_fund(date_str)
                sz_stock, sz_fund = fetch_szse_data(date_str)

            if sse_stock is None and sse_fund is None and sz_stock is None and sz_fund is None:
                st.warning(f"{date_str} 无数据，可能为非交易日或数据尚未发布。")
            else:
                rows = []
                for name, ss, sf in [("上交所", sse_stock, sse_fund), ("深交所", sz_stock, sz_fund)]:
                    rows.append({
                        "交易所": name,
                        "股票(亿元)": ss if ss is not None else "-",
                        "股票(万亿元)": f"{ss/10000:.4f}" if ss is not None else "-",
                        "基金(亿元)": sf if sf is not None else "-",
                        "基金(万亿元)": f"{sf/10000:.4f}" if sf is not None else "-",
                    })

                df = pd.DataFrame(rows)
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
                if sse_s is not None or sse_f is not None or sz_s is not None or sz_f is not None:
                    results.append({
                        "日期": date_str,
                        "上交所股票(亿元)": sse_s if sse_s is not None else "-",
                        "上交所基金(亿元)": sse_f if sse_f is not None else "-",
                        "深交所股票(亿元)": sz_s if sz_s is not None else "-",
                        "深交所基金(亿元)": sz_f if sz_f is not None else "-"
                    })
                progress.progress((i + 1) / len(dates))
            status.empty()
            progress.empty()

            if results:
                df_yi = pd.DataFrame([{
                    "日期": r["日期"],
                    "上交所股票(亿元)": r["上交所股票(亿元)"],
                    "上交所基金(亿元)": r["上交所基金(亿元)"],
                    "深交所股票(亿元)": r["深交所股票(亿元)"],
                    "深交所基金(亿元)": r["深交所基金(亿元)"],
                } for r in results])

                df_wan = df_yi.copy()
                for col in df_wan.columns[1:]:
                    df_wan[col] = df_wan[col].apply(lambda x: f"{float(x)/10000:.4f}" if x != "-" else "-")

                st.subheader("单位：亿元")
                st.dataframe(df_yi, hide_index=True, use_container_width=True)

                st.subheader("单位：万亿元")
                st.dataframe(df_wan, hide_index=True, use_container_width=True)

                csv = df_yi.to_csv(index=False, encoding="utf-8-sig")
                st.download_button("下载 CSV（亿元）", data=csv, file_name=f"batch_yi_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}.csv", mime="text/csv")
            else:
                st.warning("所选日期范围内无数据。")

st.markdown("---")
st.caption("数据仅供参考，不构成投资建议。交易日数据需在收盘后获取。")
