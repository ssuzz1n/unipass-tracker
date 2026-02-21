import requests
from bs4 import BeautifulSoup
import os
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
# 🔥 노션에서 마지막 기준 링크 가져오기
# ==================================================

def get_last_link_from_notion():

    if not NOTION_DATABASE_ID:
        print("❌ 노션 DB ID 없음")
        return None

    url = f"https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}/query"

    payload = {
        "page_size": 100
    }

    res = requests.post(url, headers=NOTION_HEADERS, json=payload)

    print("🔎 노션 API 응답코드:", res.status_code)

    if res.status_code != 200:
        print("🔎 노션 API 응답:", res.text)
        return None

    results = res.json().get("results", [])

    if not results:
        return None

    # 최신순 정렬
    results_sorted = sorted(
        results,
        key=lambda x: x["created_time"],
        reverse=True
    )

    for page in results_sorted:
        props = page.get("properties", {})

        try:
            url_property = props["조회링크"]["url"]
        except:
            continue

        if url_property and url_property.strip():
            print("✅ 기준 링크 발견:", url_property)
            return url_property.strip()

    print("⚠ 기준 링크 없음")
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
# 🔥 HTML 파싱
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

    last_link = get_last_link_from_notion()
    print("📌 노션 기준 링크:", last_link)

    session = login()
    if not session:
        return

    session.get("https://asap-china.com/mypage/service_list.php")

    offset = 0
    limit = 20

    today = datetime.today()
    edate = today.strftime("%Y-%m-%d")

    while True:

        params = {
            "last": offset,
            "limit": limit,
            "sdate": "2026-02-20",
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

        valid_orders = []

        # 🔥 기준 체크
        for order in orders:

            invoice = order["invoice"]
            link = order["link"]

            # 기준 만나면 중단
            if last_link and link == last_link:
                print("🛑 기준 링크 발견 -> 중단")
                break

            valid_orders.append(order)

        # 🔥 저장 전에 뒤집기 (아래부터 쌓이게)
        valid_orders.reverse()

        for order in valid_orders:
            print("➕ 저장:", order["invoice"], order["name"])
            add_to_notion(order["link"], order["name"])

        # 기준 만나서 break 된 경우
        if last_link and any(o["link"] == last_link for o in orders):
            break

        offset += limit

    print("✅ 실행 완료")


if __name__ == "__main__":
    main()
