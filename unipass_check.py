import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs
import smtplib
from email.message import EmailMessage

# 📌 Notion & Email 환경변수
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")  # pink_glitter@naver.com
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")

# 📌 Notion 공통 헤더
NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

def get_tracking_items():
    """
    Notion DB에서 조회링크, 성함, page_id 꺼내오기
    (notion-client 대신 REST API 직접 호출)
    """
    url = f"https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}/query"
    response = requests.post(url, headers=NOTION_HEADERS, json={})
    response.raise_for_status()
    data = response.json()

    items = []
    for result in data["results"]:
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

def check_unipass_status(code, invoice):
    url = f"https://asap-china.com/guide/unipass_delivery.php?code={code}&invoice={invoice}"
    response = requests.get(url)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    tables = soup.find_all("table", style=lambda v: v and "margin:0 auto" in v)

    if len(tables) < 2:
        print(f"[❌ 처리단계 테이블 없음] {invoice}")
        return []

    table = tables[1]  # 두 번째 테이블이 처리단계
    rows = table.find_all("tr")[1:]  # 첫 줄은 헤더
    if not rows:
        print(f"[⚠️ 처리단계 테이블은 있지만 내용 없음] {invoice}")
        return []

    steps = []
    for row in rows:
        tds = row.find_all("td")
        if len(tds) > 1:
            step = tds[1].get_text(strip=True)
            steps.append(step)

    print(f"[✅ 처리단계 감지] {invoice} ▶ {steps}")
    return steps

def delete_notion_page(page_id):
    """
    Notion 페이지 아카이브 처리 (리스트에서 빼기)
    notion.pages.update 대신 REST API PATCH 사용
    """
    url = f"https://api.notion.com/v1/pages/{page_id}"
    payload = {"archived": True}
    resp = requests.patch(url, headers=NOTION_HEADERS, json=payload)
    if resp.status_code != 200:
        print(f"[⚠️ Notion 페이지 아카이브 실패] {page_id} / status {resp.status_code} / {resp.text}")
    else:
        print(f"[🗑 Notion 페이지 아카이브 완료] {page_id}")

def send_email(subject, body):
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = EMAIL_ADDRESS  # 본인에게 보내기
    msg.set_content(body)

    with smtplib.SMTP_SSL("smtp.naver.com", 465) as smtp:
        smtp.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        smtp.send_message(msg)

def main():
    print("[✅ 유니패스 자동 추적 시작]\n")
    print(f"EMAIL: {EMAIL_ADDRESS} / TO: {EMAIL_ADDRESS}\n")

    items = get_tracking_items()
    found_items = []

    for code, invoice, page_id, url, name in items:
        print(f"[🔍 검사 중] {invoice} / {name} / 링크: {url}")
        steps = check_unipass_status(code, invoice)
        if "반입신고" in steps:
            found_items.append((invoice, url, name))
            delete_notion_page(page_id)
            print(f"[🔔 반입신고 확인됨] {invoice} / 삭제됨")

    if found_items:
        subject = "[📦 반입신고 알림] 유니패스 통관 처리 완료"
        body = "다음 송장이 '반입신고' 단계에 도달했습니다:\n\n"
        for invoice, url, name in found_items:
            body += f"- {name} 님 / 송장번호: {invoice}\n"
            body += f"  ▶ 링크: {url}\n\n"
        body += "📮 [스마트스토어 송장 입력 바로가기]\n"
        body += "👉 https://sell.smartstore.naver.com/#/naverpay/sale/delivery/situation?summaryInfoType=DELIVERING\n\n"
        body += "💡 CJ 운송장으로 수정해주세요!"
        send_email(subject, body)
    else:
        print("[ℹ️ 반입신고 없음] 메일 전송 생략")

if __name__ == "__main__":
    main()
