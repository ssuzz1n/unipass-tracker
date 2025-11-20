import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs

# 📌 Notion 환경변수
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")

# 📌 Notion 공통 헤더
NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

def get_tracking_items():
    """Notion DB에서 조회링크, 성함, page_id 가져오기"""
    url = f"https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}/query"
    response = requests.post(url, headers=NOTION_HEADERS, json={})

    print("[DEBUG] Notion status:", response.status_code)
    try:
        data = response.json()
    except Exception as e:
        print("[DEBUG] Notion 응답 JSON 파싱 실패:", e, response.text)
        return []

    # ✅ 에러 응답일 때 바로 내용 찍고 종료
    if "results" not in data:
        print("[DEBUG] Notion 응답에 'results' 키가 없음. 전체 응답:")
        print(data)
        return []

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
    """유니패스 처리단계 + 처리일시 가져오기"""
    url = f"https://asap-china.com/guide/unipass_delivery.php?code={code}&invoice={invoice}"
    response = requests.get(url)
    soup = BeautifulSoup(response.text, "html.parser")
    tables = soup.find_all("table")

    if len(tables) < 2:
        return []

    table = tables[1]
    rows = table.find_all("tr")[1:]  # 헤더 제외

    steps = []
    for row in rows:
        tds = row.find_all("td")
        # No / 처리단계 / 처리일시 → 최소 3개 있어야 함
        if len(tds) > 2:
            step_text = tds[1].get_text(strip=True)   # 처리단계
            time_text = tds[2].get_text(strip=True)   # 처리일시
            steps.append({
                "step": step_text,
                "time": time_text,
            })

    return steps


def update_notion_status(page_id, processed_at):
    """
    노션 페이지의 '반입상태'를
    '심사완료 [처리일시]' 형태로 업데이트
    """
    status_text = f"심사완료 [{processed_at}]"

    url = f"https://api.notion.com/v1/pages/{page_id}"
    payload = {
        "properties": {
            "반입상태": {
                "rich_text": [{"text": {"content": status_text}}]
            }
        }
    }

    resp = requests.patch(url, headers=NOTION_HEADERS, json=payload)
    if resp.status_code == 200:
        print(f"[🟢 반입상태 업데이트 완료] {page_id} → {status_text}")
    else:
        print(f"[⚠️ 업데이트 실패] {resp.text}")


def main():
    print("[🚀 유니패스 자동 추적 시작]\n")

    items = get_tracking_items()
    any_found = False

    for code, invoice, page_id, url, name in items:
        print(f"[🔍 검사 중] {invoice} / {name}")
        steps = check_unipass_status(code, invoice)  
        # steps = [{"step": "...", "time": "..."}, ...] 구조
        target = next(
            (s for s in steps if s["step"] == "통관목록심사완료"),
            None
        )
        if target:
            processed_at = target["time"]  # 처리일시
            print(f"[🎉 통관목록심사완료 발견] {invoice} / {name} / {processed_at}")
            update_notion_status(page_id, processed_at)
            any_found = True
            
            
        if not any_found:
        print("[ℹ️ 반입신고 없음]")

if __name__ == "__main__":
    main()
