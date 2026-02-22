import requests
from bs4 import BeautifulSoup
import os
import time
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
# 🔥 노션에서 마지막 기준 링크 가져오기 (SortKey 기준)
# ==================================================

def get_last_link_from_notion():

    if not NOTION_DATABASE_ID:
        print("❌ 노션 DB ID 없음")
        return None

    url = f"https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}/query"

    payload = {
        "page_size": 100,
        "sorts": [
            {
                "property": "SortKey",
                "direction": "descending"
            }
        ]
    }

    res = requests.post(url, headers=NOTION_HEADERS, json=payload)

    print("🔎 노션 API 응답코드:", res.status_code)

    if res.status_code != 200:
        print("🔎 노션 API 응답:", res.text)
        return None

    results = res.json().get("results", [])

    if not results:
        return None

    for page in results:

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
# 🔐 로그인
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
# 🔥 노션 저장 (SortKey 추가!!)
# ==================================================

def add_to_notion(link, receiver):

    if not NOTION_DATABASE_ID:
        print("❌ 노션 DB ID 없음")
        return

    url = "https://api.notion.com/v1/pages"

    sort_key = time.time()  # ✅ 자동 증가 키

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
            },
            "SortKey": {   # ✅ 새로 추가된 필드
                "number": sort_key
            }
        }
    }

    res = requests.post(url, headers=NOTION_HEADERS, json=payload)

    if res.status_code != 200:
        print("❌ 노션 저장 실패:", res.text)


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
    time.sleep(1)

    offset = 0
    limit = 20

    today = datetime.today()
    #sdate = (today - timedelta(days=10)).strftime("%Y-%m-%d")
    #edate = today.strftime("%Y-%m-%d")
    sdate = "2000-01-01"
    edate = "2099-12-31"

    while True:

        params = {
            "last": offset,
            "limit": limit,
            "find": "",
            "value": "",
            "or_de_no": "",
            "state": "",
            "sdate": sdate,
            "edate": edate,
            "mb_id": ASAP_ID,
            "type": "",
            "last_code": "",
            "it_code": "",
            "dtype": "",
            "gr_output_stay_type": "",
            "gr_var5": "",
            "gr_unipass_result": "",
            "gr_fltno": "",
            "gr_fltno2": "",
        }

       headers = {
           "User-Agent": "Mozilla/5.0",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://asap-china.com/mypage/service_list.php",
            "Origin": "https://asap-china.com"
       }

        res = session.post(
            ASAP_AJAX_URL,
            headers=headers,
            params=params
        )

        print("AJAX 응답 상태코드:", res.status_code)
        print("AJAX 응답 길이:", len(res.text))

        #디버깅
        html = res.text

        print("\n============================")
        print("🔍 HTML 일부 출력 (앞 2000자)")
        print("============================\n")
        print(html[:2000])

        orders = parse_orders(html)

        print("\n============================")
        print("📦 첫 페이지 주문 링크 목록")
        print("============================\n")

        for i, o in enumerate(orders):
            print(f"{i+1}. {o['link']}")

        print("\n============================")
        print("🎯 기준 링크 위치 확인")
        print("============================\n")
    
        if last_link:
            for i, o in enumerate(orders):
                if o["link"] == last_link:
                    print(f"⚠ 기준 링크가 {i+1}번째에 있음")
                    break
            else:
                print("❌ 기준 링크가 이 페이지에 없음")
    
        print("\n✅ 디버깅 완료")

        #끝

        if res.status_code != 200:
            break

        html = res.text

        if not html.strip():
            break

        orders = parse_orders(html)
        if not orders:
            break

        valid_orders = []

        for order in orders:

            link = order["link"]

            if last_link and link == last_link:
                print("🛑 기준 링크 발견 -> 중단")
                break

            valid_orders.append(order)

        valid_orders.reverse()

        for order in valid_orders:
            print("➕ 저장:", order["invoice"], order["name"])
            add_to_notion(order["link"], order["name"])

        if last_link and any(o["link"] == last_link for o in orders):
            break

        offset += limit

    print("✅ 실행 완료")


if __name__ == "__main__":
    main()
