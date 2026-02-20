import requests
from bs4 import BeautifulSoup
import os
import json
from datetime import datetime, timedelta

ASAP_LOGIN_URL = "https://asap-china.com/elpisbbs/login.php"
ASAP_AJAX_URL = "https://asap-china.com/elpisbbs/ajax.nt_order_list_member.php"

ASAP_ID = os.getenv("ASAP_ID")
ASAP_PW = os.getenv("ASAP_PW")

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")

NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

LAST_FILE = "last_invoice.json"


def load_last_invoice():
    with open(LAST_FILE, "r") as f:
        data = json.load(f)
    return data["last_invoice"]


def save_last_invoice(invoice):
    with open(LAST_FILE, "w") as f:
        json.dump({"last_invoice": invoice}, f, indent=2)


def login():
    session = requests.Session()
    payload = {
        "mb_id": ASAP_ID,
        "mb_password": ASAP_PW,
    }
    session.post(ASAP_LOGIN_URL, data=payload)
    return session


def fetch_latest(session):
    payload = {
        "last": 0,
        "limit": 20,
        "mb_id": ASAP_ID,
    }
    res = session.post(ASAP_AJAX_URL, data=payload)
    return res.text


def parse_orders(html):
    soup = BeautifulSoup(html, "html.parser")
    results = []

    # 🔥 여기 부분은 실제 html 구조에 맞게 수정 필요
    for link in soup.find_all("a"):
        href = link.get("href")
        text = link.get_text(strip=True)

        if href and text.isdigit():
            full_link = "https://asap-china.com" + href
            results.append({
                "invoice": text,
                "link": full_link
            })

    return results


def add_to_notion(link, receiver=""):
    url = "https://api.notion.com/v1/pages"
    payload = {
        "parent": {"database_id": NOTION_DATABASE_ID},
        "properties": {
            "조회링크": {"url": link},
            "성함": {
                "rich_text": [
                    {"text": {"content": receiver}}
                ]
            }
        }
    }
    requests.post(url, headers=NOTION_HEADERS, json=payload)


def main():
    last_invoice = load_last_invoice()
    print("📌 현재 기준:", last_invoice)
   

    session = login()

    offset = 0
    limit = 20
    newest_invoice = None
    stop = False

    today = datetime.today()
    sdate = (today - timedelta(days=30)).strftime("%Y-%m-%d")
    edate = today.strftime("%Y-%m-%d")

    while True:
        payload = {
            "last": offset,
            "limit": limit,
            "mb_id": ASAP_ID,
            "sdate": sdate,
            "edate": edate,
        }

        res = session.post(ASAP_AJAX_URL, data=payload)
        html = res.text
        print(soup.prettify()[:1000])
        orders = parse_orders(html)

        # 주문이 아예 없으면 종료
        if not orders:
            print("📭 더 이상 주문 없음.")
            break

        for idx, order in enumerate(orders):

            # 첫 페이지 첫 주문 = 최신 기준
            if offset == 0 and idx == 0:
                newest_invoice = order["invoice"]

            if order["invoice"] == last_invoice:
                print("🛑 기준 도달. 중단.")
                stop = True
                break

            print("➕ 추가:", order["invoice"])
            add_to_notion(order["link"])

        if stop:
            break

        # 다음 페이지로 이동
        offset += limit

    if newest_invoice:
        save_last_invoice(newest_invoice)
        print("✅ 기준 업데이트:", newest_invoice)





if __name__ == "__main__":
    main()
