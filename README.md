<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>NFPC/NFTC 법령 자동검토 로그</title>
  <link rel="stylesheet" href="./style.css" />
</head>
<body>
  <header class="wrap">
    <div class="title">
      <h1>NFPC/NFTC 법령 자동검토 로그</h1>
      <p class="sub">법제처·소방청 기준 | 날짜별 검토 결과(변경 없음 / 변경 있음) 누적</p>
    </div>

    <div class="toolbar">
      <input id="q" class="input" type="search" placeholder="검색: 기준번호(NFPC 103), 고시번호, 키워드…" />
      <select id="resultFilter" class="select">
        <option value="all">전체</option>
        <option value="nochange">변경 없음</option>
        <option value="change">변경 있음</option>
      </select>
      <button id="exportBtn" class="btn">CSV 내보내기</button>
    </div>
  </header>

  <main class="wrap">
    <section class="cards" id="list"></section>

    <section class="detail" id="detail" hidden>
      <div class="detailHead">
        <h2 id="detailTitle"></h2>
        <button id="closeDetail" class="btn ghost">닫기</button>
      </div>

      <div id="detailBody"></div>
    </section>

    <footer class="foot">
      <span id="meta"></span>
    </footer>
  </main>

<script>
const $ = (id) => document.getElementById(id);

function badge(result){
  if(result === "변경 없음") return `<span class="badge ok">변경 없음</span>`;
  return `<span class="badge warn">변경 있음</span>`;
}

function esc(s){ return (s ?? "").toString()
  .replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;")
  .replaceAll('"',"&quot;").replaceAll("'","&#039;");
}

function formatRefs(refs){
  if(!refs?.length) return "";
  const items = refs.map(r => `<li><a href="${esc(r.url)}" target="_blank" rel="noreferrer">${esc(r.label)}</a></li>`).join("");
  return `<h3>원문 링크</h3><ul class="refs">${items}</ul>`;
}

function renderList(rows){
  const list = $("list");
  list.innerHTML = rows.map(r => `
    <article class="card" data-id="${esc(r.id)}">
      <div class="cardTop">
        <div class="date">${esc(r.date)}</div>
        ${badge(r.result)}
      </div>
      <div class="cardMid">
        <div class="scope">${esc(r.scope)}</div>
        <div class="summary">${esc(r.summary || "")}</div>
      </div>
      <div class="cardBot">
        <span class="muted">변경 법령:</span>
        <span>${esc((r.changes?.map(c=>c.code).join(", ")) || "-")}</span>
      </div>
    </article>
  `).join("");

  [...document.querySelectorAll(".card")].forEach(el=>{
    el.addEventListener("click", () => openDetail(el.dataset.id));
  });
}

let DATA = [];
let FILTERED = [];

function applyFilter(){
  const q = $("q").value.trim().toLowerCase();
  const rf = $("resultFilter").value;

  FILTERED = DATA.filter(r=>{
    if(rf === "nochange" && r.result !== "변경 없음") return false;
    if(rf === "change" && r.result !== "변경 있음") return false;

    if(!q) return true;
    const hay = [
      r.date, r.scope, r.result, r.summary,
      ...(r.changes||[]).flatMap(c => [c.code, c.title, c.noticeNo, c.reason]),
      ...(r.changes||[]).flatMap(c => (c.diff||[]).flatMap(d => [d.article, d.before, d.after])),
    ].join(" ").toLowerCase();
    return hay.includes(q);
  });

  renderList(FILTERED);
  $("meta").textContent = `총 ${FILTERED.length}건 표시 / 전체 ${DATA.length}건`;
}

function openDetail(id){
  const r = DATA.find(x=>x.id===id);
  if(!r) return;

  $("detail").hidden = false;
  $("detailTitle").innerHTML = `${esc(r.date)} · ${badge(r.result)} <span class="muted">(${esc(r.scope)})</span>`;

  if(r.result === "변경 없음"){
    $("detailBody").innerHTML = `
      <div class="panel">
        <p><b>검토 결과:</b> 변경 없음</p>
        <p class="muted">메모: ${esc(r.summary || "전일/전주 대비 신규·개정 고시/훈령/예규 등재 없음")}</p>
        ${formatRefs(r.refs)}
      </div>
    `;
    return;
  }

  const changes = (r.changes||[]).map(c=>`
    <div class="panel">
      <h3>${esc(c.code)} · ${esc(c.title || "")}</h3>
      <div class="grid">
        <div><span class="muted">고시/번호</span><div>${esc(c.noticeNo || "-")}</div></div>
        <div><span class="muted">발령일</span><div>${esc(c.announceDate || "-")}</div></div>
        <div><span class="muted">시행일</span><div>${esc(c.effectiveDate || "-")}</div></div>
      </div>

      <h3>개정이유(요지)</h3>
      <p>${esc(c.reason || "-")}</p>

      <h3>조문·별표 신구대비 핵심</h3>
      ${Array.isArray(c.diff) && c.diff.length ? `
        <table class="tbl">
          <thead><tr><th>조문/별표</th><th>변경 전</th><th>변경 후</th></tr></thead>
          <tbody>
            ${c.diff.map(d=>`
              <tr>
                <td>${esc(d.article || "")}</td>
                <td>${esc(d.before || "")}</td>
                <td>${esc(d.after || "")}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      ` : `<p class="muted">신구대비 표는 원문(신구법비교/제·개정이유) 확인 후 업데이트</p>`}

      <h3>부칙(경과규정·적용시점)</h3>
      <p>${esc(c.supplementary || "-")}</p>

      <h3>현장 영향 체크리스트(공동주택 포함)</h3>
      ${Array.isArray(c.impact) && c.impact.length ? `
        <ul class="check">
          ${c.impact.map(x=>`<li>${esc(x)}</li>`).join("")}
        </ul>
      ` : `<p class="muted">영향 체크리스트 없음</p>`}

      ${formatRefs(c.refs)}
    </div>
  `).join("");

  $("detailBody").innerHTML = changes + formatRefs(r.refs);
}

function closeDetail(){ $("detail").hidden = true; }
$("closeDetail").addEventListener("click", closeDetail);

function toCSV(rows){
  const cols = ["date","scope","result","summary","change_codes"];
  const lines = [cols.join(",")];
  for(const r of rows){
    const codes = (r.changes||[]).map(c=>c.code).join(";");
    const vals = [r.date,r.scope,r.result,(r.summary||""),codes].map(v =>
      `"${(v??"").toString().replaceAll('"','""')}"`
    );
    lines.push(vals.join(","));
  }
  return lines.join("\n");
}
$("exportBtn").addEventListener("click", ()=>{
  const csv = toCSV(FILTERED.length?FILTERED:DATA);
  const blob = new Blob([csv], {type:"text/csv;charset=utf-8"});
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "nfpc_nftc_audit_log.csv";
  a.click();
  URL.revokeObjectURL(url);
});

$("q").addEventListener("input", applyFilter);
$("resultFilter").addEventListener("change", applyFilter);

(async function init(){
  const res = await fetch("./data.json", {cache:"no-store"});
  const json = await res.json();
  DATA = (json.records || []).slice().sort((a,b)=> (a.date<b.date?1:-1));
  applyFilter();
})();
</script>
</body>
</html>
