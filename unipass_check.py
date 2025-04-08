import os
import requests
import json
import smtplib
from email.mime.text import MIMEText
from urllib.parse import urlparse, parse_qs
from bs4 import BeautifulSoup
from notion_client import Client

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
EMAIL_TO = os.getenv("EMAIL_TO")

notion = Client(auth=NOTION_TOKEN)

STATUS_FILE = "status.json"

def load_status():
    if os.path.exists(STATUS_FILE):
        with open(STATUS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_status(data):
    with open(STATUS_FILE, "w") as f:
        json.dump(data, f)

def get_tracking_items():
    response = notion.databases.query(database_id=NOTION_DATABASE_ID)
    items = []
    for result in response["results"]:
        props = result["properties"]
        full_url = props.get("조회링크", {}).get("url", "")
        name = props.get("성함", {}).get("rich_text", [])
        name_text = name[0]["plain_text"] if name else ""
        page_id = result["id"]

        parsed_url = urlparse(full_url)
        query_params = parse_qs(parsed_url.query)
        customs_code = query_params.get("code", [""])[0]
        invoice_no = query_params.get("invoice", [""])[0]

        if customs_code and invoice_no:
            items.append((customs_code, invoice_no, page_id, full_url, name_text))
    return items

def check_status(customs_code, invoice_no):
    url = f"https://unipass.customs.go.kr/csp/index.do"
    data = {
        "cargMtNo": invoice_no,
        "brCd": customs_code,
        "cargTp": "1"
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    res = requests.post(url, data=data, headers=headers)
    soup = BeautifulSoup(res.text, "html.parser")
    table = soup.find("table", class_="table")
    if not table:
        print(f"[❌ 처리단계 없음] {invoice_no}")
        return []
    return [row.text.strip() for row in table.find_all("td") if row.text.strip()]

def send_email(subject, body):
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = EMAIL_TO

    with smtplib.SMTP_SSL("smtp.naver.com", 465) as smtp:
        smtp.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        smtp.send_message(msg)

def delete_item_from_notion(page_id):
    notion.pages.update(page_id=page_id, archived=True)

def main():
    print("\n[✅ 유니패스 자동 추적 시작]")
    print(f"EMAIL: {EMAIL_ADDRESS} / TO: {EMAIL_TO}\n")
    status_data = load_status()
    tracking_items = get_tracking_items()

    for customs_code, invoice_no, page_id, link, name in tracking_items:
        key = f"{customs_code}_{invoice_no}"
        status_list = check_status(customs_code, invoice_no)

        if not status_list:
            continue

        if "반입신고" in status_list:
            if status_data.get(key) != "반입신고":
                subject = f"[📦 반입신고 상태 도달] {invoice_no}"
                body = f"송장번호 {invoice_no}가 반입신고 상태에 도달하여 리스트에서 삭제되었습니다.\n"
                if name:
                    body += f"성함: {name}\n"
                body += f"조회링크: {link}"

                send_email(subject, body)
                delete_item_from_notion(page_id)
                status_data[key] = "반입신고"
                print(f"[✅ 처리 완료] {invoice_no}")
        else:
            print(f"[📦 추적 중] {invoice_no} 상태: {status_list[-1]}")

    save_status(status_data)

if __name__ == "__main__":
    main()
