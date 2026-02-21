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


# =============================
# 🔹 기준 저장 / 불러오기
# =============================

def load_last_invoice():
    if not os.path.exists(LAST_FILE):
        return None
    with open(LAST_FILE, "r") as f:
        data = json.load(f)
    return data.get("last_invoice")


def save_last_invoice(invoice):
    with open(LAST_FILE, "w") as f:
        json.dump({"last_invoice": invoice}, f, indent=2)


# =============================
# 🔹 로그인
# =============================

def login():
    session = requests.Session()

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": ASAP_LOGIN_URL,
    }

    payload = {
        "mb_id": ASAP_ID,
        "mb_password": ASAP_PW,
    }

    res = session.post(ASAP_LOGIN_URL, data=payload, headers=headers)
    print("🔐 로그인 응답코드:", res.status_code)
    print("🍪 로그인 쿠키:", session.cookies.get_dict())

    return session


# =============================
# 🔹 HTML에서 송장 / 링크 / 이름 파싱
# =============================

def parse_orders(html):
    soup = BeautifulSoup(html, "html.parser")
    orders = []

    # 🔥 송장번호 a 태그 찾기
    for a in soup.find_all("a", href=True):
        invoice = a.get_text(strip=True)

        if not invoice.isdigit():
            continue

        link = a["href"]

        # ✅ 송장 기준으로 부모 테이블 탐색
        parent = a.find_parent("tr")
        name = ""

        if parent:
            name_tag = parent.find("p")
            if name_tag:
                name = name_tag.get_text(strip=True)

        orders.append({
            "invoice": invoice,
            "link": link,
            "name": name
        })

    return orders


# =============================
# 🔹 노션 저장
# =============================

def add_to_notion(link, receiver):
    url = "https://api.notion.com/v1/pages"

    payload = {
        "parent": {"database_id": NOTION_DATABASE_ID},
        "properties": {
            "조회링크": {
                "url": link
            },
            "성함": {
                "rich_text": [
                    {"text": {"content": receiver}}
                ]
            }
        }
    }

    requests.post(url, headers=NOTION_HEADERS, json=payload)


# =============================
# 🔥 메인
# =============================

def main():
    last_invoice = load_last_invoice()
    print("📌 현재 기준:", last_invoice)

    session = login()
    session.get("https://asap-china.com/mypage/service_list.php")

    offset = 0
    limit = 20
    newest_invoice = None
    stop = False

    today = datetime.today()
    sdate = (today - timedelta(days=30)).strftime("%Y-%m-%d")
    edate = today.strftime("%Y-%m-%d")

    while True:

        params = {
            "last": offset,
            "limit": limit,
            "sdate": sdate,
            "edate": edate,
            "mb_id": ASAP_ID,
        }

        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://asap-china.com/mypage/service_list.php",
            "X-Requested-With": "XMLHttpRequest",
        }

        res = session.post(
            ASAP_AJAX_URL,
            headers=headers,
            params=params
        )

        print("📡 응답코드:", res.status_code)

        if res.status_code != 200:
            break

        html = res.text

        if not html.strip():
            break

        orders = parse_orders(html)

        if not orders:
            break

        for order in orders:

            invoice = order["invoice"]
            link = "https://www.asap-china.com" + order["link"]
            name = order["name"]

            if not newest_invoice:
                newest_invoice = invoice

            # ✅ 기준 도달하면 중단
            if last_invoice and int(invoice) <= int(last_invoice):
                print("🛑 기준 도달 -> 중단")
                stop = True
                break

            print("➕ 저장:", invoice, name)

            add_to_notion(link, name)

        if stop:
            break

        offset += limit

    if newest_invoice:
        save_last_invoice(newest_invoice)
        print("✅ 기준 업데이트:", newest_invoice)


if __name__ == "__main__":
    main()
