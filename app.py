import streamlit as st
import requests
import pandas as pd
import io
from datetime import datetime, timedelta

st.set_page_config(page_title="沪深成交数据查询", layout="centered")
st.title("沪深交易所日成交数据")
st.caption("数据来源：上海证券交易所 & 深圳证券交易所")

SSE_HEADERS = {
    "Referer": "https://www.sse.com.cn/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}
SZSE_HEADERS = {
    "Referer": "https://www.szse.cn/market/overview/index.html",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

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

def fetch_sse(date_str, code):
    try:
        r = requests.get("https://query.sse.com.cn/commonQuery.do", params={
            "sqlId": "COMMON_SSE_SJ_GPSJ_CJGK_MRGK_C", "PRODUCT_CODE": code,
            "type": "inParams", "SEARCH_DATE": date_str
        }, headers=SSE_HEADERS, timeout=15)
        d = r.json()
        if d.get("result"):
            return float(d["result"][0]["TRADE_AMT"])
    except Exception:
        pass
    return None

@st.cache_data(ttl=3600)
def fetch_sse_stock(date_str):
    return fetch_sse(date_str, "17")

@st.cache_data(ttl=3600)
def fetch_sse_fund(date_str):
    return fetch_sse(date_str, "05")

@st.cache_data(ttl=3600)
def fetch_szse(date_str):
    try:
        r = requests.get("http://www.szse.cn/api/report/ShowReport", params={
            "SHOWTYPE": "xlsx", "CATALOGID": "1803_sczm", "TABKEY": "tab1",
            "txtQueryDate": date_str, "random": "0.39339437497296137"
        }, headers=SZSE_HEADERS, timeout=15)
        df = pd.read_excel(io.BytesIO(r.content), engine="openpyxl")
        df["证券类别"] = df["证券类别"].str.strip()
        result = {"stock": None, "fund": None}
        for _, row in df.iterrows():
            cat = str(row.iloc[0])
            raw = str(row.iloc[2]).replace(",", "")
            try:
                amt = float(raw) / 1e8
            except ValueError:
                continue
            if cat == "股票":
                result["stock"] = round(amt, 2)
            elif cat == "基金":
                result["fund"] = round(amt, 2)
        return result["stock"], result["fund"]
    except Exception:
        return None, None

today = datetime.now()
tab1, tab2 = st.tabs(["单日查询", "批量查询"])

with tab1:
    d = st.date_input("选择日期", value=today, max_value=today)
    if st.button("查询", type="primary", use_container_width=True):
        ds = d.strftime("%Y-%m-%d")
        if not is_trading_day(d):
            st.warning(f"{ds} 为非交易日（周末或法定节假日），当日无成交数据。")
        else:
            with st.spinner(f"获取 {ds} 数据..."):
                ss = fetch_sse_stock(ds)
                sf = fetch_sse_fund(ds)
                zs, zf = fetch_szse(ds)
            if ss is None and sf is None and zs is None and zf is None:
                st.warning(f"{ds} 无数据")
            else:
                rows = []
                for name, s, f in [("上交所", ss, sf), ("深交所", zs, zf)]:
                    rows.append({
                        "交易所": name,
                        "股票(亿元)": s if s is not None else "-",
"股票(万亿元)": f"{s/10000:.2f}" if s is not None else "-",
                    "基金(亿元)": f if f is not None else "-",
                    "基金(万亿元)": f"{f/10000:.2f}" if f is not None else "-",
                    })
                st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
                csv = pd.DataFrame(rows).to_csv(index=False, encoding="utf-8-sig")
                st.download_button("下载 CSV", csv, f"stock_{ds}.csv")

with tab2:
    c1, c2 = st.columns(2)
    with c1:
        sd = st.date_input("开始", value=today - timedelta(days=30), max_value=today, key="s")
    with c2:
        ed = st.date_input("结束", value=today, max_value=today, key="e")
    if st.button("批量", type="primary", use_container_width=True, key="b"):
        if sd > ed:
            st.error("开始 > 结束")
        else:
            dates = pd.bdate_range(start=sd, end=ed)
            res = []
            p = st.progress(0)
            sts = st.empty()
            for i, dt in enumerate(dates):
                ds = dt.strftime("%Y-%m-%d")
                sts.text(f"查询 {ds}...")
                s1 = fetch_sse_stock(ds)
                s2 = fetch_sse_fund(ds)
                s3, s4 = fetch_szse(ds)
                if any(x is not None for x in [s1, s2, s3, s4]):
                    res.append({"日期": ds, "上交所股票(亿元)": s1 if s1 is not None else "-",
                                "上交所基金(亿元)": s2 if s2 is not None else "-",
                                "深交所股票(亿元)": s3 if s3 is not None else "-",
                                "深交所基金(亿元)": s4 if s4 is not None else "-"})
                p.progress((i + 1) / len(dates))
            sts.empty()
            p.empty()
            if res:
                df = pd.DataFrame(res)
                st.markdown("**单位：亿元**")
                st.dataframe(df, hide_index=True, use_container_width=True)
                df2 = df.copy()
                for c in df2.columns[1:]:
                    df2[c] = df2[c].apply(lambda x: f"{float(x)/10000:.2f}" if x != "-" else "-")
                st.markdown("**单位：万亿元**")
                st.dataframe(df2, hide_index=True, use_container_width=True)
                st.download_button("下载 CSV", df.to_csv(index=False, encoding="utf-8-sig"),
                                   f"batch_{sd.strftime('%Y%m%d')}_{ed.strftime('%Y%m%d')}.csv")
            else:
                st.warning("无数据")

st.markdown("---")
st.caption("仅供参考")
