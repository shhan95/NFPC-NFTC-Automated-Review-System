import json, re
from datetime import datetime, timezone, timedelta
import requests
from bs4 import BeautifulSoup

KST = timezone(timedelta(hours=9))
TODAY = datetime.now(KST).strftime("%Y-%m-%d")

def load(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default

def save(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def fetch_meta(url: str) -> dict:
    """
    법제처/소방청 페이지는 형태가 다양함.
    여기서는 가능한 범위에서 '발령일/시행일/고시번호/개정유형'처럼
    메타를 문자열 패턴으로 최대한 뽑는 방식.
    """
    try:
        r = requests.get(url, timeout=25, headers={"User-Agent":"Mozilla/5.0"})
        r.raise_for_status()
        html = r.text
    except Exception as e:
        return {"error": str(e)}

    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(" ", strip=True)

    def pick(pats):
        for p in pats:
            m = re.search(p, text)
            if m:
                return m.group(1)
        return None

    notice = pick([r"(소방청고시\s*제[\d\-]+호)"])
    announce = pick([r"발령일\s*[:：]?\s*(\d{4}\.\d{1,2}\.\d{1,2})",
                     r"발령\s*[:：]?\s*(\d{4}\.\d{1,2}\.\d{1,2})"])
    effective = pick([r"시행일\s*[:：]?\s*(\d{4}\.\d{1,2}\.\d{1,2})",
                      r"시행\s*[:：]?\s*(\d{4}\.\d{1,2}\.\d{1,2})"])
    revtype = pick([r"(일부개정|전부개정|제정|폐지|타법개정)"])

    meta = {
        "noticeNo": notice,
        "announceDate": announce,
        "effectiveDate": effective,
        "revisionType": revtype,
        "checkedAt": TODAY,
        "sourceUrl": url
    }
    return meta

def main():
    nfpc = load("standards_nfpc.json", {"items":[]})
    nftc = load("standards_nftc.json", {"items":[]})
    snap = load("snapshot.json", {"nfpc":{}, "nftc":{}})
    data = load("data.json", {"lastRun": None, "records": []})

    changes = []

    # NFPC
    for item in nfpc.get("items", []):
        code, url = item.get("code"), item.get("url")
        if not code or not url: 
            continue
        prev = snap["nfpc"].get(code, {})
        cur = fetch_meta(url)
        snap["nfpc"][code] = {**prev, **cur, "title": item.get("title"), "url": url}
        # 변경 감지: 발령일/시행일/개정유형/고시번호 중 하나라도 바뀌면 변경으로 처리
        keys = ["noticeNo","announceDate","effectiveDate","revisionType"]
        if all(prev.get(k) == snap["nfpc"][code].get(k) for k in keys):
            continue
        if prev:  # 첫 수집은 변경으로 안 잡고 싶으면 prev 존재할 때만
            changes.append({
                "code": code,
                "title": item.get("title"),
                "noticeNo": snap["nfpc"][code].get("noticeNo"),
                "announceDate": snap["nfpc"][code].get("announceDate"),
                "effectiveDate": snap["nfpc"][code].get("effectiveDate"),
                "reason": "자동 감지: 발령/시행/개정유형 등 메타 변경 확인(원문 제·개정이유 및 신구비교 확인 필요)",
                "diff": [],
                "supplementary": "부칙/경과규정은 원문 확인",
                "impact": [
                    "설계: 시행일 기준 적용(도서/시방서에 적용기준 명시)",
                    "시공: 자재/설비 선정 시 개정기준 충족 여부 확인",
                    "유지관리: 점검대장에 적용기준/이력 기록"
                ],
                "refs": [{"label":"원문", "url": url}]
            })

    # NFTC
    for item in nftc.get("items", []):
        code, url = item.get("code"), item.get("url")
        if not code or not url:
            continue
        prev = snap["nftc"].get(code, {})
        cur = fetch_meta(url)
        snap["nftc"][code] = {**prev, **cur, "title": item.get("title"), "url": url}
        keys = ["noticeNo","announceDate","effectiveDate","revisionType"]
        if all(prev.get(k) == snap["nftc"][code].get(k) for k in keys):
            continue
        if prev:
            changes.append({
                "code": code,
                "title": item.get("title"),
                "noticeNo": snap["nftc"][code].get("noticeNo"),
                "announceDate": snap["nftc"][code].get("announceDate"),
                "effectiveDate": snap["nftc"][code].get("effectiveDate"),
                "reason": "자동 감지: 발령/시행/개정유형 등 메타 변경 확인(원문 제·개정이유 및 신구비교 확인 필요)",
                "diff": [],
                "supplementary": "부칙/경과규정은 원문 확인",
                "impact": [
                    "설계: 시행일 기준 적용(도서/시방서에 적용기준 명시)",
                    "시공: 자재/설비 선정 시 개정기준 충족 여부 확인",
                    "유지관리: 점검대장에 적용기준/이력 기록"
                ],
                "refs": [{"label":"원문", "url": url}]
            })

    # 로그 기록
    data["lastRun"] = TODAY
    if changes:
        rec = {
            "id": TODAY,
            "date": TODAY,
            "scope": "NFPC / NFTC (법제처·소방청)",
            "result": "변경 있음",
            "summary": f"자동 감지: {len(changes)}건 메타 변경(원문 확인 권장)",
            "changes": changes,
            "refs": []
        }
    else:
        rec = {
            "id": TODAY,
            "date": TODAY,
            "scope": "NFPC / NFTC (법제처·소방청)",
            "result": "변경 없음",
            "summary": "전일/전주 대비 신규 발령·개정 메타 변경 없음",
            "refs": []
        }

    # 중복 방지: 같은 날짜 기록 있으면 교체
    data["records"] = [r for r in data.get("records", []) if r.get("date") != TODAY]
    data["records"].insert(0, rec)

    save("snapshot.json", snap)
    save("data.json", data)

if __name__ == "__main__":
    main()
