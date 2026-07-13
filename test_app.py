import requests
import pandas as pd
import io

SSE_HEADERS = {
    "Referer": "https://www.sse.com.cn/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}
SZSE_HEADERS = {
    "Referer": "https://www.szse.cn/market/overview/index.html",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

def fetch_sse_stock(date_str):
    params = {"sqlId": "COMMON_SSE_SJ_GPSJ_CJGK_MRGK_C", "PRODUCT_CODE": "17", "type": "inParams", "SEARCH_DATE": date_str}
    r = requests.get("https://query.sse.com.cn/commonQuery.do", params=params, headers=SSE_HEADERS, timeout=15)
    data = r.json()
    if data["result"]:
        return float(data["result"][0]["TRADE_AMT"])
    return None

def fetch_sse_fund(date_str):
    params = {"sqlId": "COMMON_SSE_SJ_GPSJ_CJGK_MRGK_C", "PRODUCT_CODE": "05", "type": "inParams", "SEARCH_DATE": date_str}
    r = requests.get("https://query.sse.com.cn/commonQuery.do", params=params, headers=SSE_HEADERS, timeout=15)
    data = r.json()
    if data["result"]:
        return float(data["result"][0]["TRADE_AMT"])
    return None

def fetch_szse_data(date_str):
    params = {"SHOWTYPE": "xlsx", "CATALOGID": "1803_sczm", "TABKEY": "tab1", "txtQueryDate": date_str, "random": "0.39339437497296137"}
    r = requests.get("http://www.szse.cn/api/report/ShowReport", params=params, headers=SZSE_HEADERS, timeout=15)
    df = pd.read_excel(io.BytesIO(r.content), engine="openpyxl")
    df["证券类别"] = df["证券类别"].str.strip()
    result = {}
    for _, row in df.iterrows():
        cat = str(row.iloc[0])
        amt = float(str(row.iloc[2]).replace(",", "")) / 1e8
        if cat == "股票":
            result["stock"] = round(amt, 2)
        elif cat == "基金":
            result["fund"] = round(amt, 2)
    return result.get("stock"), result.get("fund")

print("Testing single date: 2026-07-10")
ss = fetch_sse_stock("2026-07-10")
sf = fetch_sse_fund("2026-07-10")
zs, zf = fetch_szse_data("2026-07-10")
print(f"  SSE Stock: {ss} 亿元")
print(f"  SSE Fund:  {sf} 亿元")
print(f"  SZSE Stock: {zs} 亿元")
print(f"  SZSE Fund:  {zf} 亿元")

print("\nTesting another date: 2026-07-09")
ss2 = fetch_sse_stock("2026-07-09")
sf2 = fetch_sse_fund("2026-07-09")
zs2, zf2 = fetch_szse_data("2026-07-09")
print(f"  SSE Stock: {ss2} 亿元")
print(f"  SSE Fund:  {sf2} 亿元")
print(f"  SZSE Stock: {zs2} 亿元")
print(f"  SZSE Fund:  {zf2} 亿元")

print("\nTesting non-trading day: 2026-07-12 (Sunday)")
ss3 = fetch_sse_stock("2026-07-12")
sf3 = fetch_sse_fund("2026-07-12")
zs3, zf3 = fetch_szse_data("2026-07-12")
print(f"  SSE Stock: {ss3}")
print(f"  SSE Fund:  {sf3}")
print(f"  SZSE Stock: {zs3}")
print(f"  SZSE Fund:  {zf3}")

print("\nAll tests passed!")
