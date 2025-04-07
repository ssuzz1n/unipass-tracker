import requests
from bs4 import BeautifulSoup
import smtplib
import json
from email.mime.text import MIMEText
from email.utils import formataddr
from dotenv import load_dotenv
import os
import re
from notion_client import Client  # Notion SDK

# .env 로드
load_dotenv()

# 이메일 설정
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_NAME = os.getenv("EMAIL_NAME") or "유니패스 알리미"
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
TO_EMAIL = os.getenv("TO_EMAIL") or EMAIL_ADDRESS

# Notion 설정
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID", "").strip()
NOTION_TOKEN = os.getenv("NOTION_TOKEN", "").strip()

if NOTION_DATABASE_ID and '-' not in NOTION_DATABASE_ID:
    NOTION_DATABASE_ID = str(re.sub(r"(.{8})(.{4})(.{4})(.{4})(.{12})", r"\1-\2-\3-\4-\5", NOTION_DATABASE_ID))


notion = Client(auth=NOTION_TOKEN)

try:
    print("[🔍 Notion DB 조회 테스트]")
    db = notion.databases.retrieve(database_id=NOTION_DATABASE_ID)
    print("[✅ Notion DB 이름]", db["title"][0]["text"]["content"])
except Exception as e:
    print(f"[⚠️ DB 조회 실패] {e}")

# 상태 저장 파일
STATUS_FILE = "unipass_status.json"

def load_status():
    if os.path.exists(STATUS_FILE):
        with open(STATUS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_status(status_data):
    with open(STATUS_FILE, "w") as f:
        json.dump(status_data, f, indent=4)

# 처리단계 조회
def check_status(customs_code, invoice_no):
    url = f"https://asap-china.com/guide/unipass_delivery.php?code={customs_code}&invoice={invoice_no}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
    try:
        res = requests.get(url, headers=headers)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")

        tables = soup.find_all("table")
        if len(tables) < 2:
            print(f"[❌ 처리단계 없음] {customs_code}, {invoice_no}")
            return []

        status_table = tables[1]
        rows = status_table.find_all("tr")[1:]

        status_list = []
        for row in rows:
            cols = row.find_all("td")
            if len(cols) >= 2:
                status = cols[1].text.strip()
                status_list.append(status)

        return status_list
    except Exception as e:
        print(f"[⚠️ 에러] {customs_code}, {invoice_no}: {e}")
        return []

# 메일 발송
def send_email(subject, body):
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = formataddr((EMAIL_NAME, EMAIL_ADDRESS))
    msg["To"] = TO_EMAIL

    try:
        with smtplib.SMTP_SSL("smtp.naver.com", 465) as server:
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.send_message(msg)
        print(f"[📧 메일 전송 완료] {subject}")
    except Exception as e:
        print(f"[⚠️ 메일 전송 실패] {e}")

# Notion에서 송장번호 가져오기 (customs_code + invoice + page_id)
def get_tracking_items():
    try:
        response = notion.databases.query(database_id=NOTION_DATABASE_ID)
        results = response.get("results", [])
        tracking_items = []

        for item in results:
            props = item["properties"]
            # 여기서 '통관부호'와 '송장번호' 컬럼 이름이 정확히 일치해야 함
            customs_code = props["통관부호"]["rich_text"][0]["plain_text"]
            invoice = props["송장번호"]["title"][0]["plain_text"]
            page_id = item["id"]
            tracking_items.append((customs_code, invoice, page_id))

        return tracking_items
    except Exception as e:
        print(f"[⚠️ Notion 데이터 불러오기 실패] {e}")
        return []

# Notion에서 항목 삭제
def delete_item_from_notion(page_id):
    try:
        notion.pages.update(page_id=page_id, archived=True)
        print(f"[🗑️ Notion 삭제 완료] {page_id}")
    except Exception as e:
        print(f"[⚠️ Notion 삭제 실패] {page_id}: {e}")

# 메인 로직
def main():
    status_data = load_status()
    tracking_items = get_tracking_items()

    for customs_code, invoice_no, page_id in tracking_items:
        key = f"{customs_code}_{invoice_no}"

        status_list = check_status(customs_code, invoice_no)
        if not status_list:
            continue

        if "반입신고" in status_list:
            if status_data.get(key) != "반입신고":
                subject = "[📦 반입신고 상태 도달] " + invoice_no
                body = f"송장번호 {invoice_no}가 반입신고 상태에 도달하여 자동으로 리스트에서 삭제되었습니다."
                send_email(subject, body)
                delete_item_from_notion(page_id)
                status_data[key] = "반입신고"
                print(f"[✅ 처리 완료] {invoice_no}")
        else:
            print(f"[📦 추적 중] {invoice_no} 상태: {status_list[-1]}")

    save_status(status_data)

if __name__ == "__main__":
    print("[✅ 유니패스 자동 추적 시작]")
    print(f"EMAIL: {EMAIL_ADDRESS} / TO: {TO_EMAIL}")
    print(f"NOTION_DATABASE_ID: {repr(NOTION_DATABASE_ID)}")
    print(f"NOTION_TOKEN: {repr(NOTION_TOKEN)}")
    main()
