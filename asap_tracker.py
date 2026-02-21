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


# ==================================================
# 🔥 노션에서 마지막 기준 가져오기
# ==================================================

def get_last_invoice_from_notion():

    if not NOTION_DATABASE_ID:
        print("❌ 노션 DB ID 없음")
        return None

    url = f"https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}/query"

    payload = {
        "page_size": 1,
        "sorts": [
            {
                "property": "created_time",
                "direction": "descending"
            }
        ]
    }

    res = requests.post(url, headers=NOTION_HEADERS, json=payload)

    if res.status_code != 200:
        print("❌ 노션 기준 조회 실패")
        return None

    data = res.json()
    results = data.get("results", [])

    if not results:
        return None

    page = results[0]
    props = page["properties"]

    # 🔥 조회링크 값 가져오기
    try:
        url_property = props["조회링크"]["url"]
    except:
        return None

    if not url_property:
        return None

    # 🔥 url에서 invoice 번호 추출
    invoice = url_property.split("invoice=")[-1]

    if invoice.isdigit():
        return invoice

    return None


# ==================================================
# 🔥 로그인
# ==================================================

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

    if res.status_code != 200:
        return None

    return session


# ==================================================
# 🔥 파싱
# ==================================================

def parse_orders(html):

    soup = BeautifulSoup(html, "html.parser")
    orders = []

    for a in soup.find_all("a", href=True):

        invoice = a.get_text(strip=True)

        if not invoice.isdigit():
            continue

        link = a["href"]

        if link.startswith("http"):
            full_link = link
        else:
            full_link = "https://www.asap-china.com" + link

        name = ""

        current_tr = a.find_parent("tr")

        if current_tr:
            next_tr = current_tr.find_next_sibling("tr")

            if next_tr:
                p_tags = next_tr.find_all("p")

                if len(p_tags) >= 2:
                    name = p_tags[1].get_text(strip=True)

                elif len(p_tags) == 1:
                    name = p_tags[0].get_text(strip=True)

        if "배송" in name:
            name = ""

        orders.append({
            "invoice": invoice,
            "link": full_link,
            "name": name
        })

    return orders


# ==================================================
# 🔥 노션 저장
# ==================================================

def add_to_notion(link, receiver):

    if not NOTION_DATABASE_ID:
        print("❌ 노션 DB ID 없음")
        return

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


# ==================================================
# 🔥 메인
# ==================================================

def main():

    # ✅ 기준을 이제 노션에서 가져옴
    last_invoice = get_last_invoice_from_notion()

    print("📌 노션 기준:", last_invoice)

    session = login()
    if not session:
        return

    session.get("https://asap-china.com/mypage/service_list.php")

    offset = 0
    limit = 20
    newest_invoice = None

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
            link = order["link"]
            name = order["name"]

            if not newest_invoice:
                newest_invoice = invoice

            if last_invoice and int(invoice) <= int(last_invoice):
                print("🛑 기준 도달 -> 중단")
                break

            print("➕ 저장:", invoice, name)
            add_to_notion(link, name)

        else:
            offset += limit
            continue

        break


    print("✅ 실행 완료")


if __name__ == "__main__":
    main()
