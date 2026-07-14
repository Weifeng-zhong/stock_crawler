import smtplib
import requests
import os
import sys
import random
import json
import argparse
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone, timedelta

BJ_TZ = timezone(timedelta(hours=8))

SSE_HEADERS = {
    "Referer": "https://www.sse.com.cn/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}
SZSE_HEADERS = {
    "Referer": "https://www.szse.cn/market/overview/index.html",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

HOLIDAYS = {
    (2026, 1, 1), (2026, 1, 2), (2026, 1, 3),
    (2026, 1, 26), (2026, 1, 27), (2026, 1, 28), (2026, 1, 29), (2026, 1, 30),
    (2026, 2, 2), (2026, 2, 3), (2026, 2, 4), (2026, 2, 5), (2026, 2, 6),
    (2026, 4, 6), (2026, 4, 7),
    (2026, 5, 1), (2026, 5, 2), (2026, 5, 3),
    (2026, 5, 28), (2026, 5, 29),
    (2026, 10, 1), (2026, 10, 2), (2026, 10, 3), (2026, 10, 4), (2026, 10, 5),
    (2026, 10, 6), (2026, 10, 7), (2026, 10, 8), (2026, 10, 9),
}

def is_trading_day(dt):
    if dt.weekday() >= 5:
        return False
    return (dt.year, dt.month, dt.day) not in HOLIDAYS

def prev_trading_day(dt):
    d = dt - timedelta(days=1)
    while not is_trading_day(d):
        d -= timedelta(days=1)
    return d

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

def fetch_sse_stock(date_str):
    return fetch_sse(date_str, "17")

def fetch_sse_fund(date_str):
    return fetch_sse(date_str, "05")

def fetch_szse(date_str):
    import pandas as pd
    import io
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

def send_email(subject, body, mail_to):
    mail_user = os.environ["MAIL_USER"]
    mail_pass = os.environ["MAIL_PASS"]
    msg = MIMEMultipart()
    msg["From"] = mail_user
    msg["To"] = mail_to
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))
    with smtplib.SMTP_SSL("smtp.163.com", 465, timeout=30) as s:
        s.login(mail_user, mail_pass)
        s.send_message(msg)

def fetch_send(date_str, mail_to_list):
    print(f"获取 {date_str} 数据...")
    ss = fetch_sse_stock(date_str)
    sf = fetch_sse_fund(date_str)
    zs, zf = fetch_szse(date_str)

    if ss is None and sf is None and zs is None and zf is None:
        print(f"{date_str} 无可用数据")
        return False

    def v(x):
        return f"{x/10000:.2f}" if x is not None else "-"

    line = f"{date_str} | {v(ss)} | {v(sf)} | {v(zs)} | {v(zf)}"
    print(line)

    subject = f"沪深成交数据 {date_str}"
    body = f"前一交易日成交数据（单位：万亿元）\n\n日期 | 上交所股票 | 上交所基金 | 深交所股票 | 深交所基金\n--- | --- | --- | --- | ---\n{line}\n\n如需退订，请访问：https://stockcrawler-qe3y5qgjgyceaazkpajrzd.streamlit.app/\n(数据来源：上交所、深交所官网)"
    for mail_to in mail_to_list:
        send_email(subject, body, mail_to)
        print(f"邮件已发送至 {mail_to}")
    return True

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-email", help="发送验证邮件到指定邮箱")
    args = parser.parse_args()

    if args.verify_email:
        now = datetime.now(BJ_TZ)
        latest = prev_trading_day(now)
        date_str = latest.strftime("%Y-%m-%d")
        ok = fetch_send(date_str, [args.verify_email])
        sys.exit(0 if ok else 1)

    config = {"receiver_email": ""}
    try:
        with open("config.json") as f:
            config.update(json.load(f))
    except Exception:
        pass

    mail_to_list = config.get("receiver_emails", [])
    if not mail_to_list and config.get("receiver_email"):
        mail_to_list = [config["receiver_email"]]
    if not mail_to_list:
        print("未设置接收邮箱，跳过")
        return

    now = datetime.now(BJ_TZ)
    yesterday = now - timedelta(days=1)
    if not is_trading_day(yesterday):
        print(f"{yesterday.date()} 非交易日，跳过")
        return
    date_str = yesterday.strftime("%Y-%m-%d")

    last_sent = config.get("last_sent_date", "")
    if date_str == last_sent:
        print(f"{date_str} 已发送过，跳过")
        return

    ok = fetch_send(date_str, mail_to_list)
    if ok:
        config["last_sent_date"] = date_str
        try:
            with open("config.json", "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

if __name__ == "__main__":
    main()
