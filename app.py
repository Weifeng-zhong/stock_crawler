import streamlit as st
import requests
import pandas as pd
import io
import random
import json
import concurrent.futures
from datetime import datetime, timedelta, date
from chinese_calendar import is_workday as _is_workday

st.set_page_config(page_title="沪深成交数据查询", layout="centered")
st.title("沪深交易所日成交数据")
st.caption("数据来源：上海证券交易所 & 深圳证券交易所")

GH_REPO = "Weifeng-zhong/stock_crawler"
GH_API = f"https://api.github.com/repos/{GH_REPO}/contents/config.json"

SSE_HEADERS = {
    "Referer": "https://www.sse.com.cn/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}
SZSE_HEADERS = {
    "Referer": "https://www.szse.cn/market/overview/index.html",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

def is_trading_day(dt):
    return _is_workday(dt)

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

@st.cache_data(ttl=1800)
def fetch_szse(date_str):
    params = {
        "SHOWTYPE": "xlsx", "CATALOGID": "1803_sczm", "TABKEY": "tab1",
        "txtQueryDate": date_str, "random": str(random.random())
    }
    for url in ["https://www.szse.cn/api/report/ShowReport", "http://www.szse.cn/api/report/ShowReport"]:
        try:
            r = requests.get(url, params=params, headers=SZSE_HEADERS, timeout=15)
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
            continue
    return None, None

def fetch_all(date_str):
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
        sf = ex.submit(fetch_sse_stock, date_str)
        ff = ex.submit(fetch_sse_fund, date_str)
        zf = ex.submit(fetch_szse, date_str)
        sz_stock, sz_fund = zf.result()
        return sf.result(), ff.result(), sz_stock, sz_fund

def read_config(token):
    r = requests.get(GH_API, headers={"Authorization": f"Bearer {token}"})
    if r.status_code == 404:
        return {}
    import base64
    decoded = base64.b64decode(r.json()["content"]).decode()
    return json.loads(decoded)

def write_config(token, config, sha=None):
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"message": "Update push config", "content": base64_encode(json.dumps(config, ensure_ascii=False, indent=2))}
    if sha:
        payload["sha"] = sha
    r = requests.put(GH_API, json=payload, headers=headers)
    return r.ok

def base64_encode(s):
    import base64
    return base64.b64encode(s.encode()).decode()

WORKFLOW_API = f"https://api.github.com/repos/{GH_REPO}/actions/workflows/send_daily.yml/dispatches"

def trigger_verify_workflow(email, token):
    r = requests.post(WORKFLOW_API, json={"ref": "master", "inputs": {"verify_email": email}},
                      headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.v3+json"})
    return r.status_code == 204

today = datetime.now()
tabs = st.tabs(["单日查询", "批量查询", "推送设置"])

with tabs[0]:
    d = st.date_input("选择日期", value=today, max_value=today)
    if st.button("查询", type="primary", use_container_width=True):
        ds = d.strftime("%Y-%m-%d")
        if not is_trading_day(d):
            st.warning(f"{ds} 为非交易日（周末或法定节假日），当日无成交数据。")
        else:
            with st.spinner(f"获取 {ds} 数据..."):
                ss, sf, zs, zf = fetch_all(ds)
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
                st.dataframe(pd.DataFrame(rows), hide_index=True, width='stretch')
                csv = pd.DataFrame(rows).to_csv(index=False, encoding="utf-8-sig")
                st.download_button("下载 CSV", csv, f"stock_{ds}.csv")

with tabs[1]:
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
            with st.spinner(f"正在并行获取 {len(dates)} 个交易日数据..."):
                with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
                    fut = {ex.submit(fetch_all, dt.strftime("%Y-%m-%d")): dt for dt in dates}
                    p = st.progress(0)
                    done = 0
                    for f in concurrent.futures.as_completed(fut):
                        dt = fut[f]
                        ds = dt.strftime("%Y-%m-%d")
                        ss, sf, zs, zf = f.result()
                        if any(x is not None for x in [ss, sf, zs, zf]):
                            res.append({"日期": ds, "上交所股票(亿元)": ss if ss is not None else "-",
                                        "上交所基金(亿元)": sf if sf is not None else "-",
                                        "深交所股票(亿元)": zs if zs is not None else "-",
                                        "深交所基金(亿元)": zf if zf is not None else "-"})
                        done += 1
                        p.progress(done / len(dates))
                    p.empty()
            res.sort(key=lambda x: x["日期"])
            if res:
                df = pd.DataFrame(res)
                st.markdown("**单位：亿元**")
                st.dataframe(df, hide_index=True, width='stretch')
                df2 = df.copy()
                for c in df2.columns[1:]:
                    df2[c] = df2[c].apply(lambda x: f"{float(x)/10000:.2f}" if x != "-" else "-")
                st.markdown("**单位：万亿元**")
                st.dataframe(df2, hide_index=True, width='stretch')
                st.download_button("下载 CSV", df.to_csv(index=False, encoding="utf-8-sig"),
                                   f"batch_{sd.strftime('%Y%m%d')}_{ed.strftime('%Y%m%d')}.csv")
            else:
                st.warning("无数据")

with tabs[2]:
    if "add_result" not in st.session_state:
        st.session_state.add_result = None

    token = st.secrets.get("GITHUB_TOKEN", "")
    if not token:
        st.warning("未检测到 GITHUB_TOKEN，请在 Streamlit Cloud 的 Secrets 中添加。")
    else:
        config = read_config(token)
        saved_emails = config.get("receiver_emails", [])
        if not saved_emails and config.get("receiver_email"):
            saved_emails = [config["receiver_email"]]

        def save_emails(emails, token, cfg):
            cfg["receiver_emails"] = emails
            sha = None
            try:
                r = requests.get(GH_API, headers={"Authorization": f"Bearer {token}"})
                if r.status_code == 200:
                    sha = r.json()["sha"]
            except:
                pass
            write_config(token, cfg, sha)

        st.markdown("### 邮件推送设置")
        st.caption("每天早上 9:00 (北京时间) 自动推送前一交易日数据到所有已订阅邮箱。添加邮箱后通过 GitHub Actions 发送验证邮件（1-2 分钟到账）。")

        st.markdown("**已订阅邮箱：**")
        if saved_emails:
            for i, em in enumerate(saved_emails):
                c1, c2 = st.columns([5, 1])
                c1.text(em)
                if c2.button("退订", key=f"del_{i}"):
                    saved_emails.pop(i)
                    save_emails(saved_emails, token, config)
                    st.rerun()
        else:
            st.info("暂无订阅")

        new_email = st.text_input("添加邮箱", placeholder="new@email.com", key="new_email")
        if st.button("添加", type="primary"):
            if not new_email:
                st.error("请输入邮箱")
            elif new_email in saved_emails:
                st.warning("该邮箱已订阅")
            else:
                saved_emails.append(new_email)
                save_emails(saved_emails, token, config)

                ok = trigger_verify_workflow(new_email, token)
                if ok:
                    st.session_state.add_result = f"已添加 {new_email}，验证邮件列队发送中（预计 1-2 分钟到账）"
                else:
                    st.session_state.add_result = f"已添加 {new_email}（验证邮件触发失败，明早 9:00 将自动推送）"
                st.rerun()

        if st.session_state.add_result:
            st.success(st.session_state.add_result)
            st.session_state.add_result = None

        st.markdown("**邮件格式示例：**")
        st.code("前一交易日成交数据（单位：万亿元）\n\n日期 | 上交所股票 | 上交所基金 | 深交所股票 | 深交所基金\n--- | --- | --- | --- | ---\n2026-07-10 | 1.56 | 0.36 | 1.83 | 0.18\n\n如需退订，请访问：https://stockcrawler-qe3y5qgjgyceaazkpajrzd.streamlit.app/\n(数据来源：上交所、深交所官网)")

st.markdown("---")
st.caption("仅供参考")
