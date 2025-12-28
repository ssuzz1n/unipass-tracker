import os
import re
import requests
from datetime import datetime
from urllib.parse import urlparse, parse_qs

# =====================
# 기본 설정
# =====================
HEADERS = {
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,ko;q=0.7",
    "referer": "https://www.taobao.com/",
}

TAOBAO_COOKIE = os.getenv("TAOBAO_COOKIE")
if TAOBAO_COOKIE:
    HEADERS["cookie"] = TAOBAO_COOKIE

DEBUG_DIR = "debug_html"
os.makedirs(DEBUG_DIR, exist_ok=True)

BLOCK_SIGNALS = [
    "login.taobao.com",
    "sec.taobao.com",
    "verify",
    "验证码",
    "滑块",
    "访问受限",
    "请登录",
    "安全验证",
]

# =====================
# 유틸
# =====================
def extract_item_id(url: str) -> str | None:
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    if "id" in qs:
        return qs["id"][0]
    return None


def is_blocked(html: str) -> list[str]:
    return [s for s in BLOCK_SIGNALS if s in html]


# =====================
# 메인 fetch + 디버깅
# =====================
def fetch_and_debug(url: str, index: int):
    print(f"\n[FETCH] {url}")
    resp = requests.get(url, headers=HEADERS, timeout=15)

    print(f"[DEBUG] status_code = {resp.status_code}")
    print(f"[DEBUG] final_url  = {resp.url}")

    html = resp.text

    # 1️⃣ HTML 앞부분 출력
    head = html[:800].replace("\n", "\\n")
    print(f"[DEBUG] html_head = {head}")

    # 2️⃣ 차단/로그인 신호 체크
    hits = is_blocked(html)
    print(f"[DEBUG] block_signals = {hits}")

    # 3️⃣ ICE_APP_CONTEXT 존재 여부
    has_ctx = "__ICE_APP_CONTEXT__" in html
    print(f"[DEBUG] has_ICE_APP_CONTEXT = {has_ctx}")

    # 4️⃣ 실패 시 HTML 저장
    if not has_ctx:
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        path = f"{DEBUG_DIR}/taobao_{index}_{ts}.html"
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"[DEBUG] saved html → {path}")

    return has_ctx, hits


# =====================
# 실행부
# =====================
def main():
    urls = [
        "https://item.taobao.com/item.htm?id=968090853112",
        "https://item.taobao.com/item.htm?id=948568525004",
    ]

    print(f"[INFO] pages loaded: {len(urls)}")

    for i, url in enumerate(urls, 1):
        ok, signals = fetch_and_debug(url, i)

        if not ok:
            if signals:
                print("[RESULT] ❌ 로그인/차단 페이지로 판단됨")
            else:
                print("[RESULT] ❌ ICE_APP_CONTEXT 없음 (구조변경 or CSR 가능)")
        else:
            print("[RESULT] ✅ ICE_APP_CONTEXT 존재 (파싱 가능 상태)")


if __name__ == "__main__":
    main()
