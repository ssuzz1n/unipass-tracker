import os
import re
import json
import time
import base64
import gzip
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, List, Tuple

import requests


NOTION_TOKEN = os.getenv("NOTION_TOKEN")
TAOBAO_NOTION_DB_ID = os.getenv("TAOBAO_NOTION_DB_ID")

NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

# 타오바오가 봇 차단을 자주 해서 UA는 최대한 "사람"처럼
DEFAULT_UA = os.getenv(
    "TAOBAO_USER_AGENT",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

SESSION = requests.Session()
SESSION.headers.update(
    {
        "User-Agent": DEFAULT_UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,ko;q=0.7",
        "Connection": "keep-alive",
    }
)

# Notion rich_text 조각당 2000자 제한 대응
NOTION_TEXT_CHUNK = 1900


def now_kst_str() -> str:
    # KST(UTC+9) 문자열
    kst = timezone.utc
    # 깔끔하게: UTC에서 +9 변환
    dt = datetime.utcnow().replace(tzinfo=timezone.utc)
    dt_kst = dt.astimezone(timezone.utc).replace(tzinfo=timezone.utc)
    # 위 줄은 환경마다 헷갈릴 수 있어서 그냥 표시용은 UTC로 두고, 뒤에 "UTC" 표기해도 됨.
    # 찡이 원하면 KST로 바꿔줄게. 일단 GitHub 로그용은 UTC가 안정적.
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


def chunk_text_for_notion(s: str) -> List[Dict[str, Any]]:
    chunks = []
    for i in range(0, len(s), NOTION_TEXT_CHUNK):
        chunks.append({"type": "text", "text": {"content": s[i : i + NOTION_TEXT_CHUNK]}})
    return chunks or [{"type": "text", "text": {"content": ""}}]


def b64_gzip_encode(obj: Any) -> str:
    raw = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    compressed = gzip.compress(raw, compresslevel=9)
    return base64.b64encode(compressed).decode("ascii")


def b64_gzip_decode(s: str) -> Any:
    data = base64.b64decode(s.encode("ascii"))
    raw = gzip.decompress(data).decode("utf-8")
    return json.loads(raw)


def sha1_of_obj(obj: Any) -> str:
    raw = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha1(raw).hexdigest()


def notion_query_all_pages(db_id: str) -> List[Dict[str, Any]]:
    url = f"https://api.notion.com/v1/databases/{db_id}/query"
    payload = {"page_size": 100}
    results = []
    while True:
        r = requests.post(url, headers=NOTION_HEADERS, json=payload, timeout=30)
        r.raise_for_status()
        data = r.json()
        results.extend(data.get("results", []))
        if not data.get("has_more"):
            break
        payload["start_cursor"] = data.get("next_cursor")
    return results


def notion_update_page(page_id: str, properties: Dict[str, Any]) -> None:
    url = f"https://api.notion.com/v1/pages/{page_id}"
    r = requests.patch(url, headers=NOTION_HEADERS, json={"properties": properties}, timeout=30)
    r.raise_for_status()


def extract_ice_app_context(html: str) -> Dict[str, Any]:
    """
    HTML에서 window.__ICE_APP_CONTEXT__를 만드는 var b = {...} 부분을 뽑아서 JSON 파싱.
    """
    # var b = {...};for (var k in a) {b[k] = a[k]}window.__ICE_APP_CONTEXT__=b;
    m = re.search(r"var\s+b\s*=\s*(\{.*?\});\s*for\s*\(var\s+k\s+in\s+a\)", html, re.S)
    if not m:
        raise ValueError("ICE_APP_CONTEXT(var b=...) 부분을 찾지 못함 (차단/구조변경 가능)")
    blob = m.group(1)

    # 이 blob은 JSON 호환 형태(큰따옴표)라서 보통 json.loads 가능
    try:
        return json.loads(blob)
    except json.JSONDecodeError as e:
        # 가끔 JS에서 특수문자 섞이면 여기서 터질 수 있음
        raise ValueError(f"ICE_APP_CONTEXT JSON 파싱 실패: {e}")


def parse_taobao_sku_snapshot(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """
    ctx['loaderData']['home']['data']['res'] 하위에서 skuBase/skuCore를 읽어
    조합별 재고 상태 스냅샷을 만든다.
    """
    res = ctx["loaderData"]["home"]["data"]["res"]
    item = res.get("item", {})
    sku_base = res.get("skuBase", {})
    sku_core = res.get("skuCore", {})
    sku2info = sku_core.get("sku2info", {})

    # 옵션 pid/vid -> 이름 매핑
    pid_vid_to_name: Dict[Tuple[str, str], str] = {}
    pid_to_propname: Dict[str, str] = {}

    for prop in sku_base.get("props", []) or []:
        pid = str(prop.get("pid", ""))
        pid_to_propname[pid] = prop.get("name", pid)
        value_map = prop.get("valueMap") or {}
        for vid, vobj in value_map.items():
            pid_vid_to_name[(pid, str(vid))] = vobj.get("name", str(vid))

    # 조합 목록
    combos = []
    for sk in sku_base.get("skus", []) or []:
        prop_path = sk.get("propPath", "")
        sku_id = str(sk.get("skuId", ""))

        # propPath -> ["pid:vid", ...]
        parts = [p for p in prop_path.split(";") if p.strip()]
        readable_parts = []
        for p in parts:
            if ":" not in p:
                continue
            pid, vid = p.split(":", 1)
            prop_name = pid_to_propname.get(pid, pid)
            val_name = pid_vid_to_name.get((pid, vid), vid)
            readable_parts.append({"pid": pid, "prop": prop_name, "vid": vid, "value": val_name})

        info = sku2info.get(sku_id, {}) or {}
        combos.append(
            {
                "skuId": sku_id,
                "propPath": prop_path,
                "options": readable_parts,
                "quantity": info.get("quantity"),
                "quantityText": info.get("quantityText"),
            }
        )

    # skuId별 빠른 조회용 dict도 같이 저장
    by_sku = {c["skuId"]: c for c in combos}

    snapshot = {
        "itemId": str(item.get("itemId", "")),
        "title": item.get("title", ""),
        "fetchedAt": now_kst_str(),
        "combos": combos,
        "bySkuId": by_sku,  # 비교 편하게
    }
    return snapshot


def classify_stock_state(quantity_text: str, quantity: Any) -> str:
    """
    타오바오 표기 기반으로 상태 통일.
    """
    qt = (quantity_text or "").strip()
    if qt in ("无货", "缺货"):
        return "OOS"  # out of stock
    if qt in ("即将售罄",):
        return "LOW"
    # quantity가 숫자고 0이면 OOS
    try:
        if quantity is not None and int(quantity) == 0:
            return "OOS"
    except Exception:
        pass
    return "IN"


def diff_snapshots(prev: Dict[str, Any], cur: Dict[str, Any]) -> Dict[str, Any]:
    """
    prev/cur combo 비교해서 변화만 요약.
    """
    prev_map = prev.get("bySkuId", {}) or {}
    cur_map = cur.get("bySkuId", {}) or {}

    changed = []
    newly_oos = []
    restocked = []
    newly_low = []

    all_sku_ids = set(prev_map.keys()) | set(cur_map.keys())

    def combo_label(combo: Dict[str, Any]) -> str:
        # "색:검정 / 사이즈:A6 / ..." 형태
        parts = [f"{o['prop']}:{o['value']}" for o in combo.get("options", [])]
        return " / ".join(parts) if parts else f"skuId={combo.get('skuId')}"

    for sku_id in sorted(all_sku_ids):
        p = prev_map.get(sku_id)
        c = cur_map.get(sku_id)
        if not p or not c:
            # 옵션 추가/삭제 같은 구조 변경
            changed.append(f"옵션구조 변경 감지: skuId {sku_id} (추가/삭제)")
            continue

        p_state = classify_stock_state(p.get("quantityText"), p.get("quantity"))
        c_state = classify_stock_state(c.get("quantityText"), c.get("quantity"))

        if p_state != c_state:
            label = combo_label(c)
            changed.append(f"{label}: {p_state} → {c_state}")
            if p_state != "OOS" and c_state == "OOS":
                newly_oos.append(label)
            if p_state == "OOS" and c_state != "OOS":
                restocked.append(label)
            if c_state == "LOW" and p_state != "LOW":
                newly_low.append(label)

    return {
        "changed_lines": changed,
        "newly_oos": newly_oos,
        "restocked": restocked,
        "newly_low": newly_low,
        "changed_count": len(changed),
    }


def fetch_taobao_html(url: str) -> str:
    # PC 상세 링크만 저장한다 했으니, url에서 id만 뽑아서 표준 detail url로 맞춰도 좋음
    # (찡이 저장한 링크가 제각각이어도 안정적으로)
    item_id = None
    m = re.search(r"(?:id=|itemId=)(\d{8,})", url)
    if m:
        item_id = m.group(1)
    if item_id and "taobao.com" in url:
        url = f"https://item.taobao.com/item.htm?id={item_id}"

    r = SESSION.get(url, timeout=30)
    # 차단되면 여기서 로그인/검증페이지가 올 수 있음
    r.raise_for_status()
    return r.text


def main():
    if not NOTION_TOKEN or not TAOBAO_NOTION_DB_ID:
        raise RuntimeError("NOTION_TOKEN / TAOBAO_NOTION_DB_ID 환경변수가 필요함")

    pages = notion_query_all_pages(TAOBAO_NOTION_DB_ID)
    print(f"[INFO] pages loaded: {len(pages)}")

    for idx, page in enumerate(pages, start=1):
        page_id = page["id"]
        props = page.get("properties", {})

        # 타오바오 링크 property 이름은 너 DB에 맞춰 바꾸면 됨
        taobao_url = None
        if "타오바오 링크" in props and props["타오바오 링크"].get("type") == "url":
            taobao_url = props["타오바오 링크"].get("url")

        if not taobao_url:
            continue

        print(f"\n[{idx}/{len(pages)}] Fetch: {taobao_url}")

        # 이전 스냅샷 읽기
        prev_b64 = ""
        if "taobao_snapshot_b64" in props and props["taobao_snapshot_b64"]["type"] == "rich_text":
            rt = props["taobao_snapshot_b64"].get("rich_text", [])
            prev_b64 = "".join([x.get("plain_text", "") for x in rt])

        try:
            html = fetch_taobao_html(taobao_url)
            ctx = extract_ice_app_context(html)
            cur_snapshot = parse_taobao_sku_snapshot(ctx)
        except Exception as e:
            # 차단/구조변경 시 에러를 변화감지요약에 남겨주면 운영에 도움됨
            notion_update_page(
                page_id,
                {
                    "변화감지요약": {
                        "rich_text": chunk_text_for_notion(f"[에러] {now_kst_str()} - {str(e)[:800]}")
                    }
                },
            )
            print(f"[WARN] failed: {e}")
            time.sleep(1.0)
            continue

        cur_hash = sha1_of_obj(cur_snapshot)

        # 이전 해시가 있으면 먼저 비교해서 완전 동일하면 스킵
        prev_hash = ""
        if "taobao_snapshot_hash" in props:
            t = props["taobao_snapshot_hash"]
            if t.get("type") == "rich_text":
                prev_hash = "".join([x.get("plain_text", "") for x in t.get("rich_text", [])])
            elif t.get("type") == "text":
                prev_hash = t.get("text", {}).get("content", "")

        summary_text = ""
        if prev_b64:
            try:
                prev_snapshot = b64_gzip_decode(prev_b64)
                diff = diff_snapshots(prev_snapshot, cur_snapshot)
                if diff["changed_count"] > 0:
                    # 너무 길어지면 상위 30개까지만 보여주고 "외 N개" 처리
                    lines = diff["changed_lines"]
                    head = lines[:30]
                    tail_n = max(0, len(lines) - len(head))

                    summary_text = (
                        f"✅ 변화 감지 ({now_kst_str()})\n"
                        f"- 변경 {diff['changed_count']}건\n"
                        f"- 신규 품절 {len(diff['newly_oos'])} / 재입고 {len(diff['restocked'])} / 품절임박 {len(diff['newly_low'])}\n\n"
                        + "\n".join([f"- {x}" for x in head])
                    )
                    if tail_n:
                        summary_text += f"\n- ... 외 {tail_n}건"
            except Exception as e:
                summary_text = f"[경고] 이전 스냅샷 파싱 실패({now_kst_str()}): {str(e)[:300]}"

        # 스냅샷 저장(항상 최신으로 업데이트)
        cur_b64 = b64_gzip_encode(cur_snapshot)

        update_props = {
            "taobao_snapshot_b64": {"rich_text": chunk_text_for_notion(cur_b64)},
            "taobao_snapshot_hash": {"rich_text": chunk_text_for_notion(cur_hash)},
        }

        # 변화가 있을 때만 변화감지요약 갱신 (없으면 건드리지 않음)
        if summary_text:
            update_props["변화감지요약"] = {"rich_text": chunk_text_for_notion(summary_text)}

        notion_update_page(page_id, update_props)
        print("[OK] updated")

        # 400개면 너무 빨리 돌리면 막힐 수 있어서 텀 주기
        time.sleep(1.2)


if __name__ == "__main__":
    main()
