import os
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs
from datetime import datetime

# ─────────────────────────────────────────────────────────────
# 장부 DB 전용 유니패스 자동 추적
# 기존 unipass_check.py(송장 DB)와 병행 운영
#
# 환경변수:
#   NOTION_TOKEN   - 기존과 동일한 Notion API 키
#   LEDGER_DB_ID   - 장부 Notion DB ID (송장 DB와 별개)
#
# 흐름:
#   1. 장부 DB에서 배송상태 = 'Not started' 인 항목 조회
#   2. 배송조회링크(ASAP unipass URL) 로 통관 상태 확인
#   3. '통관목록심사완료' 발견 → 배송상태를 '통관 완료'(Status)로 업데이트
# ─────────────────────────────────────────────────────────────

NOTION_TOKEN  = os.getenv("NOTION_TOKEN")
LEDGER_DB_ID  = os.getenv("LEDGER_DB_ID")   # ← GitHub Secrets에 추가 필요

NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

UA_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123 Safari/537.36"
    )
}


# ── 장부 DB 조회 ──────────────────────────────────────────────
def get_tracking_items():
    """
    장부 DB에서 배송상태 = 'Not started' 인 항목만 조회
    (통관 완료 / 국내 배송 상태는 건너뜀)
    """
    url  = f"https://api.notion.com/v1/databases/{LEDGER_DB_ID}/query"
    body = {
        "page_size": 100,
        "filter": {
            "property": "배송상태",
            "status": {"equals": "Not started"}
        }
    }

    items   = []
    has_more = True
    cursor   = None

    while has_more:
        if cursor:
            body["start_cursor"] = cursor

        response = requests.post(url, headers=NOTION_HEADERS, json=body)
        print("[DEBUG] Notion status:", response.status_code)

        try:
            data = response.json()
        except Exception as e:
            print("[DEBUG] Notion 응답 JSON 파싱 실패:", e, response.text)
            break

        if "results" not in data:
            print("[DEBUG] Notion 응답에 'results' 키가 없음:", data)
            break

        for result in data["results"]:
            props   = result["properties"]
            page_id = result["id"]

            # 이름: Title 타입
            name_arr  = props.get("이름", {}).get("title", [])
            name_text = name_arr[0]["plain_text"] if name_arr else ""

            # 배송조회링크: URL 타입
            raw = (props.get("배송조회링크", {}).get("url") or "").strip()

            if not raw:
                continue  # 링크 없으면 체크 불가

            parsed      = urlparse(raw)
            query_params = parse_qs(parsed.query)
            customs_code = query_params.get("code",    [""])[0]
            invoice_no   = query_params.get("invoice", [""])[0]

            if customs_code and invoice_no:
                items.append({
                    "type":     "asap",
                    "code":     customs_code,
                    "invoice":  invoice_no,
                    "page_id":  page_id,
                    "name":     name_text,
                    "raw":      raw,
                })
            else:
                print(f"[⚠️ URL 형식 불명] {name_text} / {raw}")

        has_more = data.get("has_more", False)
        cursor   = data.get("next_cursor")

    return items


# ── ASAP 유니패스 통관 상태 조회 ──────────────────────────────
def check_unipass_status_asap(code, invoice):
    """기존 unipass_check.py 와 동일한 로직"""
    url      = f"https://asap-china.com/guide/unipass_delivery.php?code={code}&invoice={invoice}"
    response = requests.get(url, headers=UA_HEADERS, timeout=20)
    soup     = BeautifulSoup(response.text, "html.parser")

    tables = soup.find_all("table")
    if len(tables) < 2:
        return []

    table = tables[1]
    rows  = table.find_all("tr")[1:]  # 헤더 제외

    steps = []
    for row in rows:
        tds = row.find_all("td")
        if len(tds) > 2:
            step_text = tds[1].get_text(strip=True)
            time_text = tds[2].get_text(strip=True)
            steps.append({"step": step_text, "time": time_text})

    return steps


# ── 장부 DB 배송상태 업데이트 (Status 타입) ───────────────────
def update_delivery_status(page_id, status_name):
    """
    배송상태 칼럼(Status 타입)을 지정된 값으로 업데이트
    예: '통관 완료', '국내 배송'
    """
    url     = f"https://api.notion.com/v1/pages/{page_id}"
    payload = {
        "properties": {
            "배송상태": {
                "status": {"name": status_name}
            }
        }
    }

    resp = requests.patch(url, headers=NOTION_HEADERS, json=payload)
    if resp.status_code == 200:
        print(f"[🟢 배송상태 업데이트] {page_id} → {status_name}")
    else:
        print(f"[⚠️ 업데이트 실패] {resp.status_code} / {resp.text}")


# ── 메인 ──────────────────────────────────────────────────────
def main():
    print("[🚀 장부 DB 유니패스 자동 추적 시작]\n")

    if not NOTION_TOKEN or not LEDGER_DB_ID:
        print("[❌ 환경변수 누락] NOTION_TOKEN 또는 LEDGER_DB_ID 가 설정되지 않았습니다.")
        return

    items     = get_tracking_items()
    any_found = False

    print(f"[📋 조회 대상: {len(items)}건]\n")

    for it in items:
        name    = it.get("name", "")
        invoice = it.get("invoice", "")
        code    = it.get("code", "")

        print(f"[🔍 검사 중] {invoice} / {name}")
        steps = check_unipass_status_asap(code, invoice)

        if not steps:
            print(f"  └ 처리단계 없음 (운송 중 또는 조회 불가)\n")
            continue

        # 통관목록심사완료 단계 확인
        target = next((s for s in steps if s["step"] == "통관목록심사완료"), None)
        if target:
            processed_at = target["time"]
            print(f"  └ [🎉 통관목록심사완료] {processed_at}")
            update_delivery_status(it["page_id"], "통관 완료")
            any_found = True
        else:
            latest = steps[-1] if steps else {}
            print(f"  └ 최근 단계: {latest.get('step', '?')} / {latest.get('time', '?')}\n")

    if not any_found:
        print("\n[ℹ️ 아직 통관 완료 없음]")
    else:
        print("\n[✅ 완료]")


if __name__ == "__main__":
    main()
