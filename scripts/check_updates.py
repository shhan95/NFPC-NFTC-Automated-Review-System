import os, json, hashlib, urllib.parse
from datetime import datetime, timezone, timedelta
import requests

KST = timezone(timedelta(hours=9))
TODAY = datetime.now(KST).strftime("%Y-%m-%d")

LAWGO_OC = os.getenv("LAWGO_OC", "").strip()
if not LAWGO_OC:
    raise SystemExit("ENV LAWGO_OC is empty. Set GitHub Secret 'LAWGO_OC' to your 법제처 OPEN API OC value (email id).")

LAW_SEARCH = "https://www.law.go.kr/DRF/lawSearch.do"
LAW_SERVICE = "https://www.law.go.kr/DRF/lawService.do"

def load(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default

def save(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def ymd_int_to_dot(v):
    # 20250202 -> 2025.02.02
    if v is None:
        return None
    s = str(v).strip()
    if not s.isdigit() or len(s) != 8:
        return s
    return f"{s[0:4]}.{s[4:6]}.{s[6:8]}"

def sha256_text(t: str) -> str:
    return hashlib.sha256((t or "").encode("utf-8")).hexdigest()

def lawgo_search(query: str, knd: int = 3, display: int = 20):
    params = {
        "OC": LAWGO_OC,
        "target": "admrul",
        "type": "JSON",
        "query": query,
        "knd": str(knd),
        "display": str(display),
        "sort": "ddes"  # 발령일자 내림차순
    }
    r = requests.get(LAW_SEARCH, params=params, timeout=30)
    r.raise_for_status()
    return r.json()

def lawgo_detail(admrul_id: str):
    params = {
        "OC": LAWGO_OC,
        "target": "admrul",
        "type": "JSON",
        "ID": str(admrul_id)
    }
    r = requests.get(LAW_SERVICE, params=params, timeout=30)
    r.raise_for_status()
    return r.json()

def pick_best_item(items, org_name="소방청"):
    # 우선: 소관부처명=소방청, 행정규칙종류=고시
    # 그 다음: 제명이 가장 길게/정확히 일치하는 것(간단 점수)
    best = None
    best_score = -1
    for it in items:
        org = (it.get("소관부처명") or it.get("소관부처") or "")
        kind = (it.get("행정규칙종류") or "")
        score = 0
        if org_name and org_name in org:
            score += 100
        if "고시" in kind:
            score += 20
        # 최신 발령일 가산
        prml = it.get("발령일자")
        if prml:
            score += 1
        if score > best_score:
            best, best_score = it, score
    return best

def build_snapshot_entry(std_item, tab_key: str, prev_entry: dict):
    # 1) 검색
    search_json = lawgo_search(std_item.get("query") or std_item["title"], knd=int(std_item.get("knd",3)))
    # 응답 구조: { "admrul": [ ... ] } 또는 { "admrul":[...] } 등 변동 가능
    items = None
    for k in ("admrul", "Admrul", "admruls"):
        if k in search_json:
            items = search_json[k]
            break
    if items is None:
        # 일부 응답은 "법령" 같은 상위 키 밑에 있을 수 있음
        items = search_json.get("행정규칙", None)

    items = items or []
    best = pick_best_item(items, org_name=std_item.get("orgName","소방청"))
    if not best:
        return {**prev_entry, "checkedAt": TODAY, "error": "검색 결과 없음"}

    adm_id = best.get("행정규칙일련번호") or best.get("일련번호") or best.get("id") or best.get("ID")
    if not adm_id:
        return {**prev_entry, "checkedAt": TODAY, "error": "일련번호 추출 실패"}

    # 2) 상세
    det = lawgo_detail(adm_id)
    # 상세 구조: {"행정규칙": {...}} 또는 {"admrul": {...}}
    payload = det.get("행정규칙") or det.get("admrul") or det
    notice_no = payload.get("발령번호") or payload.get("발령번호string") or payload.get("발령번호 ")
    announce = ymd_int_to_dot(payload.get("발령일자"))
    effective = payload.get("시행일자")
    # 시행일자가 YYYYMMDD 형태면 변환
    effective = ymd_int_to_dot(effective) if isinstance(effective, (int,str)) else effective
    rev = payload.get("제개정구분명")
    org = payload.get("소관부처명")
    name = payload.get("행정규칙명") or std_item.get("title")
    # 본문/부칙/별표 해시로 변경 감지 강화(원문 전문 저장은 피함)
    body_hash = sha256_text(payload.get("조문내용") or "")
    add_hash = sha256_text((payload.get("부칙내용") or "") + (payload.get("별표내용") or ""))

    # 법제처 원문 링크: 목록 API에서 제공하는 상세링크가 있을 수 있음
    html_url = best.get("행정규칙상세링크") or best.get("상세링크") or ""
    # 없으면 law.go.kr에서 ID 기반 링크를 만들어두고(사용자 클릭용)
    if not html_url:
        # DRF 상세(JSON)이 아닌 웹 상세는 변동될 수 있어, 최소한 DRF HTML 링크 제공
        html_url = f"{LAW_SERVICE}?OC={urllib.parse.quote(LAWGO_OC)}&target=admrul&ID={adm_id}&type=HTML"

    return {
        "code": std_item["code"],
        "title": std_item.get("title"),
        "checkedAt": TODAY,
        "lawgoId": str(adm_id),
        "noticeNo": notice_no,
        "announceDate": announce,
        "effectiveDate": effective,
        "revisionType": rev,
        "orgName": org,
        "ruleName": name,
        "htmlUrl": html_url,
        "bodyHash": body_hash,
        "suppHash": add_hash
    }

def detect_change(prev: dict, cur: dict):
    if not prev:
        return False, []
    keys = ["noticeNo","announceDate","effectiveDate","revisionType","bodyHash","suppHash"]
    diffs=[]
    for k in keys:
        if (prev.get(k) or "") != (cur.get(k) or ""):
            diffs.append(k)
    return (len(diffs)>0), diffs

def main():
    nfpc = load("standards_nfpc.json", {"items":[]})
    nftc = load("standards_nftc.json", {"items":[]})
    snap = load("snapshot.json", {"nfpc":{}, "nftc":{}})
    data = load("data.json", {"lastRun": None, "records": []})

    changes = []

    for tab_key, std in (("nfpc", nfpc), ("nftc", nftc)):
        for item in std.get("items", []):
            code = item.get("code")
            if not code:
                continue
            prev = (snap.get(tab_key, {}) or {}).get(code, {})
            cur = build_snapshot_entry(item, tab_key, prev)
            snap.setdefault(tab_key, {})[code] = cur

            changed, diff_keys = detect_change(prev, cur)
            if changed:
                changes.append({
                    "code": code,
                    "title": item.get("title"),
                    "noticeNo": cur.get("noticeNo"),
                    "announceDate": cur.get("announceDate"),
                    "effectiveDate": cur.get("effectiveDate"),
                    "reason": f"자동 감지: 메타/본문 해시 변경({', '.join(diff_keys)})",
                    "diff": [],  # 조문·별표 신구대비는 별도 API 또는 수동 확인 영역
                    "supplementary": "부칙/경과규정은 원문 확인",
                    "impact": [
                        "설계: 시행일 기준 적용(도서·시방서에 적용기준 명시)",
                        "시공: 자재/설비 선정 시 개정기준 충족 여부 확인",
                        "유지관리: 점검대장에 적용기준/이력 기록"
                    ],
                    "refs": [{"label":"법제처(원문/DRF)", "url": cur.get("htmlUrl","")}]
                })

    data["lastRun"] = TODAY

    if changes:
        rec = {
            "id": TODAY,
            "date": TODAY,
            "scope": "NFPC / NFTC (법제처 OPEN API: 행정규칙)",
            "result": "변경 있음",
            "summary": f"자동 감지: {len(changes)}건 변경(원문 확인 권장)",
            "changes": changes,
            "refs": []
        }
    else:
        rec = {
            "id": TODAY,
            "date": TODAY,
            "scope": "NFPC / NFTC (법제처 OPEN API: 행정규칙)",
            "result": "변경 없음",
            "summary": "전일 대비 변경 감지 없음",
            "refs": []
        }

    # 같은 날짜 있으면 교체
    data["records"] = [r for r in data.get("records", []) if r.get("date") != TODAY]
    data["records"].insert(0, rec)

    save("snapshot.json", snap)
    save("data.json", data)

if __name__ == "__main__":
    main()
