import os
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs

# =========================
# Notion 설정
# =========================
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")

NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

TRADLINX_YEAR = "2025"

TARGET_KEYWORDS = [
    "통관목록심사완료",
    "입항적재화물목록 심사완료",
]


# =========================
# Notion 조회
# =========================
def get_tracking_items():
    url = f"https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}/query"
    res = requests.post(url, headers=NOTION_HEADERS, json={})
    data = res.json()

    items = []
    for row in data.get("results", []):
        props = row["properties"]

        raw = props.get("조회링크", {}).get("rich_text", [])
        value = raw[0]["plain_text"].strip() if raw else ""

        name = props.get("성함", {}).get("rich_text", [])
        name_text = name[0]["plain_text"] if name else ""

        items.append({
            "value": value,
            "page_id": row["id"],
            "name": name_text,
        })
    return items


# =========================
# ASAP
# =========================
def check_asap(url):
    res = requests.get(url, timeout=10)
    soup = BeautifulSoup(res.text, "html.parser")

    tables = soup.find_all("table")
    if len(tables) < 2:
        return None

    rows = tables[1].find_all("tr")[1:]
    for r in rows:
        tds = r.find_all("td")
        if len(tds) >= 3:
            step = tds[1].get_text(strip=True)
            time = tds[2].get_text(strip=True)
            if step == "통관목록심사완료":
                return time
    return None


# =========================
# Tradlinx
# =========================
def check_tradlinx(bl_no):
    url = (
        f"https://www.tradlinx.com/ko/unipass"
        f"?type=2&blNo={bl_no}&blYr={TRADLINX_YEAR}"
    )

    res = requests.get(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
        },
        timeout=10,
    )

    soup = BeautifulSoup(res.text, "html.parser")

    process_blocks = soup.select("div.process-detail")

    for block in process_blocks:
        step = block.select_one("li.tp-cd")
        time = block.select_one("li.rl-br-dttm")

        if not step:
            continue

        step_text = step.get_text(strip=True)
        time_text = time.get_text(strip=True) if time else ""

        for keyword in TARGET_KEYWORDS:
            if keyword in step_text:
                return time_text or "시간정보없음"

    return None


# =========================
# Notion 업데이트
# =========================
def update_notion(page_id, time_text):
    status = f"심사완료 [{time_text}]"

    url = f"https://api.notion.com/v1/pages/{page_id}"
    payload = {
        "properties": {
            "반입상태": {
                "rich_text": [
                    {"text": {"content": status}}
                ]
            }
        }
    }

    res = requests.patch(url, headers=NOTION_HEADERS, json=payload)
    if res.status_code == 200:
        print(f"[✅ 업데이트] {page_id} → {status}")
    else:
        print(f"[❌ 실패] {res.text}")


# =========================
# 메인
# =========================
def main():
    print("🚀 통관 자동 추적 시작")

    items = get_tracking_items()
    found = False

    for item in items:
        value = item["value"]
        page_id = item["page_id"]
        name = item["name"]

        print(f"\n🔍 검사중: {name} / {value}")

        # 1️⃣ URL이면 ASAP
        if value.startswith("http"):
            result = check_asap(value)

        # 2️⃣ 숫자만 있으면 Tradlinx
        elif re.fullmatch(r"\d+", value):
            result = check_tradlinx(value)

        else:
            print("⚠️ 알 수 없는 형식")
            continue

        if result:
            print(f"🎉 심사완료 발견 → {result}")
            update_notion(page_id, result)
            found = True

    if not found:
        print("\nℹ️ 아직 심사완료 없음")


if __name__ == "__main__":
    main()
