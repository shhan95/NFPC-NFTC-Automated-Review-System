const $ = (id) => document.getElementById(id);
const esc = (s) => (s ?? "").toString()
  .replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;")
  .replaceAll('"',"&quot;").replaceAll("'","&#039;");

let TAB = "nfpc";
let NFPC = [];
let NFTC = [];
let LOG = { lastRun: null, records: [] };
let SNAP = { nfpc:{}, nftc:{} };

function badge(text){
  return text === "변경 없음"
    ? `<span class="badge ok">변경 없음</span>`
    : `<span class="badge warn">변경 있음</span>`;
}

function stdStatus(code){
  // 마지막 로그에서 해당 code가 변경으로 등장했는지 간단 표시
  for(const r of LOG.records){
    if(r.result === "변경 있음" && (r.changes||[]).some(c=>c.code===code)) return "변경 있음";
  }
  return "변경 없음";
}

function renderStandards(){
  const q = $("searchStd").value.trim().toLowerCase();
  const list = TAB === "nfpc" ? NFPC : NFTC;

  const rows = list.filter(x=>{
    if(!q) return true;
    return [x.code,x.title,x.noticeNo,x.url].join(" ").toLowerCase().includes(q);
  }).map(x=>{
    const st = stdStatus(x.code);
    return `
      <div class="item" data-code="${esc(x.code)}" data-tab="${esc(TAB)}">
        <div class="itemTop">
          <div>
            <div class="code">${esc(x.code)}</div>
            <div class="title">${esc(x.title || "")}</div>
          </div>
          ${badge(st)}
        </div>
        <div class="small">${esc(x.noticeNo || "")} · ${esc(x.url || "")}</div>
      </div>
    `;
  }).join("");

  $("stdList").innerHTML = rows || `<div class="small">표시할 항목이 없습니다.</div>`;

  document.querySelectorAll(".item").forEach(el=>{
    el.addEventListener("click", ()=> openStd(el.dataset.tab, el.dataset.code));
  });
}

function renderLogs(){
  const rf = $("resultFilter").value;
  const rows = LOG.records
    .filter(r=>{
      if(rf==="nochange") return r.result==="변경 없음";
      if(rf==="change") return r.result==="변경 있음";
      return true;
    })
    .map(r=>`
      <div class="logRow">
        <div class="logRowHead">
          <div><b>${esc(r.date)}</b> <span class="small">${esc(r.scope||"NFPC/NFTC")}</span></div>
          ${badge(r.result)}
        </div>
        <div class="small">${esc(r.summary||"")}</div>
        <div class="small"><b>변경:</b> ${(r.changes||[]).map(c=>esc(c.code)).join(", ") || "-"}</div>
      </div>
    `).join("");

  $("logList").innerHTML = rows || `<div class="small">로그가 없습니다.</div>`;
}

function openStd(tab, code){
  const list = tab==="nfpc" ? NFPC : NFTC;
  const s = list.find(x=>x.code===code);
  const snap = (SNAP[tab]||{})[code];

  $("dlgTitle").innerHTML = `${esc(code)} · ${esc(s?.title||"")}`;
  $("dlgSub").innerHTML = `${tab.toUpperCase()} · 원문 링크: <a href="${esc(s?.url||"#")}" target="_blank" rel="noreferrer">열기</a>`;

  const meta = snap ? `
    <table class="tbl">
      <thead><tr><th>항목</th><th>값</th></tr></thead>
      <tbody>
        <tr><td>고시번호</td><td>${esc(snap.noticeNo||s?.noticeNo||"-")}</td></tr>
        <tr><td>발령일</td><td>${esc(snap.announceDate||"-")}</td></tr>
        <tr><td>시행일</td><td>${esc(snap.effectiveDate||"-")}</td></tr>
        <tr><td>개정유형</td><td>${esc(snap.revisionType||"-")}</td></tr>
        <tr><td>최근확인</td><td>${esc(snap.checkedAt||"-")}</td></tr>
      </tbody>
    </table>
  ` : `<div class="small">스냅샷 정보가 없습니다(첫 자동검토 후 생성됩니다).</div>`;

  $("dlgBody").innerHTML = `
    <div class="small">※ 자동검토는 기본적으로 ‘메타(발령/시행/연혁) 변경 감지’를 수행합니다. 조문·별표 신구대비는 원문 제공 형식에 따라 자동 채움이 제한될 수 있습니다.</div>
    ${meta}
    <div style="margin-top:10px">
      <a href="${esc(s?.url||"#")}" target="_blank" rel="noreferrer">법제처/소방청 원문 보기</a>
    </div>
  `;
  $("dlg").showModal();
}

function downloadJson(){
  const blob = new Blob([JSON.stringify(LOG,null,2)], {type:"application/json;charset=utf-8"});
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "data.json";
  a.click();
  URL.revokeObjectURL(url);
}

async function init(){
  const [nfpc,nftc,log,snap] = await Promise.all([
    fetch("./standards_nfpc.json",{cache:"no-store"}).then(r=>r.json()),
    fetch("./standards_nftc.json",{cache:"no-store"}).then(r=>r.json()),
    fetch("./data.json",{cache:"no-store"}).then(r=>r.json()),
    fetch("./snapshot.json",{cache:"no-store"}).then(r=>r.json()).catch(()=>({nfpc:{},nftc:{}}))
  ]);
  NFPC = nfpc.items || [];
  NFTC = nftc.items || [];
  LOG = log;
  SNAP = snap;

  $("lastRun").textContent = `마지막 자동검토: ${LOG.lastRun || "-"}`;

  document.querySelectorAll(".tab").forEach(btn=>{
    btn.addEventListener("click", ()=>{
      document.querySelectorAll(".tab").forEach(b=>b.classList.remove("active"));
      btn.classList.add("active");
      TAB = btn.dataset.tab;
      renderStandards();
    });
  });

  $("searchStd").addEventListener("input", renderStandards);
  $("resultFilter").addEventListener("change", renderLogs);
  $("downloadJson").addEventListener("click", downloadJson);
  $("dlgClose").addEventListener("click", ()=> $("dlg").close());

  renderStandards();
  renderLogs();
}
init();
