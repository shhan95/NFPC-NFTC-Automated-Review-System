 (cd "$(git rev-parse --show-toplevel)" && git apply --3way <<'EOF' 
diff --git a/scripts/check_updates.py b/scripts/check_updates.py
index fb65a9fffd4fd32ecc71990e346d47a4885b6360..f7905e1ef0898d5d21580c8b3c2bce68608d5270 100644
--- a/scripts/check_updates.py
+++ b/scripts/check_updates.py
@@ -1,384 +1,440 @@
-import os, json, hashlib, urllib.parse, time, random
-from datetime import datetime, timezone, timedelta
-from typing import Any, Dict, Tuple, Optional
+import hashlib
+import json
+import os
+import random
+import time
+import urllib.parse
+from datetime import datetime, timedelta, timezone
+from typing import Any, Dict, List, Optional, Tuple
 
 import requests
 
 
 # =====================
 # Config
 # =====================
 KST = timezone(timedelta(hours=9))
 TODAY = datetime.now(KST).strftime("%Y-%m-%d")
 
 LAWGO_OC = os.getenv("LAWGO_OC", "").strip()
 if not LAWGO_OC:
-    raise SystemExit("ENV LAWGO_OC is empty. Set GitHub Secret 'LAWGO_OC' to your 법제처 OPEN API OC value (email id).")
+    raise SystemExit(
+        "ENV LAWGO_OC is empty. Set GitHub Secret 'LAWGO_OC' to your 법제처 OPEN API OC value (email id)."
+    )
 
-# ✅ https 고정
 LAW_SEARCH = "https://www.law.go.kr/DRF/lawSearch.do"
 LAW_SERVICE = "https://www.law.go.kr/DRF/lawService.do"
 
 TIMEOUT = 30
 MAX_RETRIES = 4
 
 
 # =====================
 # Helpers (file I/O)
 # =====================
 def load(path: str, default: Any) -> Any:
     try:
         with open(path, "r", encoding="utf-8") as f:
             return json.load(f)
     except FileNotFoundError:
         return default
 
+
 def save(path: str, obj: Any) -> None:
     with open(path, "w", encoding="utf-8") as f:
         json.dump(obj, f, ensure_ascii=False, indent=2)
 
+
 def ymd_int_to_dot(v: Any) -> Any:
     if v is None:
         return None
     s = str(v).strip()
     if not s.isdigit() or len(s) != 8:
         return s
     return f"{s[0:4]}.{s[4:6]}.{s[6:8]}"
 
+
 def sha256_text(t: str) -> str:
     return hashlib.sha256((t or "").encode("utf-8")).hexdigest()
 
 
 # =====================
 # HTTP (robust)
 # =====================
-def _request_json(url: str, params: Dict[str, str]) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
+def _backoff(attempt: int) -> None:
+    # 0.6s, 1.2s, 2.4s... + jitter
+    base = 0.6 * (2 ** (attempt - 1))
+    time.sleep(base + random.random() * 0.4)
+
+
+def _request_json(
+    url: str,
+    params: Dict[str, str],
+    session: requests.Session,
+) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
     """
     Returns: (json_payload, error_info)
       - json_payload: parsed dict if success
       - error_info: dict with debug fields if failed (no secret exposure)
     """
-    session = requests.Session()
-    last_err = None
+    last_err: Optional[Dict[str, Any]] = None
 
     for attempt in range(1, MAX_RETRIES + 1):
         try:
-            r = session.get(url, params=params, timeout=TIMEOUT, allow_redirects=True)
-            ct = (r.headers.get("Content-Type") or "").lower()
-            text = r.text or ""
+            response = session.get(url, params=params, timeout=TIMEOUT, allow_redirects=True)
+            content_type = (response.headers.get("Content-Type") or "").lower()
+            text = response.text or ""
             head = text[:200].replace("\n", " ")
 
-            # status not ok
-            if r.status_code != 200:
+            if response.status_code != 200:
                 last_err = {
                     "kind": "http_error",
-                    "status": r.status_code,
-                    "contentType": ct,
+                    "status": response.status_code,
+                    "contentType": content_type,
                     "head": head,
                     "url": url,
                 }
-                # 429/5xx는 재시도 가치 큼
-                if r.status_code in (429, 500, 502, 503, 504):
+                if response.status_code in (429, 500, 502, 503, 504):
                     _backoff(attempt)
                     continue
                 return None, last_err
 
-            # content type not json (HTML/empty/blocked)
-            if "json" not in ct:
-                # 빈 응답도 여기로 들어옴
+            if "json" not in content_type:
                 last_err = {
                     "kind": "not_json",
-                    "status": r.status_code,
-                    "contentType": ct,
+                    "status": response.status_code,
+                    "contentType": content_type,
                     "head": head,
                     "url": url,
                 }
-                # 일시 오류 가능 → 재시도
                 _backoff(attempt)
                 continue
 
-            # try parse json
             try:
-                return r.json(), None
-            except Exception as e:
+                payload = response.json()
+            except Exception as e:  # noqa: BLE001
                 last_err = {
                     "kind": "json_parse_fail",
-                    "status": r.status_code,
-                    "contentType": ct,
+                    "status": response.status_code,
+                    "contentType": content_type,
                     "head": head,
                     "url": url,
                     "error": str(e),
                 }
                 _backoff(attempt)
                 continue
 
+            if not isinstance(payload, dict):
+                last_err = {
+                    "kind": "json_type_error",
+                    "status": response.status_code,
+                    "contentType": content_type,
+                    "head": head,
+                    "url": url,
+                }
+                _backoff(attempt)
+                continue
+
+            return payload, None
+
         except requests.RequestException as e:
             last_err = {
                 "kind": "request_exception",
                 "url": url,
                 "error": str(e),
             }
             _backoff(attempt)
             continue
 
     return None, last_err
 
-def _backoff(attempt: int) -> None:
-    # 0.6s, 1.2s, 2.4s... + jitter
-    base = 0.6 * (2 ** (attempt - 1))
-    time.sleep(base + random.random() * 0.4)
-
 
 # =====================
 # Law.go API wrappers
 # =====================
-def lawgo_search(query: str, knd: int = 3, display: int = 20) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
+def lawgo_search(
+    query: str,
+    session: requests.Session,
+    knd: int = 3,
+    display: int = 20,
+) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
     params = {
         "OC": LAWGO_OC,
         "target": "admrul",
         "type": "JSON",
         "query": query,
         "knd": str(knd),
         "display": str(display),
         "sort": "ddes",
     }
-print("STATUS", r.status_code)
-print("CT", r.headers.get("Content-Type"))
-print("HEAD", (r.text or "")[:200].replace("\n", " "))
-    return _request_json(LAW_SEARCH, params)
+    return _request_json(LAW_SEARCH, params, session)
+
 
-def lawgo_detail(admrul_id: str) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
+def lawgo_detail(
+    admrul_id: str,
+    session: requests.Session,
+) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
     params = {
         "OC": LAWGO_OC,
         "target": "admrul",
         "type": "JSON",
         "ID": str(admrul_id),
     }
-    return _request_json(LAW_SERVICE, params)
+    return _request_json(LAW_SERVICE, params, session)
 
 
 # =====================
 # Picking / parsing
 # =====================
-def pick_best_item(items, org_name="소방청"):
-    best = None
+def pick_best_item(items: List[Dict[str, Any]], org_name: str = "소방청") -> Optional[Dict[str, Any]]:
+    best: Optional[Dict[str, Any]] = None
     best_score = -1
+
     for it in items or []:
         org = (it.get("소관부처명") or it.get("소관부처") or "")
         kind = (it.get("행정규칙종류") or "")
+
         score = 0
         if org_name and org_name in org:
             score += 100
         if "고시" in kind:
             score += 20
         if it.get("발령일자"):
             score += 1
+
         if score > best_score:
-            best, best_score = it, score
+            best = it
+            best_score = score
+
     return best
 
-def _extract_items(search_json: Dict[str, Any]) -> list:
-    for k in ("admrul", "Admrul", "admruls"):
-        if k in search_json:
-            return search_json.get(k) or []
-    if "행정규칙" in search_json and isinstance(search_json["행정규칙"], list):
-        return search_json["행정규칙"]
+
+def _extract_items(search_json: Dict[str, Any]) -> List[Dict[str, Any]]:
+    for key in ("admrul", "Admrul", "admruls"):
+        value = search_json.get(key)
+        if isinstance(value, list):
+            return value
+
+    kr_value = search_json.get("행정규칙")
+    if isinstance(kr_value, list):
+        return kr_value
+
     return []
 
+
 def _extract_payload(detail_json: Dict[str, Any]) -> Dict[str, Any]:
-    # 상세 구조 다양성 대응
-    if isinstance(detail_json.get("행정규칙"), dict):
-        return detail_json["행정규칙"]
-    if isinstance(detail_json.get("admrul"), dict):
-        return detail_json["admrul"]
+    kr_payload = detail_json.get("행정규칙")
+    if isinstance(kr_payload, dict):
+        return kr_payload
+
+    en_payload = detail_json.get("admrul")
+    if isinstance(en_payload, dict):
+        return en_payload
+
     return detail_json
 
 
 # =====================
 # Snapshot builder
 # =====================
-def build_snapshot_entry(std_item: Dict[str, Any], tab_key: str, prev_entry: Dict[str, Any]) -> Dict[str, Any]:
+def build_snapshot_entry(
+    std_item: Dict[str, Any],
+    prev_entry: Dict[str, Any],
+    session: requests.Session,
+) -> Dict[str, Any]:
     query = std_item.get("query") or std_item.get("title") or std_item.get("code")
     knd = int(std_item.get("knd", 3))
     org_name = std_item.get("orgName", "소방청")
 
     # 1) search
-    sj, err = lawgo_search(query, knd=knd)
-    if err:
+    search_json, search_err = lawgo_search(query=query, session=session, knd=knd)
+    if search_err:
         return {
             **(prev_entry or {}),
             "code": std_item.get("code"),
             "title": std_item.get("title"),
             "checkedAt": TODAY,
             "error": {
                 "where": "search",
-                **err,
+                **search_err,
                 "query": query,
             },
         }
 
-    items = _extract_items(sj or {})
+    items = _extract_items(search_json or {})
     best = pick_best_item(items, org_name=org_name)
     if not best:
         return {
             **(prev_entry or {}),
             "code": std_item.get("code"),
             "title": std_item.get("title"),
             "checkedAt": TODAY,
             "error": {"where": "search", "kind": "no_results", "query": query},
         }
 
     adm_id = best.get("행정규칙일련번호") or best.get("일련번호") or best.get("id") or best.get("ID")
     if not adm_id:
         return {
             **(prev_entry or {}),
             "code": std_item.get("code"),
             "title": std_item.get("title"),
             "checkedAt": TODAY,
             "error": {"where": "search", "kind": "id_missing", "query": query},
         }
 
     # 2) detail
-    dj, derr = lawgo_detail(str(adm_id))
-    if derr:
+    detail_json, detail_err = lawgo_detail(str(adm_id), session=session)
+    if detail_err:
         return {
             **(prev_entry or {}),
             "code": std_item.get("code"),
             "title": std_item.get("title"),
             "checkedAt": TODAY,
             "lawgoId": str(adm_id),
-            "error": {"where": "detail", **derr},
+            "error": {"where": "detail", **detail_err},
         }
 
-    payload = _extract_payload(dj or {})
+    payload = _extract_payload(detail_json or {})
 
     notice_no = payload.get("발령번호")
     announce = ymd_int_to_dot(payload.get("발령일자"))
     effective = ymd_int_to_dot(payload.get("시행일자"))
-    rev = payload.get("제개정구분명")
+    revision_type = payload.get("제개정구분명")
     org = payload.get("소관부처명")
     name = payload.get("행정규칙명") or std_item.get("title")
 
     body_hash = sha256_text(payload.get("조문내용") or "")
-    add_hash = sha256_text((payload.get("부칙내용") or "") + (payload.get("별표내용") or ""))
+    supp_hash = sha256_text((payload.get("부칙내용") or "") + (payload.get("별표내용") or ""))
 
     html_url = best.get("행정규칙상세링크") or best.get("상세링크") or ""
     if not html_url:
-        html_url = f"{LAW_SERVICE}?OC={urllib.parse.quote(LAWGO_OC)}&target=admrul&ID={adm_id}&type=HTML"
+        html_url = (
+            f"{LAW_SERVICE}?OC={urllib.parse.quote(LAWGO_OC)}"
+            f"&target=admrul&ID={admrul_id_encoded(adm_id)}&type=HTML"
+        )
 
     return {
         "code": std_item.get("code"),
         "title": std_item.get("title"),
         "checkedAt": TODAY,
         "lawgoId": str(adm_id),
         "noticeNo": notice_no,
         "announceDate": announce,
         "effectiveDate": effective,
-        "revisionType": rev,
+        "revisionType": revision_type,
         "orgName": org,
         "ruleName": name,
         "htmlUrl": html_url,
         "bodyHash": body_hash,
-        "suppHash": add_hash,
+        "suppHash": supp_hash,
     }
 
-def detect_change(prev: Dict[str, Any], cur: Dict[str, Any]) -> Tuple[bool, list]:
+
+def admrul_id_encoded(adm_id: Any) -> str:
+    return urllib.parse.quote(str(adm_id))
+
+
+def detect_change(prev: Dict[str, Any], cur: Dict[str, Any]) -> Tuple[bool, List[str]]:
     if not prev:
         return False, []
+
     if prev.get("error") or cur.get("error"):
         # 에러 상태 변화도 기록 가치가 있음
         if (prev.get("error") or "") != (cur.get("error") or ""):
             return True, ["error"]
         return False, []
+
     keys = ["noticeNo", "announceDate", "effectiveDate", "revisionType", "bodyHash", "suppHash"]
-    diffs = [k for k in keys if (prev.get(k) or "") != (cur.get(k) or "")]
-    return (len(diffs) > 0), diffs
+    diffs = [key for key in keys if (prev.get(key) or "") != (cur.get(key) or "")]
+    return len(diffs) > 0, diffs
 
 
 # =====================
 # Main
 # =====================
-def main():
+def main() -> None:
     nfpc = load("standards_nfpc.json", {"items": []})
     nftc = load("standards_nftc.json", {"items": []})
     snap = load("snapshot.json", {"nfpc": {}, "nftc": {}})
     data = load("data.json", {"lastRun": None, "records": []})
 
-    changes = []
-    errors = []
+    changes: List[Dict[str, Any]] = []
+    errors: List[Dict[str, Any]] = []
 
-    for tab_key, std in (("nfpc", nfpc), ("nftc", nftc)):
-        for item in std.get("items", []):
-            code = item.get("code")
-            if not code:
-                continue
+    with requests.Session() as session:
+        for tab_key, std in (("nfpc", nfpc), ("nftc", nftc)):
+            for item in std.get("items", []):
+                code = item.get("code")
+                if not code:
+                    continue
 
-            prev = (snap.get(tab_key, {}) or {}).get(code, {})
-            cur = build_snapshot_entry(item, tab_key, prev)
-            snap.setdefault(tab_key, {})[code] = cur
-
-            # 에러 누적
-            if cur.get("error"):
-                errors.append({
-                    "code": code,
-                    "title": item.get("title"),
-                    "where": cur["error"].get("where"),
-                    "kind": cur["error"].get("kind"),
-                    "status": cur["error"].get("status"),
-                    "contentType": cur["error"].get("contentType"),
-                    "head": cur["error"].get("head"),
-                    "url": cur["error"].get("url"),
-                })
-
-            changed, diff_keys = detect_change(prev, cur)
-            if changed and not cur.get("error"):
-                changes.append({
-                    "code": code,
-                    "title": item.get("title"),
-                    "noticeNo": cur.get("noticeNo"),
-                    "announceDate": cur.get("announceDate"),
-                    "effectiveDate": cur.get("effectiveDate"),
-                    "reason": f"자동 감지: 메타/본문 해시 변경({', '.join(diff_keys)})",
-                    "diff": [],
-                    "supplementary": "부칙/경과규정은 원문 확인",
-                    "impact": [
-                        "설계: 시행일 기준 적용(도서·시방서에 적용기준 명시)",
-                        "시공: 자재/설비 선정 시 개정기준 충족 여부 확인",
-                        "유지관리: 점검대장에 적용기준/이력 기록",
-                    ],
-                    "refs": [{"label": "법제처(원문/DRF)", "url": cur.get("htmlUrl", "")}],
-                })
+                prev = (snap.get(tab_key, {}) or {}).get(code, {})
+                cur = build_snapshot_entry(item, prev, session)
+                snap.setdefault(tab_key, {})[code] = cur
+
+                if cur.get("error"):
+                    errors.append(
+                        {
+                            "code": code,
+                            "title": item.get("title"),
+                            "where": cur["error"].get("where"),
+                            "kind": cur["error"].get("kind"),
+                            "status": cur["error"].get("status"),
+                            "contentType": cur["error"].get("contentType"),
+                            "head": cur["error"].get("head"),
+                            "url": cur["error"].get("url"),
+                        }
+                    )
+
+                changed, diff_keys = detect_change(prev, cur)
+                if changed and not cur.get("error"):
+                    changes.append(
+                        {
+                            "code": code,
+                            "title": item.get("title"),
+                            "noticeNo": cur.get("noticeNo"),
+                            "announceDate": cur.get("announceDate"),
+                            "effectiveDate": cur.get("effectiveDate"),
+                            "reason": f"자동 감지: 메타/본문 해시 변경({', '.join(diff_keys)})",
+                            "diff": [],
+                            "supplementary": "부칙/경과규정은 원문 확인",
+                            "impact": [
+                                "설계: 시행일 기준 적용(도서·시방서에 적용기준 명시)",
+                                "시공: 자재/설비 선정 시 개정기준 충족 여부 확인",
+                                "유지관리: 점검대장에 적용기준/이력 기록",
+                            ],
+                            "refs": [{"label": "법제처(원문/DRF)", "url": cur.get("htmlUrl", "")}],
+                        }
+                    )
 
     data["lastRun"] = TODAY
 
     if changes:
         result = "변경 있음"
         summary = f"자동 감지: {len(changes)}건 변경(원문 확인 권장)"
     else:
         result = "변경 없음"
         summary = "전일 대비 변경 감지 없음"
 
-    # 에러가 있어도 워크플로는 “성공”으로 두고, 기록만 남김
     rec = {
         "id": TODAY,
         "date": TODAY,
         "scope": "NFPC / NFTC (법제처 OPEN API: 행정규칙)",
         "result": result,
         "summary": summary,
         "changes": changes,
         "errors": errors,
         "refs": [],
     }
 
-    # 같은 날짜 있으면 교체
     data["records"] = [r for r in data.get("records", []) if r.get("date") != TODAY]
     data["records"].insert(0, rec)
 
     save("snapshot.json", snap)
     save("data.json", data)
 
-    # 에러가 많아도 exit 0 (운영 지속)
     print(f"Done. changes={len(changes)} errors={len(errors)} date={TODAY}")
 
+
 if __name__ == "__main__":
     main()
 
EOF
)
