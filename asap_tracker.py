import requests
from bs4 import BeautifulSoup
import os
import json

# ------------------------
# ASAP 로그인 정보
# ------------------------
ASAP_LOGIN_URL = "https://asap-china.com/elpisbbs/login.php"
ASAP_AJAX_URL = "https://asap-china.com/elpisbbs/ajax.nt_order_list_member.php"

ASAP_ID = os.getenv("ASAP_ID")
ASAP_PW = os.getenv("ASAP_PW")

# ------------------------
# Notion 설정
# ------------------------
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")

NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}


# ------------------------
# 1️⃣ 로그인 세션 생성
# ------------------------
def login():
    session = requests.Session()

    payload = {
        "mb_id": ASAP_ID,
        "mb_password": ASAP_PW,
    }

    response = session.post(ASAP_LOGIN_URL, data=payload)

    if response.status_code == 200:
        print("✅ 로그인 성공")
        return session
    else:
        raise Exception("❌ 로그인 실패")


# ------------------------
# 2️⃣ AJAX 호출
# ------------------------
def fetch_latest_orders(session):
    payload = {
        "last": 0,
        "limit": 20,
        "mb_id": ASAP_ID,
    }

    response = session.post(ASAP_AJAX_URL, data=payload)

    if response.status_code != 200:
        raise Exception("❌ AJAX 호출 실패")

    return response.text


# ------------------------
# 3️⃣ HTML 파싱
# ------------------------
def parse_orders(html):
    soup = BeautifulSoup(html, "html.parser")
    results = []

    # 송장번호 링크 구조에 맞게 수정 필요
    links = soup.find_all("a")

    for link in links:
        href = link.get("href")
        text = link.get_text(strip=True)

        if href and text.isdigit():  # 숫자로 된 송장번호만
            full_link = "https://asap-china.com" + href

            # 수취인명은 부모 구조에서 찾아야 할 수도 있음
            parent = link.find_parent()
            receiver = parent.get_text(strip=True)

            results.append({
                "link": full_link,
                "receiver": receiver
            })

    return results


# ------------------------
# 4️⃣ 노션 중복 체크
# ------------------------
def exists_in_notion(link):
    url = f"https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}/query"

    payload = {
        "filter": {
            "property": "조회링크",
            "url": {
                "equals": link
            }
        }
    }

    res = requests.post(url, headers=NOTION_HEADERS, json=payload)
    data = res.json()

    return len(data["results"]) > 0


# ------------------------
# 5️⃣ 노션 추가
# ------------------------
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
                    {
                        "text": {
                            "content": receiver
                        }
                    }
                ]
            }
        }
    }

    requests.post(url, headers=NOTION_HEADERS, json=payload)


# ------------------------
# 메인 실행
# ------------------------
def main():
    session = login()
    html = fetch_latest_orders(session)
    orders = parse_orders(html)

    for order in orders:
        if not exists_in_notion(order["link"]):
            print("➕ 추가:", order["link"])
            add_to_notion(order["link"], order["receiver"])
        else:
            print("⏩ 이미 존재:", order["link"])


if __name__ == "__main__":
    main()
