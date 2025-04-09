import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs
from notion_client import Client
import smtplib
from email.message import EmailMessage
from dotenv import load_dotenv

# 📦 환경변수 로드
load_dotenv()
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
EMAIL_NAME = os.getenv("EMAIL_NAME") or "재입고 알리미"
TO_EMAIL = os.getenv("TO_EMAIL") or EMAIL_ADDRESS

# 📌 Notion 클라이언트
notion = Client(auth=NOTION_TOKEN)

# 🔍 상품 재입고 여부 확인 함수
def is_restocked(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, timeout=10)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")

        sold_out_tag = soup.find("div", class_="sold-out") or soup.find(string=lambda t: "품절" in t)
        return sold_out_tag is None
    except Exception as e:
        print(f"[⚠️ 요청 실패] {url}: {e}")
        return False

# 🗃️ Notion 상품 링크 가져오기
def get_product_links():
    items = []
    try:
        res = notion.databases.query(database_id=NOTION_DATABASE_ID)
        for result in res["results"]:
            title_prop = result["properties"].get("상품 링크", {})
            if title_prop.get("title"):
                title_text = title_prop["title"][0].get("plain_text", "")
                if title_text:
                    items.append((title_text, result["id"]))
    except Exception as e:
        print(f"[⚠️ Notion 불러오기 실패] {e}")
    return items

# 🧹 Notion에서 항목 삭제

def delete_notion_page(page_id):
    try:
        notion.pages.update(page_id=page_id, archived=True)
    except Exception as e:
        print(f"[⚠️ Notion 삭제 실패] {page_id}: {e}")

# 📧 메일 전송

def send_email(restocked_links):
    subject = "[🔔 재입고 알림] 타오바오 상품 구매 가능"
    body = "다음 상품이 다시 구매 가능해졌습니다:\n\n"
    for link in restocked_links:
        body += f"- 상품 링크: {link}\n"

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{EMAIL_NAME} <{EMAIL_ADDRESS}>"
    msg["To"] = TO_EMAIL
    msg.set_content(body)

    try:
        with smtplib.SMTP_SSL("smtp.naver.com", 465) as smtp:
            smtp.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            smtp.send_message(msg)
        print("[📧 메일 전송 완료]")
    except Exception as e:
        print(f"[⚠️ 메일 전송 실패] {e}")

# ✅ 메인 로직

def main():
    print("[🚀 타오바오 재입고 알림 시스템 시작]")
    links = get_product_links()
    restocked = []

    for url, page_id in links:
        print(f"[🔍 확인 중] {url}")
        if is_restocked(url):
            restocked.append(url)
            delete_notion_page(page_id)
            print(f"[✅ 재입고 확인 및 삭제] {url}")

    if restocked:
        send_email(restocked)
    else:
        print("[ℹ️ 재입고 없음] 메일 생략")

if __name__ == "__main__":
    main()
