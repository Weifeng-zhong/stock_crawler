import requests
from chinese_calendar import is_workday

TENCENT_SYMBOL = {
    "sse_stock": "sh000001",
    "sse_fund": "sh000011",
    "szse_stock": "sz399106",
}


def is_trading_day(dt):
    return is_workday(dt)

SSE_HEADERS = {
    "Referer": "https://www.sse.com.cn/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}
SZSE_HEADERS = {
    "Referer": "https://www.szse.cn/market/overview/index.html",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def _fetch_tencent_daily(symbol, date_str):
    r = requests.get("https://web.ifzq.gtimg.cn/appstock/app/newfqkline/get",
                     params={"param": f"{symbol},day,{date_str},{date_str},10,qfq"},
                     headers=UA, timeout=15)
    for row in r.json()["data"][symbol]["day"]:
        if row[0] == date_str:
            return round(float(row[8]) / 10000, 2)
    return None


def fetch_sse(date_str, code):
    try:
        r = requests.get("https://query.sse.com.cn/commonQuery.do", params={
            "sqlId": "COMMON_SSE_SJ_GPSJ_CJGK_MRGK_C", "PRODUCT_CODE": code,
            "type": "inParams", "SEARCH_DATE": date_str
        }, headers=SSE_HEADERS, timeout=15)
        d = r.json()
        if d.get("result"):
            return float(d["result"][0]["TRADE_AMT"])
        print(f"SSE 官方接口无数据: {d.get('error') or d.get('success')}")
    except Exception as e:
        print(f"SSE 官方接口异常: {e}")
    return fetch_sse_fallback(date_str, code)


def fetch_sse_fallback(date_str, code):
    symbol = {"17": TENCENT_SYMBOL["sse_stock"], "05": TENCENT_SYMBOL["sse_fund"]}.get(code)
    if not symbol:
        return None
    try:
        v = _fetch_tencent_daily(symbol, date_str)
        if v is not None:
            print(f"SSE 使用腾讯兜底数据: {symbol} {date_str}")
        return v
    except Exception as e:
        print(f"SSE 腾讯兜底接口异常: {e}")
    return None


def fetch_sse_stock(date_str):
    return fetch_sse(date_str, "17")


def fetch_sse_fund(date_str):
    return fetch_sse(date_str, "05")


def fetch_szse(date_str):
    import pandas as pd
    import io
    import random
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
            if result["stock"] is None and result["fund"] is None:
                print(f"SZSE {url} 解析成功但未匹配到数据行")
            return result["stock"], result["fund"]
        except Exception as e:
            print(f"SZSE {url} 请求/解析失败: {e}")
    return fetch_szse_fallback(date_str)


def fetch_szse_fallback(date_str):
    try:
        s = _fetch_tencent_daily(TENCENT_SYMBOL["szse_stock"], date_str)
        if s is not None:
            print(f"SZSE 使用腾讯兜底数据(股票): {date_str}")
        return s, None
    except Exception as e:
        print(f"SZSE 腾讯兜底接口异常: {e}")
    return None, None
