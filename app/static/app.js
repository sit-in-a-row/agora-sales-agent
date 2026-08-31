const $ = s => document.querySelector(s), $$ = s => [...document.querySelectorAll(s)];
function uiWarn(selector){ console.warn(`[UI] element not found: ${selector}. If you just upgraded, hard-refresh once.`); }
function setText(selector, value){ const el=$(selector); if(!el){uiWarn(selector);return null;} el.textContent=String(value??''); return el; }
function setHtml(selector, value){ const el=$(selector); if(!el){uiWarn(selector);return null;} el.innerHTML=String(value??''); return el; }
function setDisabled(selector, value){ const el=$(selector); if(!el){uiWarn(selector);return null;} el.disabled=!!value; return el; }
function bind(selector, event, handler){ const el=$(selector); if(!el){uiWarn(selector);return null;} el.addEventListener(event,handler); return el; }
const LS = {
  settings: 'agoraSales.v1.6.settings',
  currentJob: 'agoraSales.v1.6.currentJob',
  preview: 'agoraSales.v1.6.preview',
  selected: 'agoraSales.v1.6.selectedRows',
  section: 'agoraSales.v1.6.section',
};
let selectedFile = null;
let currentFileSignature = null;
let inspectionData = null;
let previewRows = [];
let selectedVisitorIds = new Set();
let currentJob = null;
let eventSource = null;
let leads = {};
let currentFilter = 'ALL';
let apiTraces = [];
let lastEventId = -1;
let notionMatches = {};
let notionConnected = false;
let deploymentMode = 'local';
let activeStreamAbort = null;
let apiTraceAll = [];

async function api(url, opts={}){
  const r = await fetch(url, opts);
  if(!r.ok){ let t=await r.text(); try{t=JSON.parse(t).detail||t}catch{} throw new Error(t); }
  return r.json();
}
function esc(s){ return String(s??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c])); }
function log(message, level='info'){
  const d=document.createElement('div'); d.className='log-entry '+level;
  d.innerHTML=`<span class="time">${new Date().toLocaleTimeString()}</span> ${esc(message)}`;
  $('#log').prepend(d);
}
function safeParse(key, fallback){ try{return JSON.parse(localStorage.getItem(key)||'') ?? fallback}catch{return fallback} }
function fileSignature(f){ return f ? `${f.name}|${f.size}|${f.lastModified}` : null; }

async function health(){
  try{
    const h=await api('/api/health');
    deploymentMode=h.deployment_mode||'local';
    const s=$('#serverStatus');
    if(s){s.classList.add('ok');s.innerHTML=`<i></i>Backend v${esc(h.version||'?')} 연결됨${deploymentMode==='vercel'?' · Vercel':''}`;}
  }catch{ setHtml('#serverStatus','<i></i>Backend 오류'); }
}

function notionConfig(){
  return {
    api_key:$('#notionApiKey')?.value?.trim()||'',
    database_url:$('#notionDatabaseUrl')?.value?.trim()||'',
  };
}
function notionReady(){const c=notionConfig();return !!(c.api_key&&c.database_url);}
function setNotionStatus(text,state=''){const el=$('#notionStatus');if(!el)return;el.textContent=text;el.className='notion-status'+(state?' '+state:'');}
async function testNotionConnection(refresh=true){
  if(!notionReady()){setNotionStatus('Key / DB URL 필요','error');return false;}
  setNotionStatus('연결 확인 중…','loading');
  try{
    const c=notionConfig();
    const x=await api('/api/notion/test',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(c)});
    notionConnected=true;setNotionStatus('Notion 연결됨','ok');
    setText('#notionMatchSummary',`${x.data_source_name||'Sales DB'} · API ${x.notion_version||''}`);
    saveSettings();
    if(refresh&&previewRows.length)await refreshNotionMatches();
    return true;
  }catch(e){notionConnected=false;setNotionStatus('연결 실패','error');setText('#notionMatchSummary',e.message);log('Notion 연결 실패: '+e.message,'error');return false;}
}
async function refreshNotionMatches(){
  if(!notionReady()){notionMatches={};setText('#notionMatchSummary','Notion Key와 DB URL을 입력하면 기존 생성 여부를 표시한다.');renderPreview();return;}
  if(!previewRows.length)return;
  setNotionStatus('DB 대조 중…','loading');
  try{
    const c=notionConfig();
    const rows=previewRows.map(r=>({visitor_id:r.visitor_id,company:r.company,name:r.name,email:r.email}));
    const x=await api('/api/notion/match',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...c,rows})});
    notionMatches=x.matches||{}; notionConnected=true;
    const vals=Object.values(notionMatches);
    const exact=vals.filter(v=>v.match==='EXACT').length, company=vals.filter(v=>v.match==='COMPANY').length, fresh=vals.filter(v=>v.match==='NONE').length;
    setNotionStatus('Notion 연결됨','ok');
    setText('#notionMatchSummary',`메일 저장됨 ${exact} · 회사 조사 있음 ${company} · 미생성 ${fresh} · DB 전체 ${x.total_saved||0}`);
    renderPreview(); updateLaunchState();
  }catch(e){notionConnected=false;setNotionStatus('대조 실패','error');setText('#notionMatchSummary',e.message);log('Notion 대조 실패: '+e.message,'warning');}
}
function notionBadgeForRow(r){
  const m=notionMatches[r.visitor_id];
  if(!notionReady())return '<span class="notion-badge UNKNOWN">미연결</span>';
  if(!m)return '<span class="notion-badge UNKNOWN">확인 전</span>';
  if(m.match==='EXACT')return `<span class="notion-badge EXACT">메일 저장됨</span>${m.page_url?`<a class="notion-link" href="${esc(m.page_url)}" target="_blank">↗</a>`:''}`;
  if(m.match==='COMPANY')return `<span class="notion-badge COMPANY">회사 조사 있음</span>${m.page_url?`<a class="notion-link" href="${esc(m.page_url)}" target="_blank">↗</a>`:''}`;
  return '<span class="notion-badge NONE">미생성</span>';
}
async function loadNotionExactForRows(rows){
  const pageIds=[...new Set(rows.map(r=>notionMatches[r.visitor_id]).filter(m=>m?.match==='EXACT'&&m.page_id).map(m=>m.page_id))];
  if(!pageIds.length)return 0;
  const c=notionConfig();
  const x=await api('/api/notion/load',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...c,page_ids:pageIds})});
  let loaded=0;
  for(const item of (x.items||[])){
    const l=item.lead;if(!l?.lead_id)continue;
    l.loaded_from_notion=true;l.notion={...(item.record||{}),sync_action:'loaded'};
    leads[l.lead_id]=l;loaded++;
  }
  if(loaded){renderLeads();renderReviews();log(`Notion 기존 결과 ${loaded}건 로드 · API 재생성 생략`);}
  return loaded;
}

function showSection(id, persist=true){
  $$('.section').forEach(s=>s.classList.toggle('visible',s.id===id));
  $$('.nav-item').forEach(b=>b.classList.toggle('active',b.dataset.target===id));
  if(persist) localStorage.setItem(LS.section,id);
}
$$('.nav-item').forEach(b=>b.onclick=()=>showSection(b.dataset.target));

function saveSettings(){
  const remember=$('#rememberApiKey').checked;
  const data={
    sourceMode:$('#sourceMode').value,
    runScope:$('#runScope').value,
    concurrency:$('#concurrency').value,
    maxLeads:$('#maxLeads').value,
    senderName:$('#senderName').value,
    senderTitle:$('#senderTitle').value,
    senderSignature:$('#senderSignature').value,
    quickMode:$('#quickMode').checked,
    demoMode:$('#demoMode').checked,
    rememberApiKey:remember,
    apiKey:remember?$('#apiKey').value:'',
    rememberNotionKey:$('#rememberNotionKey')?.checked||false,
    notionApiKey:($('#rememberNotionKey')?.checked?($('#notionApiKey')?.value||''):''),
    notionDatabaseUrl:$('#notionDatabaseUrl')?.value||'',
    notionAutoSync:$('#notionAutoSync')?.checked!==false,
    notionReuseResearch:$('#notionReuseResearch')?.checked!==false,
    emailStyleReference:$('#emailStyleReference').value.slice(0,30000),
    autoFollowTrace:$('#autoFollowTrace').checked,
    currentFilter,
  };
  localStorage.setItem(LS.settings,JSON.stringify(data));
}
function restoreSettings(){
  // One-time convenience migration from v1.5 UI preferences. Secrets remain opt-in only.
  if(!localStorage.getItem(LS.settings)){
    const old=safeParse('agoraSales.v1.5.settings',null);
    if(old) try{localStorage.setItem(LS.settings,JSON.stringify(old));}catch{}
  }
  const s=safeParse(LS.settings,{});
  if(s.sourceMode && [...$('#sourceMode').options].some(o=>o.value===s.sourceMode)) $('#sourceMode').value=s.sourceMode;
  if(s.runScope) $('#runScope').value=s.runScope;
  if(s.concurrency) $('#concurrency').value=s.concurrency;
  if(s.maxLeads!=null) $('#maxLeads').value=s.maxLeads;
  $('#senderName').value=s.senderName||'박세빈';
  $('#senderTitle').value=s.senderTitle||'한국 매니저';
  $('#senderSignature').value=s.senderSignature||'박세빈 (Sebin Park)';
  $('#quickMode').checked=s.quickMode!==false;
  $('#demoMode').checked=!!s.demoMode;
  $('#rememberApiKey').checked=!!s.rememberApiKey;
  if(s.rememberApiKey && s.apiKey) $('#apiKey').value=s.apiKey;
  if($('#rememberNotionKey')) $('#rememberNotionKey').checked=!!s.rememberNotionKey;
  if($('#notionApiKey') && s.rememberNotionKey && s.notionApiKey) $('#notionApiKey').value=s.notionApiKey;
  if($('#notionDatabaseUrl')) $('#notionDatabaseUrl').value=s.notionDatabaseUrl||'https://app.notion.com/p/3cdcd049963380f794a8faea1bedcab5?v=3cdcd04996338020a2dc000cfd5ee330';
  if($('#notionAutoSync')) $('#notionAutoSync').checked=s.notionAutoSync!==false;
  if($('#notionReuseResearch')) $('#notionReuseResearch').checked=s.notionReuseResearch!==false;
  $('#emailStyleReference').value=s.emailStyleReference||'';
  $('#autoFollowTrace').checked=s.autoFollowTrace!==false;
  currentFilter=s.currentFilter||'ALL';
  $$('.filter').forEach(x=>x.classList.toggle('active',x.dataset.filter===currentFilter));
  $('#apiKey').disabled=$('#demoMode').checked;
}

function savePreviewCache(){
  if(!previewRows.length) return;
  const cachedRows=previewRows.map(r=>{const {email,...rest}=r;return rest}); const data={fileSignature:currentFileSignature,sourceMode:$('#sourceMode').value,rows:cachedRows,source:$('#previewStatus').textContent};
  try{ localStorage.setItem(LS.preview,JSON.stringify(data)); }catch(e){ console.warn('preview cache skipped',e); }
  localStorage.setItem(LS.selected,JSON.stringify([...selectedVisitorIds]));
}
function restorePreviewCache(){
  const p=safeParse(LS.preview,null);
  if(!p?.rows?.length) return;
  previewRows=p.rows;
  currentFileSignature=p.fileSignature||null;
  if(p.sourceMode && [...$('#sourceMode').options].some(o=>o.value===p.sourceMode)) $('#sourceMode').value=p.sourceMode;
  selectedVisitorIds=new Set(safeParse(LS.selected,[]));
  setText('#previewStatus',`이전 미리보기 복구 · ${previewRows.length} rows`);
  setText('#restoreNote','업로드 파일 자체는 브라우저 보안상 복구되지 않는다. 새 실행 전 같은 파일을 다시 선택하면 된다.');
  renderPreview();
}

const dz=$('#dropzone'), fi=$('#fileInput');
dz.ondragover=e=>{e.preventDefault();dz.classList.add('drag')}; dz.ondragleave=()=>dz.classList.remove('drag');
dz.ondrop=e=>{e.preventDefault();dz.classList.remove('drag');if(e.dataTransfer.files[0])setFile(e.dataTransfer.files[0])};
fi.onchange=()=>fi.files[0]&&setFile(fi.files[0]);

async function setFile(f){
  const sig=fileSignature(f);
  const priorSig=currentFileSignature;
  selectedFile=f; currentFileSignature=sig;
  setText('#fileLabel',`${f.name} · ${(f.size/1024).toFixed(1)} KB`);
  { const el=$('#inspection'); if(el){el.className='inspection';el.textContent='파일 구조 검사 중…';} else uiWarn('#inspection'); }
  setDisabled('#startBtn',true);
  if(priorSig && priorSig!==sig){ selectedVisitorIds.clear(); previewRows=[]; localStorage.removeItem(LS.selected); }
  try{
    const fd=new FormData(); fd.append('file',f);
    const x=await api('/api/inspect',{method:'POST',body:fd}); inspectionData=x;
    const chips=(x.sheets||[]).map(s=>`<span class="sheet-chip">${esc(s.name)} · ${s.data_rows} rows</span>`).join('');
    setHtml('#inspection',`<b>권장 소스: ${esc(x.suggested_source_label)}</b><br>예상 ${x.estimated_records}건 · 필드 ${Object.keys(x.logical_headers||{}).length}개 인식<br>${chips}${(x.notes||[]).map(n=>`<br><span class="muted">${esc(n)}</span>`).join('')}`);
    updateImptPresetLabels(x.company_size_counts||{});
    addSheetOptions(x.sheets||[]);
    if(x.suggested_source_mode && !localStorage.getItem(LS.settings) && [...$('#sourceMode').options].some(o=>o.value===x.suggested_source_mode)) $('#sourceMode').value=x.suggested_source_mode;
    await loadPreview();
    log(`파일 검사 완료: ${x.estimated_records} records`);
  }catch(e){ setText('#inspection','검사 실패: '+e.message); log(e.message,'error'); console.error('inspect failed',e); }
  updateLaunchState();
}

function updateImptPresetLabels(counts={}){
  const n=k=>Number(counts?.[k]||0);
  const labels={
    impt_all:`Impt (all · ${n('대기업')+n('중견기업')+n('스타트업')+n('미분류')})`,
    impt_large:`Impt (대기업 · ${n('대기업')})`,
    impt_mid:`Impt (중견기업 · ${n('중견기업')})`,
    impt_startup:`Impt (스타트업 · ${n('스타트업')})`,
    impt_large_mid:`Impt (대기업 + 중견기업 · ${n('대기업')+n('중견기업')})`,
    impt_large_startup:`Impt (대기업 + 스타트업 · ${n('대기업')+n('스타트업')})`,
    impt_mid_startup:`Impt (중견기업 + 스타트업 · ${n('중견기업')+n('스타트업')})`,
    main:'Main',
  };
  for(const [value,label] of Object.entries(labels)){const opt=[...$('#sourceMode').options].find(o=>o.value===value);if(opt)opt.textContent=label;}
}

function addSheetOptions(sheets){
  [...$('#sourceMode').options].filter(o=>o.dataset.dynamic==='1').forEach(o=>o.remove());
  for(const s of sheets){
    const v=`sheet:${s.name}`;
    if([...$('#sourceMode').options].some(o=>o.value===v)) continue;
    const o=document.createElement('option'); o.value=v; o.textContent=`원본 시트 · ${s.name}`; o.dataset.dynamic='1'; $('#sourceMode').appendChild(o);
  }
  const saved=safeParse(LS.settings,{}).sourceMode;
  if(saved && [...$('#sourceMode').options].some(o=>o.value===saved)) $('#sourceMode').value=saved;
}

async function loadPreview(){
  if(!selectedFile){ log('새 미리보기에는 파일을 다시 선택해야 한다.','warning'); return; }
  setText('#previewStatus','표 생성 중…');
  const fd=new FormData(); fd.append('file',selectedFile); fd.append('source_mode',$('#sourceMode').value); fd.append('limit','2000');
  try{
    const cachedBefore=safeParse(LS.preview,null);
    const priorSelected=new Set(selectedVisitorIds);
    const x=await api('/api/preview',{method:'POST',body:fd});
    previewRows=x.records||[];
    const newIds=new Set(previewRows.map(r=>r.visitor_id));
    if(cachedBefore?.sourceMode===$('#sourceMode').value){
      selectedVisitorIds=new Set([...priorSelected].filter(id=>newIds.has(id)));
    }else{
      selectedVisitorIds.clear();
    }
    setText('#previewStatus',`${x.source||($('#sourceMode')?.value||'')} · ${previewRows.length} rows`);
    notionMatches={}; renderPreview(); savePreviewCache(); updateLaunchState();
    log(`미리보기 생성: ${previewRows.length} rows`);
    if(notionReady()) await refreshNotionMatches();
  }catch(e){ setText('#previewStatus','미리보기 실패'); log(e.message,'error'); console.error('preview failed',e); }
}

function filteredPreviewRows(){
  const q=$('#previewSearch').value.trim().toLowerCase(); if(!q) return previewRows;
  return previewRows.filter(r=>[r.name,r.company,r.department,r.job_title,r.company_size,r.visitor_role,r.seniority,r.industry,r.function,r.interests].some(v=>String(v||'').toLowerCase().includes(q)));
}
function renderPreview(){
  const rows=filteredPreviewRows(); const tb=$('#previewTable');
  if(!rows.length){tb.innerHTML='<tr class="placeholder"><td colspan="12">표시할 row가 없다.</td></tr>'; updateSelectedCount(); return;}
  tb.innerHTML=rows.map(r=>`<tr class="${selectedVisitorIds.has(r.visitor_id)?'selected-row':''}"><td class="check-col"><input class="row-check" type="checkbox" data-id="${esc(r.visitor_id)}" ${selectedVisitorIds.has(r.visitor_id)?'checked':''}></td><td>${notionBadgeForRow(r)}</td><td>${esc(r.row_number)}</td><td>${esc(r.visited_at||'')}</td><td><b>${esc(r.name||'')}</b></td><td>${esc(r.company||'')}</td><td>${esc(r.department||'')}</td><td>${esc(r.job_title||'')}</td><td><span class="size-chip">${esc(r.company_size||'미분류')}</span></td><td>${esc(r.visitor_role||'')}</td><td>${esc(r.seniority||'')}</td><td class="interest-cell">${esc(r.interests||'')}</td></tr>`).join('');
  $$('.row-check').forEach(c=>c.onchange=()=>{ if(c.checked)selectedVisitorIds.add(c.dataset.id);else selectedVisitorIds.delete(c.dataset.id); c.closest('tr').classList.toggle('selected-row',c.checked); updateSelectedCount(); savePreviewCache(); updateLaunchState(); });
  updateSelectedCount();
}
function updateSelectedCount(){ setText('#selectedCount',`${selectedVisitorIds.size}개 선택 · 현재 표 ${filteredPreviewRows().length}/${previewRows.length}`); }
$('#previewSearch').oninput=renderPreview;
$('#selectVisible').onclick=()=>{filteredPreviewRows().forEach(r=>selectedVisitorIds.add(r.visitor_id));renderPreview();savePreviewCache();updateLaunchState();};
$('#clearSelected').onclick=()=>{selectedVisitorIds.clear();renderPreview();savePreviewCache();updateLaunchState();};
$('#refreshPreview').onclick=loadPreview;
$('#sourceMode').onchange=()=>{saveSettings();loadPreview();};
$('#runScope').onchange=()=>{saveSettings();updateLaunchState();};

$('#toggleKey').onclick=()=>{const i=$('#apiKey');i.type=i.type==='password'?'text':'password';$('#toggleKey').textContent=i.type==='password'?'보기':'숨김'};
if($('#toggleNotionKey')) $('#toggleNotionKey').onclick=()=>{const i=$('#notionApiKey');i.type=i.type==='password'?'text':'password';$('#toggleNotionKey').textContent=i.type==='password'?'보기':'숨김'};
if($('#testNotion')) $('#testNotion').onclick=()=>testNotionConnection(true);
if($('#refreshNotionStatus')) $('#refreshNotionStatus').onclick=refreshNotionMatches;
if($('#rememberNotionKey')) $('#rememberNotionKey').onchange=saveSettings;
if($('#notionImportFile')) $('#notionImportFile').onchange=()=>{const f=$('#notionImportFile').files[0];setText('#notionImportFileName',f?`${f.name} · ${(f.size/1024).toFixed(1)} KB`:'파일 미선택');};
if($('#importNotionArtifact')) $('#importNotionArtifact').onclick=async()=>{
  const f=$('#notionImportFile')?.files?.[0];
  if(!f){alert('artifacts.zip 또는 final_leads.json을 선택하세요.');return;}
  if(!notionReady()){alert('먼저 Notion API Key와 Database URL을 입력하세요.');return;}
  const btn=$('#importNotionArtifact');btn.disabled=true;setText('#notionImportStatus','기존 결과를 Notion에 저장 중…');
  const c=notionConfig(),fd=new FormData();fd.append('file',f);fd.append('notion_api_key',c.api_key);fd.append('notion_database_url',c.database_url);
  try{
    const x=await api('/api/notion/import',{method:'POST',body:fd});
    setText('#notionImportStatus',`완료 · ${x.synced}/${x.total} 저장${x.failed?` · 실패 ${x.failed}`:''}`);
    log(`Notion Backfill 완료: ${x.synced}/${x.total}${x.failed?` · 실패 ${x.failed}`:''}`,x.failed?'warning':'info');
    notionConnected=true;if(previewRows.length)await refreshNotionMatches();
  }catch(e){setText('#notionImportStatus','실패 · '+e.message);log('Notion Backfill 실패: '+e.message,'error');}
  finally{btn.disabled=false;}
};
['notionApiKey','notionDatabaseUrl','notionAutoSync','notionReuseResearch'].forEach(id=>{const el=$('#'+id);if(el)el.addEventListener(el.type==='checkbox'?'change':'input',()=>{notionConnected=false;saveSettings();});});
$('#demoMode').onchange=()=>{$('#apiKey').disabled=$('#demoMode').checked;saveSettings();updateLaunchState();};
$('#rememberApiKey').onchange=saveSettings;
['apiKey','concurrency','maxLeads','senderName','senderTitle','senderSignature','quickMode','emailStyleReference','autoFollowTrace'].forEach(id=>{ const el=$('#'+id); if(el) el.addEventListener(el.type==='checkbox'?'change':'input',()=>{saveSettings();updateLaunchState();}); });

$('#emailStyleFile').onchange=async()=>{const f=$('#emailStyleFile').files[0];if(!f)return;setText('#styleFileName',f.name);try{$('#emailStyleReference').value=await f.text();saveSettings();}catch(e){alert('메일 예시 파일을 읽지 못했습니다.')}};
$('#caseFiles').onchange=()=>{const fs=[...$('#caseFiles').files];$('#caseFileList').innerHTML=fs.length?fs.map(f=>`<span class="case-chip">${esc(f.name)}</span>`).join(''):'추가 case 없음';};

function updateLaunchState(){
  const selectedMode=$('#runScope').value==='selected';
  const selectionOk=!selectedMode || selectedVisitorIds.size>0;
  const targetRows=selectedMode?previewRows.filter(r=>selectedVisitorIds.has(r.visitor_id)):previewRows;
  const allSaved=notionReady() && targetRows.length>0 && targetRows.every(r=>notionMatches[r.visitor_id]?.match==='EXACT');
  const keyOk=$('#demoMode').checked || !!$('#apiKey').value.trim() || allSaved;
  const sourceOk=!!selectedFile || allSaved;
  setDisabled('#startBtn',!(sourceOk&&selectionOk&&keyOk));
  const scope=selectedMode?`${selectedVisitorIds.size}개 선택 row`:`현재 preset 전체${$('#maxLeads').value>0?` · 최대 ${$('#maxLeads').value} lead`:''}`;
  const prefix=allSaved&&!selectedFile?'Notion 저장본만 로드':($('#sourceMode')?.selectedOptions?.[0]?.textContent||'');
  setText('#launchSummary',sourceOk?`${prefix} · ${scope}`:'파일과 실행 row를 선택해 주세요.');
  setText('#startBtnLabel',allSaved?'Notion 저장본 불러오기':(selectedMode?'선택 Row 분석 시작':'Preset 분석 시작'));
}

$('#startBtn').onclick=startJob;
$('#cancelBtn').onclick=async()=>{
  if(deploymentMode==='vercel' && activeStreamAbort){
    activeStreamAbort.abort(); activeStreamAbort=null; $('#cancelBtn').disabled=true; $('#startBtn').disabled=false; log('Vercel 실행을 중단했습니다.','warning'); return;
  }
  if(currentJob){await api(`/api/jobs/${currentJob}/cancel`,{method:'POST'});log('취소 요청 전송','warning')}
};

async function startJob(){
  if($('#runScope').value==='selected' && !selectedVisitorIds.size){alert('먼저 실행할 row를 체크하세요.');return;}
  if(!previewRows.length){alert('실행할 row가 없습니다. 파일을 선택하거나 이전 미리보기를 복구하세요.');return;}

  const demo=$('#demoMode').checked;
  const selectedMode=$('#runScope').value==='selected';
  const targetRows=selectedMode?previewRows.filter(r=>selectedVisitorIds.has(r.visitor_id)):previewRows.slice();
  if(!targetRows.length){alert('실행할 row가 없습니다.');return;}

  leads={}; apiTraces=[]; renderApiTraces(); renderLeads(); renderReviews(); $('#downloadRow').innerHTML='';
  setDisabled('#startBtn',true); $('#cancelBtn').disabled=true; $('#log').innerHTML='';
  updateProgress({progress:0,stage:'준비',message:'Notion 기존 결과 확인 중'});

  let exactRows=[];
  if(notionReady()){
    if(!Object.keys(notionMatches).length) await refreshNotionMatches();
    exactRows=targetRows.filter(r=>notionMatches[r.visitor_id]?.match==='EXACT');
    try{await loadNotionExactForRows(exactRows);}catch(e){log('Notion 기존 결과 로드 실패: '+e.message,'warning');exactRows=[];}
  }
  const exactIds=new Set(exactRows.map(r=>r.visitor_id));
  const newRows=targetRows.filter(r=>!exactIds.has(r.visitor_id));
  updateSummary({total:0,quality:0,normal:0,trash:0,manual:0});

  if(!newRows.length){
    currentJob=null;localStorage.removeItem(LS.currentJob);
    updateProgress({progress:100,stage:'완료',message:`선택 대상 ${targetRows.length}건을 Notion에서 불러왔습니다. 신규 API 생성 없음.`});
    $('#cancelBtn').disabled=true;$('#startBtn').disabled=false;renderLeads();renderReviews();showSection('resultsSection');
    log('모든 선택 대상이 Notion에 이미 저장되어 있어 API 재생성을 생략했습니다.');
    return;
  }

  if(!selectedFile){alert(`신규 생성 대상 ${newRows.length}건이 있습니다. 원본 Excel/CSV 파일을 다시 선택하세요.`);$('#startBtn').disabled=false;return;}
  if(!demo&&!$('#apiKey').value.trim()){alert(`신규 생성 대상 ${newRows.length}건이 있습니다. OpenAI API Key를 입력하세요.`);$('#startBtn').disabled=false;return;}

  if(deploymentMode==='vercel'){
    return startVercelRuns(newRows, exactRows, targetRows, demo);
  }

  $('#cancelBtn').disabled=false;
  updateProgress({progress:0,stage:'준비',message:`기존 ${exactRows.length}건 로드 · 신규 ${newRows.length}건 업로드 중`});

  const fd=new FormData();
  fd.append('file',selectedFile); fd.append('api_key',$('#apiKey').value.trim()); fd.append('source_mode',$('#sourceMode').value);
  fd.append('max_leads',selectedMode?'0':($('#maxLeads').value||'0'));
  fd.append('selected_visitor_ids',selectedMode?JSON.stringify(newRows.map(r=>r.visitor_id)):'[]');
  fd.append('excluded_visitor_ids',selectedMode?'[]':JSON.stringify([...exactIds]));
  fd.append('demo_mode',demo?'true':'false'); fd.append('quick_mode',$('#quickMode').checked?'true':'false');
  fd.append('sender_name',$('#senderName').value); fd.append('sender_title',$('#senderTitle').value); fd.append('sender_signature',$('#senderSignature').value);
  fd.append('concurrency',$('#concurrency').value); fd.append('email_style_reference',$('#emailStyleReference').value);
  if(notionReady()){
    const c=notionConfig();
    fd.append('notion_api_key',c.api_key);fd.append('notion_database_url',c.database_url);
    fd.append('notion_auto_sync',$('#notionAutoSync').checked?'true':'false');
    fd.append('notion_reuse_research',$('#notionReuseResearch').checked?'true':'false');
  }
  [...$('#caseFiles').files].forEach(f=>fd.append('case_files',f));
  try{
    const j=await api('/api/jobs',{method:'POST',body:fd}); currentJob=j.job_id; lastEventId=-1;
    localStorage.setItem(LS.currentJob,currentJob); saveSettings();
    setTraceDownload(); log(`Job ${currentJob} 시작 · Notion 기존 ${exactRows.length} / 신규 생성 ${newRows.length}`); connectEvents(-1);
  }catch(e){log(e.message,'error');$('#startBtn').disabled=false;$('#cancelBtn').disabled=true;}
}


function companyBatchKey(r){return String(r.company||'UNKNOWN').trim().toLowerCase();}
function buildVercelBatches(rows,targetSize=8){
  const groups=new Map();
  for(const r of rows){const k=companyBatchKey(r);if(!groups.has(k))groups.set(k,[]);groups.get(k).push(r);}
  const batches=[];let cur=[];
  for(const g of groups.values()){
    if(cur.length && cur.length+g.length>targetSize){batches.push(cur);cur=[];}
    cur.push(...g);
    if(cur.length>=targetSize){batches.push(cur);cur=[];}
  }
  if(cur.length)batches.push(cur);
  return batches;
}
function buildRunFormData(rows,demo){
  const fd=new FormData();
  fd.append('file',selectedFile);fd.append('api_key',$('#apiKey').value.trim());fd.append('source_mode',$('#sourceMode').value);
  fd.append('max_leads','0');fd.append('selected_visitor_ids',JSON.stringify(rows.map(r=>r.visitor_id)));fd.append('excluded_visitor_ids','[]');
  fd.append('demo_mode',demo?'true':'false');fd.append('quick_mode',$('#quickMode').checked?'true':'false');
  fd.append('sender_name',$('#senderName').value);fd.append('sender_title',$('#senderTitle').value);fd.append('sender_signature',$('#senderSignature').value);
  fd.append('concurrency',String(Math.min(4,Math.max(1,Number($('#concurrency').value||2)))));fd.append('email_style_reference',$('#emailStyleReference').value);
  if(notionReady()){
    const c=notionConfig();fd.append('notion_api_key',c.api_key);fd.append('notion_database_url',c.database_url);
    fd.append('notion_auto_sync',$('#notionAutoSync').checked?'true':'false');fd.append('notion_reuse_research',$('#notionReuseResearch').checked?'true':'false');
  }
  [...$('#caseFiles').files].forEach(f=>fd.append('case_files',f));
  return fd;
}
async function consumeSseResponse(response,onEvent){
  if(!response.ok){let t=await response.text();try{t=JSON.parse(t).detail||t}catch{}throw new Error(t);}
  if(!response.body)throw new Error('Streaming response body가 없습니다.');
  const reader=response.body.getReader(),decoder=new TextDecoder();let buffer='';
  while(true){
    const {value,done}=await reader.read();if(done)break;
    buffer+=decoder.decode(value,{stream:true}).replace(/\r\n/g,'\n');
    let cut;
    while((cut=buffer.indexOf('\n\n'))>=0){
      const block=buffer.slice(0,cut);buffer=buffer.slice(cut+2);
      if(!block.trim()||block.startsWith(':'))continue;
      let event='message',id='';const data=[];
      for(const line of block.split('\n')){
        if(line.startsWith('event:'))event=line.slice(6).trim();
        else if(line.startsWith('id:'))id=line.slice(3).trim();
        else if(line.startsWith('data:'))data.push(line.slice(5).trimStart());
      }
      let payload={};const raw=data.join('\n');if(raw){try{payload=JSON.parse(raw)}catch{payload={message:raw}}}
      await onEvent(event,payload,id);
    }
  }
}
function updateSummaryFromAllLeads(){
  const c={total:0,quality:0,normal:0,trash:0,manual:0};
  for(const l of Object.values(leads)){c.total++;const k=String(l.classification||'').toLowerCase();if(k in c)c[k]++;if(['REQUIRED','PENDING'].includes(l.human_review_status))c.manual++;}
  for(const [k,id] of Object.entries({total:'countTotal',quality:'countQuality',normal:'countNormal',trash:'countTrash',manual:'countManual'}))setText('#'+id,c[k]??0);
}
async function runOneVercelBatch(rows,batchIndex,batchCount,demo){
  const fd=buildRunFormData(rows,demo);activeStreamAbort=new AbortController();let streamError=null;
  const response=await fetch('/api/run-stream',{method:'POST',body:fd,signal:activeStreamAbort.signal});
  await consumeSseResponse(response,async(event,x)=>{
    if(event==='progress'){
      const local=Math.max(0,Math.min(100,Number(x.progress||0)));const overall=((batchIndex+local/100)/batchCount)*100;
      updateProgress({progress:overall,stage:`배치 ${batchIndex+1}/${batchCount} · ${x.stage||'실행 중'}`,message:x.message||''});
    }else if(event==='log')log(x.message||'',x.level||'info');
    else if(event==='lead_update'&&x.lead){leads[x.lead.lead_id]=x.lead;updateSummaryFromAllLeads();renderLeads();renderReviews();}
    else if(event==='api_trace')appendApiTrace(x);
    else if(event==='error'){streamError=new Error(x.message||'Pipeline 오류');log(x.message||'Pipeline 오류','error');}
    else if(event==='completed'){log(`Vercel 배치 ${batchIndex+1}/${batchCount} 완료`);}
  });
  activeStreamAbort=null;if(streamError)throw streamError;
}
async function startVercelRuns(newRows,exactRows,targetRows,demo){
  const batches=buildVercelBatches(newRows,8);
  $('#cancelBtn').disabled=false;currentJob=null;localStorage.removeItem(LS.currentJob);saveSettings();
  apiTraceAll=[];setTraceDownload();
  log(`Vercel 모드 · 기존 Notion ${exactRows.length}건 / 신규 ${newRows.length}건 · ${batches.length}개 batch`);
  try{
    for(let i=0;i<batches.length;i++){
      if(!batches[i].length)continue;
      log(`배치 ${i+1}/${batches.length} 시작 · ${batches[i].length} rows`);
      await runOneVercelBatch(batches[i],i,batches.length,demo);
    }
    updateProgress({progress:100,stage:'완료',message:`신규 ${newRows.length} rows 처리 · Notion 기존 ${exactRows.length} rows 재사용`});
    updateSummaryFromAllLeads();renderLeads();renderReviews();renderDownloads();showSection('resultsSection');
    $('#startBtn').disabled=false;$('#cancelBtn').disabled=true;log('Vercel 전체 실행 완료 · 생성 결과는 Notion에 영속 저장됩니다.');
    if(notionReady()&&previewRows.length)await refreshNotionMatches();
  }catch(e){
    if(e?.name==='AbortError'){log('사용자가 실행을 중단했습니다.','warning');updateProgress({progress:Number($('#progressPct').textContent.replace('%',''))||0,stage:'중단됨',message:'브라우저에서 요청을 취소했습니다.'});}
    else{log(e.message||String(e),'error');updateProgress({progress:0,stage:'오류',message:e.message||String(e)});}
    $('#startBtn').disabled=false;$('#cancelBtn').disabled=true;activeStreamAbort=null;
  }
}

function connectEvents(after=-1){
  if(eventSource)eventSource.close();
  eventSource=new EventSource(`/api/jobs/${currentJob}/events?after=${encodeURIComponent(after)}`);
  const rememberId=e=>{if(e.lastEventId!==undefined&&e.lastEventId!=='')lastEventId=Math.max(lastEventId,Number(e.lastEventId));};
  eventSource.addEventListener('progress',e=>{rememberId(e);const x=JSON.parse(e.data);updateProgress(x);updateSummary(x.summary)});
  eventSource.addEventListener('log',e=>{rememberId(e);const x=JSON.parse(e.data);log(x.message,x.level)});
  eventSource.addEventListener('lead_update',e=>{rememberId(e);const x=JSON.parse(e.data);leads[x.lead.lead_id]=x.lead;updateSummary(x.summary);renderLeads();renderReviews()});
  eventSource.addEventListener('api_trace',e=>{rememberId(e);const x=JSON.parse(e.data);appendApiTrace(x);});
  eventSource.addEventListener('completed',e=>{rememberId(e);const x=JSON.parse(e.data);updateSummary(x.summary);updateProgress({progress:100,stage:'완료',message:'결과 생성 완료'});renderDownloads();$('#startBtn').disabled=false;$('#cancelBtn').disabled=true;eventSource.close();log('전체 파이프라인 완료');showSection('resultsSection')});
  eventSource.addEventListener('error',e=>{rememberId(e);try{const x=JSON.parse(e.data);log(x.message||'실행 오류','error')}catch{} });
  eventSource.addEventListener('cancelled',e=>{rememberId(e);$('#startBtn').disabled=false;$('#cancelBtn').disabled=true;eventSource.close();log('실행 취소됨','warning')});
}

function updateProgress(x={}){const p=Math.round(x.progress||0);const bar=$('#progressBar');if(bar)bar.style.width=p+'%';else uiWarn('#progressBar');setText('#progressPct',p+'%');setText('#stageLabel',x.stage||'실행 중');setText('#stageMessage',x.message||'');const text=(x.stage||'').toLowerCase();$$('#pipelineSteps span').forEach(s=>s.classList.toggle('active',text.includes((s.dataset.stage||'').toLowerCase())))}
function updateSummary(s={}){const c={total:Number(s?.total||0),quality:Number(s?.quality||0),normal:Number(s?.normal||0),trash:Number(s?.trash||0),manual:Number(s?.manual||0)};for(const l of Object.values(leads).filter(x=>x.loaded_from_notion)){c.total++;const k=String(l.classification||'').toLowerCase();if(k in c)c[k]++;if(l.human_review_status==='REQUIRED')c.manual++;}for(const [k,id] of Object.entries({total:'countTotal',quality:'countQuality',normal:'countNormal',trash:'countTrash',manual:'countManual'}))setText('#'+id,c[k]??0)}

$$('.filter').forEach(b=>b.onclick=()=>{currentFilter=b.dataset.filter;$$('.filter').forEach(x=>x.classList.toggle('active',x===b));saveSettings();renderLeads()});
function commercialBadge(l){const c=l.research?.commercial_attractiveness;if(!c)return '<span class="value-badge UNKNOWN">조사 중</span>';return `<span class="value-badge ${esc(c.level)}">${esc(c.level)}</span><small class="value-headline">${esc(c.headline||'')}</small>`}
function notionLeadTag(l){
  if(l.notion?.page_id){const label=l.loaded_from_notion?'Notion 로드':'Notion 저장';return `<span class="notion-result-tag">${label}${l.notion.page_url?` · <a href="${esc(l.notion.page_url)}" target="_blank">열기 ↗</a>`:''}</span>`;}
  if(l.notion_sync_error)return `<span class="notion-result-tag" style="color:#b91c1c">Notion 저장 실패</span>`;
  return '';
}
function renderLeads(){const list=Object.values(leads).filter(l=>currentFilter==='ALL'||l.classification===currentFilter).sort((a,b)=>(b.total_score||-1)-(a.total_score||-1));const tb=$('#leadTable');if(!list.length){tb.innerHTML='<tr class="placeholder"><td colspan="8">표시할 lead가 없다.</td></tr>';return}tb.innerHTML=list.map(l=>`<tr><td><span class="badge ${l.classification}">${esc(l.classification)}</span></td><td class="company-cell"><b>${esc(l.company)}</b><span>${esc(l.department||'부서 미상')}</span>${notionLeadTag(l)}</td><td class="commercial-cell">${commercialBadge(l)}</td><td>${l.member_count}</td><td><span class="score">${l.total_score??'–'}</span></td><td class="angle">${esc(l.strategy?.primary_angle||l.score_rationale||'처리 중')}</td><td class="mail-state">${l.draft?'초안 완료':'–'}${l.draft?.manual_edit?' · <b>수동 수정</b>':''} ${l.review?`· ${esc(l.review.decision)}`:''}${l.human_review_status==='REQUIRED'?'<br><b style="color:#5b21b6">사람 검수 필요</b>':''}</td><td><button class="view-btn" onclick="openLead('${l.lead_id}')">상세</button></td></tr>`).join('')}
function axisHtml(l){if(!l.score_axes)return '<span class="muted">아직 scoring 전</span>';const labels={account_potential:['Account Potential',25],contact_influence:['Contact Influence',20],declared_intent:['Declared Intent',20],agora_fit:['Agora Fit',20],recent_trigger:['Recent Trigger',10],evidence_quality:['Evidence Quality',5]};return Object.entries(labels).map(([k,[label,max]])=>{const a=l.score_axes[k];return `<div class="axis-row"><span>${label}</span><div class="axis-bar"><i style="width:${(a.score/max)*100}%"></i></div><b>${a.score}</b></div>`}).join('')}
function listHtml(items, empty='–'){return (items||[]).length?`<ul class="compact-list">${items.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`:`<span class="muted">${esc(empty)}</span>`}
function moneySnapshotHtml(r){if(!r)return '<span class="muted">처리 중</span>';const c=r.commercial_attractiveness||{};const rev=(r.revenue_history||[]).slice(0,3).map(x=>`<div><b>${esc(x.year)}</b><span>${esc(x.amount_text)}${x.scope?` · ${esc(x.scope)}`:''}${x.source_kind?` · ${esc(x.source_kind)}`:''}</span></div>`).join('')||'<span class="muted">공개 정보 확인 어려움</span>';const f=r.funding||{};const funding=f.applicable?[f.cumulative_funding&&`누적 ${f.cumulative_funding}`,f.latest_round&&`최근 ${f.latest_round}`,(f.major_investors||[]).length&&`투자자 ${(f.major_investors||[]).join(', ')}`].filter(Boolean).join(' · '):(f.note||'해당 없음 / 중요도 낮음');return `<div class="money-hero ${esc(c.level||'UNKNOWN')}"><div><span>영업가치 · COMMERCIAL ATTRACTIVENESS</span><strong>${esc(c.level||'UNKNOWN')}</strong></div><p>${esc(c.headline||'판단 중')}</p>${listHtml(c.reasons||[])}</div><div class="money-grid"><div class="money-card"><span>매출</span>${rev}</div><div class="money-card"><span>임직원</span><b>${esc(r.employee_snapshot||r.local_presence?.korea_employee_range||'공개 정보 확인 어려움')}</b></div><div class="money-card"><span>상장</span><b>${esc([r.listing_status,r.listing_market,r.ticker].filter(Boolean).join(' · ')||'공개 정보 확인 어려움')}</b></div><div class="money-card"><span>투자</span><b>${esc(funding)}</b></div></div>`}
function opportunityHtml(title,items,empty){const xs=items||[];return `<div class="opp-column"><h5>${esc(title)}</h5>${xs.length?xs.map(x=>`<div class="opp-item"><div><b>${esc(x.rank)}. ${esc(x.service_or_workflow)}</b><span>${Math.round((x.fit_confidence||0)*100)}% fit</span></div><strong>${esc(x.recommended_product)}</strong><p>${esc(x.idea)}</p></div>`).join(''):`<span class="muted">${esc(empty)}</span>`}</div>`}
function researchDetailHtml(r,sources){if(!r)return '<pre>처리 중</pre>';const businesses=(r.main_businesses||[]).map(x=>`${x.name}${x.description?` — ${x.description}`:''}`);const signals=(r.signals||[]).map(x=>`${x.date||'date n/a'} · ${x.topic}: ${x.summary}`);const productCheck=r.agora_product_check||{};return `${moneySnapshotHtml(r)}<div class="research-section"><h5>EXECUTIVE SUMMARY</h5>${listHtml(r.executive_summary||[])}</div><div class="research-grid"><div><h5>회사</h5><p><b>${esc(r.official_company_name||'')}</b><br>${esc(r.one_line_description||r.summary||'')}</p></div><div><h5>한국 사업</h5><p>${esc(r.local_presence?.korea_role||'공개 정보 확인 어려움')}</p></div></div><div class="research-section"><h5>주력 사업</h5>${listHtml(businesses)}</div><div class="opportunity-grid">${opportunityHtml('Agora RTC 적용 가능성',r.rtc_opportunities,'뚜렷한 RTC 적용 기회 확인 어려움')}${opportunityHtml('Agora AI 적용 가능성',r.ai_opportunities,'뚜렷한 AI 적용 기회 확인 어려움')}</div><div class="research-section"><h5>RECENT SIGNALS</h5>${listHtml(signals,'뚜렷한 최근 signal 확인 어려움')}</div><div class="research-section product-check"><h5>AGORA PRODUCT CHECK</h5><p>${productCheck.checked?'✓ 공식 Agora 제품 페이지/Documentation 확인':'⚠ 공식 Agora 제품 source 재확인 필요'} · ${esc(productCheck.summary||'')}</p>${(productCheck.official_source_urls||[]).map(u=>`<a href="${esc(u)}" target="_blank" rel="noreferrer">${esc(u)}</a>`).join('')}</div><div class="sources"><h5>SOURCES</h5>${sources}</div>`}
window.openLead=function(id){const l=leads[id];if(!l)return;const badge=$('#dialogBadge');if(badge){badge.className='badge '+l.classification;badge.textContent=l.classification;}setText('#dialogTitle',`${l.company} · ${l.department||'부서 미상'}`);const sources=(l.research?.evidence||[]).map(e=>`<a href="${esc(e.url)}" target="_blank" rel="noreferrer">${esc(e.title||e.url)}</a>`).join('')||'<span class="muted">–</span>';const manualNote=l.draft?.manual_edit?'수동 수정본이 저장되어 있으며 다운로드 결과에도 반영됩니다.':(l.review_outdated_by_manual_edit?'수동 수정으로 기존 AI Review가 이전 초안 기준입니다.':'생성 초안을 직접 수정한 뒤 저장할 수 있습니다.');setHtml('#dialogBody',`<div class="detail-grid"><div class="detail-block"><h4>LEAD SCORE</h4>${axisHtml(l)}<p>${esc(l.score_rationale||'')}</p></div><div class="detail-block"><h4>MEMBERS</h4>${(l.members||[]).map(m=>`<p><b>${esc(m.name||'')}</b> · ${esc(m.title||'')}<br><span class="muted">${esc(m.email||'')}</span></p>`).join('')}</div><div class="detail-block full research-block"><h4>ACCOUNT RESEARCH</h4>${researchDetailHtml(l.research,sources)}</div><div class="detail-block"><h4>SALES STRATEGY</h4><pre>${esc(l.strategy?`${l.strategy.primary_angle}\n\n${l.strategy.email_brief}`:'처리 중')}</pre></div><div class="detail-block"><h4>REVIEW</h4><pre>${esc(l.review?`Score ${l.review.total_score} · ${l.review.decision}\n${(l.review.issues||[]).map(i=>'- '+i.description).join('\n')}`:'처리 중')}</pre></div><div class="detail-block full draft-edit-block"><div class="draft-edit-head"><div><h4>EMAIL DRAFT · 직접 수정 가능</h4><p>${esc(manualNote)}</p></div><span id="draftSaveStatus"></span></div>${l.draft?`<label class="draft-field"><span>제목</span><input id="draftSubjectEditor" type="text" /></label><label class="draft-field"><span>메일 본문</span><textarea id="draftBodyEditor" rows="18" spellcheck="true"></textarea></label><div class="draft-actions"><button class="primary draft-save" type="button" onclick="saveDraft('${l.lead_id}')">수정 내용 저장</button><small>기업 맥락·유즈케이스·문구를 자유롭게 직접 보완할 수 있습니다. 저장본이 최종 CSV/XLSX에 반영됩니다.</small></div>`:'<span class="muted">아직 생성 전</span>'}</div></div>`);if(l.draft){const si=$('#draftSubjectEditor'),bi=$('#draftBodyEditor');if(si)si.value=l.draft.subject_primary||'';if(bi)bi.value=l.draft.full_email||'';}$('#leadDialog').showModal()};
window.saveDraft=async function(id){
  const l=leads[id];if(!l)return;
  const subject=$('#draftSubjectEditor')?.value||'';const full_email=$('#draftBodyEditor')?.value||'';const st=$('#draftSaveStatus');
  if(st){st.textContent='저장 중…';st.className='saving';}
  try{
    let x;
    if(l.notion?.page_id){
      if(!notionReady())throw new Error('Notion 저장본을 수정하려면 Notion API Key를 다시 입력하세요.');
      const c=notionConfig();
      x=await api(`/api/notion/pages/${encodeURIComponent(l.notion.page_id)}/draft`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({...c,page_id:l.notion.page_id,subject,full_email})});
    }else{
      if(!currentJob)throw new Error('현재 로컬 Job을 찾지 못했습니다.');
      const c=notionConfig();
      x=await api(`/api/jobs/${currentJob}/leads/${id}/draft`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({subject,full_email,notion_api_key:c.api_key||null,notion_database_url:c.database_url||null,sync_to_notion:notionReady()})});
    }
    leads[id]=x.lead;renderLeads();renderReviews();
    if(st){st.textContent=x.notion?'저장됨 · Notion 업데이트':'저장됨';st.className='saved';}
    log(`${x.lead.company}: 메일 수정본 저장${x.notion?' + Notion 동기화':''}`);
    if(notionReady()&&previewRows.length)refreshNotionMatches();
  }catch(e){if(st){st.textContent='저장 실패';st.className='error';}alert(e.message)}
};

$('#dialogClose').onclick=()=>$('#leadDialog').close();

function renderReviews(){
  const qs=Object.values(leads).filter(l=>l.classification==='QUALITY');const box=$('#reviewCards');
  if(!qs.length){box.innerHTML='<div class="empty-card">Quality lead가 생성되면 여기에 나타난다.</div>';return}
  box.innerHTML=qs.sort((a,b)=>(b.total_score||0)-(a.total_score||0)).map(l=>{
    const canPersist=!!l.notion?.page_id&&notionReady();
    const actions=`${canPersist?`<button class="approve" onclick="humanReview('${l.lead_id}','APPROVED')">승인</button><button class="reject" onclick="humanReview('${l.lead_id}','REJECTED')">반려</button>`:''}<button class="view-btn" onclick="openLead('${l.lead_id}')">상세 / 수정</button>${l.notion?.page_url?`<a class="view-btn notion-open-btn" href="${esc(l.notion.page_url)}" target="_blank">Notion ↗</a>`:''}`;
    return `<div class="review-card"><span class="badge QUALITY">QUALITY · ${l.total_score??'–'}</span><h3>${esc(l.company)}</h3><div class="meta">${esc(l.department||'')} · ${l.member_count}명 · ${esc(l.human_review_status)}${l.notion?.page_id?' · Notion 저장됨':''}</div><div class="mail-preview">${esc(l.draft?.full_email||'메일 생성 중…')}</div><div class="review-actions">${actions}</div></div>`;
  }).join('')
}
window.humanReview=async function(id,status){
  const l=leads[id];if(!l)return;const note=status==='REJECTED'?prompt('반려 사유 (선택)')||'':null;
  try{
    let x;
    if(l.notion?.page_id&&notionReady()){
      const c=notionConfig();
      x=await api(`/api/notion/pages/${encodeURIComponent(l.notion.page_id)}/human-review`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...c,page_id:l.notion.page_id,status,note})});
    }else if(deploymentMode==='local'&&currentJob){
      x=await api(`/api/jobs/${currentJob}/leads/${id}/human-review`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({status,note})});
    }else{
      l.human_review_status=status;l.human_review_note=note||'';x={lead:l};log('검수 상태는 현재 브라우저에만 반영되었습니다. Notion을 연결하면 영속 저장할 수 있습니다.','warning');
    }
    leads[id]=x.lead;renderReviews();renderLeads();updateSummaryFromAllLeads();log(`${x.lead.company}: ${status}${x.notion?' + Notion 저장':''}`);
  }catch(e){alert(e.message)}
};

function prettyJson(v){try{return JSON.stringify(v,null,2)}catch{return String(v??'')}}
function traceTitle(t){const phase=(t.phase||'').toUpperCase();const icon=t.phase==='request'?'→':t.phase==='response'?'←':t.phase==='error'?'!':'↻';return `${icon} ${t.agent||'API'} · ${phase}`}
function traceCardHtml(t){const meta=[t.model,t.duration_sec!=null?`${t.duration_sec}s`:null,t.web_search?'web search':null,t.attempt&&t.attempt>1?`attempt ${t.attempt}`:null].filter(Boolean).join(' · ');let detail='';if(t.phase==='request'){detail=`<div class="trace-section"><b>SYSTEM PROMPT</b><pre>${esc(t.system_prompt||'')}</pre></div><div class="trace-section"><b>USER PAYLOAD</b><pre>${esc(prettyJson(t.user_payload))}</pre></div>`}else if(t.phase==='response'){const src=(t.sources||[]).map(s=>`<a href="${esc(s.url)}" target="_blank" rel="noreferrer">${esc(s.title||s.url)}</a>`).join('');detail=`<div class="trace-section"><b>STRUCTURED OUTPUT</b><pre>${esc(prettyJson(t.parsed))}</pre></div>${src?`<div class="trace-section"><b>WEB SOURCES</b><div class="trace-sources">${src}</div></div>`:''}<div class="trace-section"><b>USAGE</b><pre>${esc(prettyJson(t.usage||{}))}</pre></div>`}else{detail=`<div class="trace-section"><pre>${esc(t.message||prettyJson(t))}</pre></div>`}return `<details class="api-trace-card ${esc(t.phase||'')}"><summary><div><b>${esc(traceTitle(t))}</b><span>${esc(meta)}</span></div><time>${new Date((t.ts||Date.now()/1000)*1000).toLocaleTimeString()}</time></summary>${detail}</details>`}
function renderApiTraces(){const box=$('#apiTranscript');box.innerHTML='';if(!apiTraces.length){box.innerHTML='<div class="api-empty">실제 API 호출이 시작되면 요청/응답이 순서대로 표시된다.</div>';return;}const frag=document.createDocumentFragment();apiTraces.slice(-250).forEach(t=>{const wrap=document.createElement('div');wrap.innerHTML=traceCardHtml(t);frag.appendChild(wrap.firstElementChild)});box.appendChild(frag);if($('#autoFollowTrace').checked)box.scrollTop=box.scrollHeight;}
function appendApiTrace(t){const box=$('#apiTranscript');const shouldFollow=$('#autoFollowTrace').checked || (box.scrollHeight-box.scrollTop-box.clientHeight<80);apiTraceAll.push(t);apiTraces.push(t);if(apiTraces.length>250)apiTraces=apiTraces.slice(-250);if(box.querySelector('.api-empty'))box.innerHTML='';const wrap=document.createElement('div');wrap.innerHTML=traceCardHtml(t);box.appendChild(wrap.firstElementChild);while(box.children.length>250)box.removeChild(box.firstElementChild);if(shouldFollow)requestAnimationFrame(()=>{box.scrollTop=box.scrollHeight});}
$('#clearApiTrace').onclick=()=>{apiTraces=[];apiTraceAll=[];renderApiTraces();setTraceDownload()};
function browserDownload(name,text,type='application/json'){
  const blob=new Blob([text],{type});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=name;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1500);
}
function csvCell(v){const s=String(v??'');return /[",\n]/.test(s)?`"${s.replace(/"/g,'""')}"`:s;}
window.downloadVercelResult=function(kind){
  if(kind==='trace'){browserDownload('api_trace.json',JSON.stringify(apiTraceAll,null,2));return false;}
  const rows=Object.values(leads);if(kind==='json'){browserDownload('final_leads.json',JSON.stringify(leads,null,2));return false;}
  if(kind==='csv'){
    const fields=['lead_id','company','department','classification','total_score','commercial_value','recipient_names','recipient_emails','subject','email_body','human_review_status','notion_url'];
    const lines=[fields.join(',')];for(const l of rows){const r={lead_id:l.lead_id,company:l.company,department:l.department,classification:l.classification,total_score:l.total_score,commercial_value:l.research?.commercial_attractiveness?.level||'',recipient_names:(l.members||[]).map(m=>m.name).filter(Boolean).join(' | '),recipient_emails:(l.members||[]).map(m=>m.email).filter(Boolean).join(' | '),subject:l.draft?.subject_primary||'',email_body:l.draft?.full_email||'',human_review_status:l.human_review_status||'',notion_url:l.notion?.page_url||''};lines.push(fields.map(f=>csvCell(r[f])).join(','));}
    browserDownload('final_leads.csv','\ufeff'+lines.join('\n'),'text/csv;charset=utf-8');return false;
  }
  return false;
};
function setTraceDownload(){
  const a=$('#downloadTraceJson');if(!a)return;
  if(deploymentMode==='vercel'){
    a.href='#';a.onclick=()=>downloadVercelResult('trace');a.classList.toggle('disabled',!apiTraceAll.length);return;
  }
  a.onclick=null;if(!currentJob){a.classList.add('disabled');a.removeAttribute('href');return;}a.href=`/api/jobs/${currentJob}/download/api_trace.json`;a.classList.remove('disabled');
}
function renderDownloads(){
  if(deploymentMode==='vercel'){
    $('#downloadRow').innerHTML=`<a href="#" onclick="return downloadVercelResult('csv')">↓ CSV</a><a href="#" onclick="return downloadVercelResult('json')">↓ 결과 JSON</a><a href="#" onclick="return downloadVercelResult('trace')">↓ API Transcript JSON</a><span class="muted">Vercel에서는 Notion이 영속 저장소입니다.</span>`;setTraceDownload();return;
  }
  if(!currentJob)return;const files=[['final_leads.xlsx','Excel'],['final_leads.csv','전체 CSV'],['quality_sales.csv','Quality'],['normal_sales.csv','Normal'],['trash_accounts.csv','Trash'],['manual_review.csv','검수 대상'],['api_trace.json','API Transcript JSON'],['artifacts.zip','전체 Artifacts']];$('#downloadRow').innerHTML=files.map(([f,n])=>`<a href="/api/jobs/${currentJob}/download/${f}">↓ ${n}</a>`).join('');setTraceDownload();
}

async function restoreJob(){
  const jid=localStorage.getItem(LS.currentJob); if(!jid)return;
  try{
    const j=await api(`/api/jobs/${jid}`); currentJob=jid; lastEventId=j.last_event_id??-1; leads=Object.fromEntries((j.leads||[]).map(l=>[l.lead_id,l]));
    updateProgress(j); updateSummary(j.summary); renderLeads(); renderReviews(); setTraceDownload();
    try{const tr=await api(`/api/jobs/${jid}/api-trace`);apiTraces=(tr.items||[]).slice(-250);renderApiTraces();}catch{}
    log(`이전 Job ${jid} 복구: ${j.status}`);
    if(j.status==='running'||j.status==='queued'){ $('#cancelBtn').disabled=false; connectEvents(lastEventId); }
    else { $('#cancelBtn').disabled=true; if(j.status==='completed')renderDownloads(); }
  }catch(e){ localStorage.removeItem(LS.currentJob); currentJob=null; log('이전 backend Job을 복구하지 못했습니다. 서버가 재시작되었을 수 있습니다.','warning'); }
}

$('#clearLocalCache').onclick=()=>{
  if(!confirm('이 브라우저에 저장된 설정, 선택 row, 메일 참고 메모, Job 연결정보, 저장된 OpenAI/Notion API Key(선택 저장 시)를 모두 지울까요?'))return;
  Object.values(LS).forEach(k=>localStorage.removeItem(k));
  if(eventSource)eventSource.close(); selectedVisitorIds.clear(); previewRows=[]; currentJob=null; leads={}; apiTraces=[];
  location.reload();
};

window.addEventListener('error',e=>{
  console.error('Frontend error:',e.error||e.message);
  const msg=e?.message||'알 수 없는 프론트 오류';
  if(msg.includes('Cannot set properties of null')){
    log('화면 요소 동기화 오류를 감지했습니다. v1.6은 stale static cache를 차단합니다. 한 번 새로고침 후 다시 시도하세요.','error');
  }
});

async function init(){
  await health(); restoreSettings(); restorePreviewCache();
  const section=localStorage.getItem(LS.section)||'runSection'; showSection(section,false);
  updateLaunchState();
  if(notionReady() && previewRows.length){
    try{ await testNotionConnection(true); }catch{}
  }
  if(deploymentMode==='local') await restoreJob();
  else { localStorage.removeItem(LS.currentJob); currentJob=null; setTraceDownload(); }
}
init();
