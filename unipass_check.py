import os
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs
from datetime import datetime

# 📌 Notion 환경변수
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")

# 📌 Notion 공통 헤더
NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

# 📌 공통 User-Agent (가끔 사이트에서 UA 없으면 막는 경우 있음)
UA_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123 Safari/537.36"
}


def is_probably_number(s: str) -> bool:
    if not s:
        return False
    return bool(re.fullmatch(r"\d{8,30}", s.strip()))


def get_tracking_items():
    """
    Notion DB에서 조회링크, 성함, page_id 가져오기
    - 조회링크가 URL이면: asap 링크로 판단
    - 조회링크가 숫자면: House B/L(송장번호)로 판단 (Tradlinx 조회)
    """
    url = f"https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}/query"
    response = requests.post(url, headers=NOTION_HEADERS, json={})

    print("[DEBUG] Notion status:", response.status_code)
    try:
        data = response.json()
    except Exception as e:
        print("[DEBUG] Notion 응답 JSON 파싱 실패:", e, response.text)
        return []

    if "results" not in data:
        print("[DEBUG] Notion 응답에 'results' 키가 없음. 전체 응답:")
        print(data)
        return []

    items = []
    for result in data["results"]:
        props = result["properties"]

        full_url = props.get("조회링크", {}).get("url", "") or ""
        name = props.get("성함", {}).get("rich_text", [])
        name_text = name[0]["plain_text"] if name else ""
        page_id = result["id"]

        raw = (full_url or "").strip()

        # 1) ASAP 링크(기존 방식)
        if raw.startswith("http"):
            parsed_url = urlparse(raw)
            query_params = parse_qs(parsed_url.query)
            customs_code = query_params.get("code", [""])[0]
            invoice_no = query_params.get("invoice", [""])[0]

            if customs_code and invoice_no:
                items.append({
                    "type": "asap",
                    "code": customs_code,
                    "invoice": invoice_no,
                    "page_id": page_id,
                    "name": name_text,
                    "raw": raw,
                })
            else:
                items.append({
                    "type": "unknown",
                    "page_id": page_id,
                    "name": name_text,
                    "raw": raw,
                })

        # 2) 숫자만 있으면 -> Tradlinx (하이원 House B/L)
        elif is_probably_number(raw):
            items.append({
                "type": "tradlinx",
                "bl_no": raw,
                "page_id": page_id,
                "name": name_text,
                "raw": raw,
            })

        else:
            items.append({
                "type": "unknown",
                "page_id": page_id,
                "name": name_text,
                "raw": raw,
            })

    return items


def check_unipass_status_asap(code, invoice):
    """(기존) ASAP 유니패스 처리단계 + 처리일시 가져오기"""
    url = f"https://asap-china.com/guide/unipass_delivery.php?code={code}&invoice={invoice}"
    response = requests.get(url, headers=UA_HEADERS, timeout=20)
    soup = BeautifulSoup(response.text, "html.parser")

    tables = soup.find_all("table")
    if len(tables) < 2:
        return []

    table = tables[1]
    rows = table.find_all("tr")[1:]  # 헤더 제외

    steps = []
    for row in rows:
        tds = row.find_all("td")
        if len(tds) > 2:
            step_text = tds[1].get_text(strip=True)
            time_text = tds[2].get_text(strip=True)
            steps.append({"step": step_text, "time": time_text})

    return steps


def fetch_tradlinx_steps(bl_no: str, year: int):
    """
    Tradlinx 페이지에서 처리단계(step) / 처리일시(time) 파싱
    - 네가 올린 HTML 기준: cargo-process 안에 process-detail 반복
      li.tp-cd = 단계명
      li.rl-br-dttm = 일시
    """
    url = f"https://www.tradlinx.com/ko/unipass?type=2&blNo={bl_no}&blYr={year}"
    r = requests.get(url, headers=UA_HEADERS, timeout=25)
    html = r.text

    soup = BeautifulSoup(html, "html.parser")
    cargo = soup.find("div", class_="cargo-process")
    if not cargo:
        # (확실하지 않음) 만약 JS 렌더링이라면 여기서 빈 페이지가 나올 수 있음
        return []

    steps = []
    for pd in cargo.find_all("div", class_="process-detail"):
        step_el = pd.select_one("ul li.tp-cd")
        time_el = pd.select_one("ul li.rl-br-dttm")
        if step_el and time_el:
            step = step_el.get_text(strip=True)
            time = time_el.get_text(strip=True)
            steps.append({"step": step, "time": time})

    return steps


def check_unipass_status_tradlinx(bl_no: str):
    """
    Tradlinx는 blYr(년도)가 필요해서:
    - 올해 먼저 시도
    - 안 나오면 작년 시도 (연말/연초 걸쳐있을 수 있어서)
    """
    this_year = datetime.now().year
    for y in [this_year, this_year - 1]:
        steps = fetch_tradlinx_steps(bl_no, y)
        if steps:
            return steps
    return []


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
        print(f"[⚠️ 업데이트 실패] {resp.status_code} / {resp.text}")


def main():
    print("[🚀 유니패스 자동 추적 시작]\n")

    items = get_tracking_items()
    any_found = False

    for it in items:
        name = it.get("name", "")
        raw = it.get("raw", "")

        if it["type"] == "asap":
            invoice = it["invoice"]
            print(f"[🔍 검사 중 - ASAP] {invoice} / {name}")
            steps = check_unipass_status_asap(it["code"], invoice)

        elif it["type"] == "tradlinx":
            bl_no = it["bl_no"]
            print(f"[🔍 검사 중 - TRADLINX] {bl_no} / {name}")
            steps = check_unipass_status_tradlinx(bl_no)

        else:
            print(f"[⚠️ 알 수 없는 형식] {name} / {raw}")
            continue

        target = next((s for s in steps if s["step"] == "통관목록심사완료"), None)
        if target:
            processed_at = target["time"]
            key = it.get("invoice") or it.get("bl_no") or raw
            print(f"[🎉 통관목록심사완료 발견] {key} / {name} / {processed_at}")
            update_notion_status(it["page_id"], processed_at)
            any_found = True

    if not any_found:
        print("[ℹ️ 아직 심사완료 없음]")


if __name__ == "__main__":
    main()
