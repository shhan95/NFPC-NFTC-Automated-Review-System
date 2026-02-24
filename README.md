# NFPC/NFTC 전수 자동검토 (GitHub Pages + GitHub Actions)

## 구성
- GitHub Pages: `index.html`이 `data.json`, `snapshot.json`, `standards_*.json`을 읽어 대시보드 표시
- GitHub Actions: 매일 07:00(KST) 자동 실행 → 법제처 OPEN API로 전수 조회 → 변경 여부를 `data.json`에 누적 기록

## 1) 법제처 OPEN API OC 값 준비
- 법제처 국가법령정보 공동활용(OPEN API)에서 발급/등록한 **OC**가 필요합니다.
- OC는 보통 이메일의 ID(예: g4c@korea.kr → g4c) 형태로 안내됩니다.

## 2) GitHub Secret 설정
Repo → Settings → Secrets and variables → Actions → New repository secret
- Name: `LAWGO_OC`
- Value: (본인의 OC 값)

## 3) 배포
Repo → Settings → Pages
- Source: `Deploy from a branch`
- Branch: `main` / root
저장 후 1~2분 뒤 `https://<계정>.github.io/<repo>/`로 접속

## 4) 수동 테스트
Actions 탭 → `NFPC NFTC Daily Check` → Run workflow
완료 후 `data.json`/`snapshot.json` 커밋이 생성되면 정상.

## 주의
- 본 자동검토는 기본적으로 ‘발령/시행/발령번호/제개정구분 + 본문 해시’ 변경 감지입니다.
- 조문·별표 ‘신구대비 표’는 별도(부가) API 신청 또는 추가 파싱 로직이 필요할 수 있습니다.
