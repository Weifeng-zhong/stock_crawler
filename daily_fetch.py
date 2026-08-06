import smtplib
import os
import sys
import json
import argparse
import traceback
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone, timedelta
from chinese_calendar import is_workday

from stock_api import fetch_sse, fetch_sse_stock, fetch_sse_fund, fetch_szse

BJ_TZ = timezone(timedelta(hours=8))


def is_trading_day(dt):
    return is_workday(dt)


def prev_trading_day(dt):
    d = dt - timedelta(days=1)
    while not is_trading_day(d):
        d -= timedelta(days=1)
    return d


def send_email(subject, body, mail_to):
    mail_user = os.environ["MAIL_USER"]
    mail_pass = os.environ["MAIL_PASS"]
    msg = MIMEMultipart()
    msg["From"] = mail_user
    msg["To"] = mail_to
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))
    last_err = None
    for port in [465, 587]:
        try:
            if port == 465:
                with smtplib.SMTP_SSL("smtp.qq.com", port, timeout=15) as s:
                    s.login(mail_user, mail_pass)
                    s.send_message(msg)
            else:
                with smtplib.SMTP("smtp.qq.com", port, timeout=15) as s:
                    s.starttls()
                    s.login(mail_user, mail_pass)
                    s.send_message(msg)
            print(f"smtp.qq.com:{port} 发送成功")
            return True
        except Exception as e:
            last_err = e
            print(f"smtp.qq.com:{port} 失败: {e}")
    raise smtplib.SMTPAuthenticationError(550, f"All ports failed: {last_err}".encode())


def fetch_send(date_str, mail_to_list):
    print(f"获取 {date_str} 数据...")
    ss = fetch_sse_stock(date_str)
    sf = fetch_sse_fund(date_str)
    zs, zf = fetch_szse(date_str)

    values = {"上交所股票": ss, "上交所基金": sf, "深交所股票": zs, "深交所基金": zf}
    failed = [k for k, v in values.items() if v is None]

    if len(failed) == 4:
        print(f"{date_str} 全部数据获取失败，本次不发送邮件")
        return False

    def v(x):
        return f"{x / 10000:.2f}" if x is not None else "获取失败"

    line = f"{date_str} | {v(ss)} | {v(sf)} | {v(zs)} | {v(zf)}"
    print(line)
    if failed:
        print(f"警告: {date_str} 以下数据获取失败(已标注): {', '.join(failed)}")

    subject = f"沪深成交数据 {date_str}"
    body = f"前一交易日成交数据（单位：万亿元）\n\n日期 | 上交所股票 | 上交所基金 | 深交所股票 | 深交所基金\n--- | --- | --- | --- | ---\n{line}\n\n如需退订，请访问：https://stockcrawler-qe3y5qgjgyceaazkpajrzd.streamlit.app/\n(数据来源：上交所、深交所官网)"

    ok_count = 0
    for mail_to in mail_to_list:
        try:
            send_email(subject, body, mail_to)
            ok_count += 1
            print(f"邮件已发送至 {mail_to}")
        except Exception as e:
            print(f"发送至 {mail_to} 失败: {e}")
    if ok_count < len(mail_to_list):
        print(f"部分收件人发送失败: {ok_count}/{len(mail_to_list)} 成功")
        return False
    return True


def main():
    try:
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
        if not ok:
            sys.exit(1)
        config["last_sent_date"] = date_str
        try:
            with open("config.json", "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
