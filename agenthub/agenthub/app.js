(function(){
'use strict';

/* =====================================================================
   0. 데이터 (실제 프로젝트에서는 fetch('/api/agents') 등 백엔드 호출로 교체)
   ===================================================================== */
var TODAY='2026-11-15';
var CATS=['개발','문서·요약','데이터','업무 자동화','고객지원','번역'];
function mk(v,date,notes,size,status){return {v:v,date:date,notes:notes,size:size,status:status||'stable'};}

var agents=[
 {id:'code-reviewer',name:'코드리뷰 에이전트',publisher:'DevPilot 팀',category:'개발',
  summary:'PR의 변경 사항을 읽고 버그 위험과 스타일 문제를 코멘트로 남깁니다.',
  description:'GitHub PR의 diff를 분석해 null 처리 누락, 예외 흐름, 네이밍 규칙 위반을 찾아 줄 단위 코멘트를 작성합니다. 팀 코딩 컨벤션 파일을 읽어 규칙을 맞출 수 있습니다.',
  tools:['diff 분석','린트 규칙 점검','리뷰 코멘트 생성','컨벤션 파일 로드'],tags:['GitHub','코드리뷰','Python'],license:'MIT',compat:'Python 3.10+',rating:4.7,reviews:128,downloads:5230,
  versions:[mk('1.3.0','2026-11-02','대용량 PR을 파일 단위로 나눠 분석하도록 개선했습니다. 리뷰 속도가 약 40% 빨라졌습니다.',412),mk('1.2.1','2026-10-14','한글 주석이 포함된 파일에서 인코딩 오류가 나던 문제를 수정했습니다.',398),mk('1.2.0','2026-09-21','타입 힌트 점검 규칙을 추가했습니다.',395),mk('1.0.0','2026-08-03','첫 공개 버전입니다.',360,'deprecated')]},
 {id:'paper-summarizer',name:'논문 요약 에이전트',publisher:'리서치랩',category:'문서·요약',
  summary:'PDF 논문을 읽고 연구 목적, 방법, 결과를 한 장으로 정리합니다.',
  description:'논문 PDF에서 초록, 방법론, 실험 결과를 추출해 구조화된 요약을 만듭니다. 참고문헌 목록과 핵심 인용 문장도 함께 정리합니다.',
  tools:['PDF 파싱','섹션 구분','핵심 인용 추출','참고문헌 정리'],tags:['논문','PDF','요약'],license:'Apache-2.0',compat:'Python 3.10+',rating:4.8,reviews:212,downloads:7810,
  versions:[mk('2.1.0','2026-10-28','2단 편집 논문에서 표 추출 정확도를 높였습니다.',640),mk('2.0.0','2026-09-05','요약 형식을 목적·방법·결과·한계 4단 구조로 바꿨습니다.',622),mk('1.4.2','2026-07-19','긴 논문에서 메모리 사용량이 늘던 문제를 수정했습니다.',580)]},
 {id:'sql-helper',name:'SQL 도우미',publisher:'DataDesk',category:'데이터',
  summary:'자연어 질문을 SQL로 바꾸고, 실행 전에 쿼리 비용을 점검합니다.',
  description:'스키마 정보를 읽고 질문에 맞는 SELECT 문을 만듭니다. 풀 스캔이나 조인 폭증처럼 비용이 큰 쿼리는 실행 전에 경고합니다.',
  tools:['스키마 로드','SQL 생성','실행 계획 점검','결과 요약'],tags:['SQL','PostgreSQL','MySQL'],license:'MIT',compat:'Node 20+',rating:4.4,reviews:96,downloads:3490,
  versions:[mk('1.1.0','2026-10-09','MySQL 8 방언을 지원합니다.',310),mk('1.0.1','2026-09-12','JOIN 별칭이 중복될 때 생기던 오류를 수정했습니다.',298),mk('1.0.0','2026-08-30','첫 공개 버전입니다.',295,'deprecated')]},
 {id:'meeting-notes',name:'회의록 에이전트',publisher:'내 팀',category:'업무 자동화',mine:true,
  summary:'회의 녹취 텍스트에서 결정 사항과 담당자별 할 일을 뽑아 정리합니다.',
  description:'캡스톤 팀 회의 녹취록을 입력하면 안건별 요약, 결정 사항, 담당자와 기한이 있는 할 일 목록을 만들어 줍니다. 팀 위키에 붙여넣기 좋은 마크다운으로 내보냅니다.',
  tools:['안건 분리','결정 사항 추출','할 일 목록 생성','마크다운 내보내기'],tags:['회의','마크다운','팀 협업'],license:'MIT',compat:'Python 3.10+',rating:4.5,reviews:18,downloads:342,
  versions:[mk('0.3.0','2026-11-10','담당자 이름 인식 정확도를 높였습니다.',188),mk('0.2.0','2026-11-01','할 일 목록에 기한 항목을 추가했습니다.',176),mk('0.1.0','2026-10-20','프로토타입 버전입니다.',160)]},
 {id:'ticket-triage',name:'문의 분류 에이전트',publisher:'CareFlow',category:'고객지원',
  summary:'들어온 고객 문의를 유형과 긴급도로 분류하고 담당 팀에 배정합니다.',
  description:'이메일과 채팅 문의를 읽고 결제, 배송, 계정, 기술 문의로 분류합니다. 긴급도를 판단해 담당 팀 큐에 배정하고 첫 응답 초안을 만듭니다.',
  tools:['문의 유형 분류','긴급도 판단','담당 팀 배정','응답 초안 작성'],tags:['CS','분류','이메일'],license:'Apache-2.0',compat:'Python 3.9+',rating:4.2,reviews:57,downloads:2105,
  versions:[mk('1.5.2','2026-10-30','환불 키워드 분류 오류를 수정했습니다.',274),mk('1.5.0','2026-10-02','긴급도 판단 기준을 팀별로 설정할 수 있습니다.',270)]},
 {id:'schedule-mate',name:'일정 조율 에이전트',publisher:'TimeBox',category:'업무 자동화',
  summary:'참석자들의 캘린더를 비교해 모두가 가능한 회의 시간을 제안합니다.',
  description:'여러 사람의 가능 시간대를 입력받아 겹치는 시간을 찾고, 선호도에 따라 상위 3개 후보를 제안합니다. 시간대가 다른 참석자도 지원합니다.',
  tools:['가능 시간 비교','후보 3개 제안','시간대 변환'],tags:['캘린더','일정','회의'],license:'MIT',compat:'Node 20+',rating:4.0,reviews:41,downloads:1560,
  versions:[mk('0.9.1','2026-10-18','서머타임 전환 구간 계산을 수정했습니다.',142),mk('0.9.0','2026-09-27','시간대가 다른 참석자 지원을 추가했습니다.',139)]},
 {id:'translate-review',name:'번역 감수 에이전트',publisher:'로컬라이즈',category:'번역',
  summary:'기계 번역 결과를 원문과 대조해 오역과 어색한 표현을 표시합니다.',
  description:'원문과 번역문을 문장 단위로 맞춰 보고 의미가 달라진 부분, 용어 불일치, 어색한 문체를 표시합니다. 용어집을 올리면 일관성도 점검합니다.',
  tools:['문장 정렬','오역 탐지','용어집 일관성 점검'],tags:['번역','감수','영한'],license:'MIT',compat:'Python 3.10+',rating:4.6,reviews:73,downloads:2890,
  versions:[mk('1.2.0','2026-10-22','일본어와 중국어 번역문 감수를 지원합니다.',356),mk('1.1.0','2026-09-15','용어집 CSV 업로드를 지원합니다.',340)]},
 {id:'chart-maker',name:'차트 생성 에이전트',publisher:'DataDesk',category:'데이터',
  summary:'CSV를 올리면 데이터 성격에 맞는 차트를 골라 그려 줍니다.',
  description:'CSV 열의 자료형을 판별해 시계열은 선 차트, 범주 비교는 막대 차트처럼 적합한 형태를 고릅니다. 결과는 PNG와 SVG로 내려받을 수 있습니다.',
  tools:['자료형 판별','차트 유형 추천','PNG·SVG 내보내기'],tags:['CSV','시각화','차트'],license:'MIT',compat:'Python 3.10+',rating:4.3,reviews:64,downloads:2240,
  versions:[mk('1.0.2','2026-10-25','한글 축 라벨이 깨지던 문제를 수정했습니다.',502),mk('1.0.0','2026-09-30','첫 공개 버전입니다.',490)]}
];

// 내가 내려받은 에이전트 (샘플 상태)
var state={q:'',cat:'전체',sort:'popular',tab:'overview',
  dl:{'code-reviewer':{version:'1.2.1',at:'2026-10-20'},'paper-summarizer':{version:'2.1.0',at:'2026-11-03'},'sql-helper':{version:'1.0.0',at:'2026-09-01'}},
  file:null,tags:[],submitted:false};

/* =====================================================================
   1. 유틸
   ===================================================================== */
var app=document.getElementById('app');
function esc(s){return String(s).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
function find(id){return agents.filter(function(a){return a.id===id;})[0];}
function num(n){return n.toLocaleString('ko-KR');}
function size(kb){return kb>=1024?(kb/1024).toFixed(1)+' MB':kb+' KB';}
function isSemver(v){return /^\d+\.\d+\.\d+$/.test(v);}
function cmp(a,b){var x=a.split('.').map(Number),y=b.split('.').map(Number);for(var i=0;i<3;i++){if(x[i]!==y[i])return x[i]-y[i];}return 0;}
function latest(a){return a.versions.filter(function(v){return v.status!=='deprecated';})[0]||a.versions[0];}
function highest(a){return a.versions.map(function(v){return v.v;}).sort(cmp).pop();}
function stateOf(a){var d=state.dl[a.id];if(!d)return null;var l=latest(a);var cur=a.versions.filter(function(v){return v.v===d.version;})[0];
  if(cur&&cur.status==='deprecated')return 'deprecated';return cmp(d.version,l.v)<0?'outdated':'current';}
function updateCount(){return agents.filter(function(a){var s=stateOf(a);return s==='outdated'||s==='deprecated';}).length;}
var toastTimer;
function toast(msg){var t=document.getElementById('toast');t.textContent=msg;t.classList.add('show');clearTimeout(toastTimer);toastTimer=setTimeout(function(){t.classList.remove('show');},2400);}
function stars(r){return '★ '+r.toFixed(1);}
var SEARCH_ICON='<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg>';

/* =====================================================================
   2. 에이전트 카드 (목록·미리보기 공용 컴포넌트)
   ===================================================================== */
function cardHTML(a,preview){
  var inner='<div class="card-head"><span class="tile">'+esc((a.name||'?').trim().charAt(0)||'?')+'</span><div style="min-width:0"><h3>'+esc(a.name||'에이전트 이름')+'</h3><p class="muted" style="font-size:.85rem">'+esc(a.publisher)+' · '+esc(a.category)+'</p></div></div>'
   +'<p class="sum">'+esc(a.summary||'한 줄 소개가 여기에 표시됩니다.')+'</p>'
   +'<div class="tags">'+(a.tags||[]).slice(0,3).map(function(t){return '<span class="tag">'+esc(t)+'</span>';}).join('')+'</div>'
   +'<div class="card-foot"><span>'+stars(a.rating)+'</span><span>↓ '+num(a.downloads)+'</span><span class="mono ver">v'+esc(latest(a).v)+'</span></div>';
  return preview?'<div class="card">'+inner+'</div>':'<a class="card" href="#agent-'+a.id+'">'+inner+'</a>';
}

/* =====================================================================
   3. [화면 ①] 에이전트 검색·목록
   ===================================================================== */
function viewBrowse(){
  var total=agents.reduce(function(s,a){return s+a.downloads;},0);
  app.innerHTML='<section class="hero"><div><h1>에이전트 마켓플레이스</h1><p class="muted" style="margin-top:6px">등록된 에이전트 '+agents.length+'개 · 누적 다운로드 '+num(total)+'회</p></div>'
   +'<div class="search"><label for="q" class="sr" style="position:absolute;left:-9999px">에이전트 검색</label>'+SEARCH_ICON+'<input id="q" type="search" placeholder="이름, 설명, 태그로 검색" autocomplete="off"></div></section>'
   +'<div class="filters"><div class="chips" id="chips"></div><label class="sortbox">정렬<select id="sort"><option value="popular">인기순</option><option value="rating">평점순</option><option value="recent">최근 업데이트순</option><option value="name">이름순</option></select></label></div>'
   +'<p class="muted" id="count" style="margin-bottom:12px;font-size:.9rem"></p><div class="grid" id="results"></div>';
  var q=document.getElementById('q'),sort=document.getElementById('sort');
  q.value=state.q;sort.value=state.sort;
  q.addEventListener('input',function(){state.q=q.value;paintResults();});
  sort.addEventListener('change',function(){state.sort=sort.value;paintResults();});
  paintChips();paintResults();
}
function paintChips(){
  document.getElementById('chips').innerHTML=['전체'].concat(CATS).map(function(c){
    return '<button class="chip" type="button" data-act="cat" data-cat="'+esc(c)+'" aria-pressed="'+(state.cat===c)+'">'+esc(c)+'</button>';}).join('');
}
function paintResults(){
  var q=state.q.trim().toLowerCase();
  var list=agents.filter(function(a){
    if(state.cat!=='전체'&&a.category!==state.cat)return false;
    if(!q)return true;
    return (a.name+' '+a.summary+' '+a.publisher+' '+a.tags.join(' ')).toLowerCase().indexOf(q)>-1;});
  var s=state.sort;
  list.sort(function(a,b){
    if(s==='rating')return b.rating-a.rating;
    if(s==='recent')return latest(b).date<latest(a).date?-1:1;
    if(s==='name')return a.name.localeCompare(b.name,'ko');
    return b.downloads-a.downloads;});
  document.getElementById('count').textContent='검색 결과 '+list.length+'개';
  document.getElementById('results').innerHTML=list.length?list.map(function(a){return cardHTML(a);}).join('')
    :'<div class="empty" style="grid-column:1/-1">조건에 맞는 에이전트가 없습니다.<br>검색어를 줄이거나 다른 분류를 선택해 보세요.</div>';
}

/* =====================================================================
   4. [화면 ②] 에이전트 상세 정보
   ===================================================================== */
function viewDetail(a){
  var l=latest(a),st=stateOf(a),d=state.dl[a.id];
  var installed=d?'<div class="installed"><span class="badge '+(st==='current'?'ok':'warn')+'">설치됨 v'+esc(d.version)+'</span>'+(st==='outdated'?'<span class="warn" style="color:var(--warn)">v'+esc(l.v)+' 업데이트 가능</span>':'')+(st==='deprecated'?'<span style="color:var(--warn)">지원 중단 버전입니다</span>':'')+'</div>':'';
  app.innerHTML='<a class="crumb" href="#browse">← 목록으로</a>'
   +'<div class="d-head"><span class="tile">'+esc(a.name.charAt(0))+'</span>'
   +'<div class="d-title"><h1>'+esc(a.name)+'</h1><p class="muted">'+esc(a.publisher)+' · '+esc(a.category)+(a.mine?' · <span class="badge ok">내가 등록함</span>':'')+'</p>'
   +'<p class="muted" style="font-size:.9rem">'+stars(a.rating)+' ('+num(a.reviews)+'개 평가) · 다운로드 '+num(a.downloads)+'회</p></div>'
   +'<div class="d-cta"><div class="row"><select id="ver-select" aria-label="다운로드할 버전">'+a.versions.map(function(v){return '<option value="'+esc(v.v)+'">v'+esc(v.v)+(v===l?' (최신)':'')+(v.status==='deprecated'?' · 지원 중단':'')+'</option>';}).join('')+'</select>'
   +'<button class="btn primary" type="button" data-act="dl-select" data-id="'+a.id+'">다운로드</button></div>'+installed+'</div></div>'
   +'<div class="d-grid"><div><div class="tabs" role="tablist">'
   +[['overview','개요'],['versions','버전 관리'],['install','설치 방법']].map(function(t){return '<button class="tab" role="tab" type="button" data-act="tab" data-tab="'+t[0]+'" aria-selected="'+(state.tab===t[0])+'">'+t[1]+'</button>';}).join('')
   +'</div><div id="panel" data-id="'+a.id+'"></div></div>'
   +'<aside class="panel"><h2 style="margin-bottom:14px;font-size:1rem">정보</h2><dl class="facts">'
   +'<dt>최신 버전</dt><dd class="mono">v'+esc(l.v)+'</dd><dt>최종 업데이트</dt><dd>'+esc(l.date)+'</dd><dt>패키지 크기</dt><dd>'+size(l.size)+'</dd>'
   +'<dt>라이선스</dt><dd>'+esc(a.license)+'</dd><dt>실행 환경</dt><dd>'+esc(a.compat)+'</dd><dt>게시자</dt><dd>'+esc(a.publisher)+'</dd></dl>'
   +'<div class="tags" style="margin-top:16px">'+a.tags.map(function(t){return '<span class="tag">'+esc(t)+'</span>';}).join('')+'</div></aside></div>';
  paintPanel(a);
}
function paintPanel(a){
  var p=document.getElementById('panel');
  p.innerHTML=state.tab==='versions'?panelVersions(a):state.tab==='install'?panelInstall(a):panelOverview(a);
  Array.prototype.forEach.call(document.querySelectorAll('.tab'),function(b){b.setAttribute('aria-selected',String(b.getAttribute('data-tab')===state.tab));});
}
function panelOverview(a){
  var l=latest(a);
  var manifest=JSON.stringify({name:a.id,version:l.v,entry:'main.py',runtime:a.compat,tools:a.tools,license:a.license},null,2);
  return '<div class="stack"><section class="panel"><h2 style="margin-bottom:10px">소개</h2><p>'+esc(a.description)+'</p></section>'
   +'<section class="panel"><h2 style="margin-bottom:12px">주요 기능</h2><ul class="feat">'+a.tools.map(function(t){return '<li>'+esc(t)+'</li>';}).join('')+'</ul></section>'
   +'<section class="panel"><h2 style="margin-bottom:12px">manifest.json</h2><pre>'+esc(manifest)+'</pre></section></div>';
}
function panelInstall(a){
  var l=latest(a);
  var c1='agenthub install '+a.id,c2='agenthub install '+a.id+'@'+l.v,c3='agenthub update '+a.id;
  function blk(label,c){return '<div class="stack" style="gap:8px"><div class="row" style="justify-content:space-between"><span class="lbl">'+label+'</span><button class="btn sm" type="button" data-act="copy" data-text="'+esc(c)+'">복사</button></div><pre>'+esc(c)+'</pre></div>';}
  return '<div class="panel stack">'+blk('최신 버전 설치',c1)+blk('특정 버전 설치',c2)+blk('설치한 버전 업데이트',c3)+'<p class="hint">내려받은 패키지는 manifest.json의 entry 파일로 실행됩니다. 실행 환경: '+esc(a.compat)+'</p></div>';
}

/* =====================================================================
   5. [화면 ③] 다운로드 · 버전 관리
   ===================================================================== */
function panelVersions(a){
  var l=latest(a),d=state.dl[a.id];
  var form=a.mine?'<form class="panel stack" id="newver-form" novalidate style="margin-bottom:22px"><h2 style="font-size:1.05rem">새 버전 배포</h2>'
    +'<div class="newver"><div class="field"><label for="nv-v">버전</label><input id="nv-v" class="mono" value="'+bump(highest(a))+'" inputmode="numeric"><p class="err" id="nv-v-err"></p></div>'
    +'<div class="field"><label for="nv-n">변경 내용</label><textarea id="nv-n" rows="2" placeholder="이번 버전에서 바뀐 점을 적어 주세요"></textarea><p class="err" id="nv-n-err"></p></div></div>'
    +'<div class="row"><button class="btn primary" type="submit">배포하기</button><span class="hint">현재 최신 v'+esc(l.v)+' · 버전은 이전보다 커야 합니다 (예: '+bump(highest(a))+')</span></div></form>':'';
  var rows=a.versions.map(function(v,i){
    var dep=v.status==='deprecated',inst=d&&d.version===v.v;
    return '<li class="ver-row'+(v===l?' first':'')+'"><div class="rail"></div><div class="ver-body"><div class="ver-top"><span class="mono vtag">v'+esc(v.v)+'</span>'
     +(v===l?'<span class="badge ok">최신</span>':'')+(inst?'<span class="badge">설치됨</span>':'')+(dep?'<span class="badge warn">지원 중단</span>':'')
     +'<span class="muted" style="font-size:.85rem">'+esc(v.date)+' · '+size(v.size)+'</span></div>'
     +'<p'+(dep?' class="muted"':'')+'>'+esc(v.notes)+'</p>'
     +'<div class="row"><button class="btn sm" type="button" data-act="dl" data-id="'+a.id+'" data-v="'+esc(v.v)+'">'+(inst?'다시 받기':'다운로드')+'</button>'
     +(a.mine?'<button class="btn sm" type="button" data-act="deprec" data-id="'+a.id+'" data-v="'+esc(v.v)+'">'+(dep?'지원 복원':'지원 중단')+'</button>':'')+'</div></div></li>';}).join('');
  return form+'<ol class="vers">'+rows+'</ol>';
}
function bump(v){var p=v.split('.').map(Number);p[2]+=1;return p.join('.');}

function download(id,version,btn){
  var a=find(id);if(!a||!btn)return;
  var orig=btn.innerHTML,p=0;btn.disabled=true;
  var t=setInterval(function(){
    p+=14+Math.random()*20;
    if(p>=100){clearInterval(t);a.downloads++;state.dl[id]={version:version,at:TODAY};toast(a.name+' v'+version+' 다운로드 완료');updateNav();route();}
    else btn.textContent='받는 중 '+Math.floor(p)+'%';
  },110);
  /* 실제 연동: location.href = '/api/agents/'+id+'/versions/'+version+'/download' */
}

function viewDownloads(){
  var ids=Object.keys(state.dl).filter(function(id){return find(id);}),n=ids.length,u=updateCount();
  var rows=ids.map(function(id){
    var a=find(id),d=state.dl[id],l=latest(a),st=stateOf(a);
    var badge=st==='current'?'<span class="badge ok">최신 버전</span>':st==='outdated'?'<span class="badge warn">업데이트 가능</span>':'<span class="badge warn">지원 중단 버전</span>';
    return '<tr><td><a class="nm" href="#agent-'+a.id+'"><span class="tile" style="width:34px;height:34px;font-size:1rem">'+esc(a.name.charAt(0))+'</span>'+esc(a.name)+'</a></td>'
     +'<td class="mono">v'+esc(d.version)+'</td><td class="mono">v'+esc(l.v)+'</td><td>'+badge+'</td><td class="muted">'+esc(d.at)+'</td>'
     +'<td><div class="row" style="flex-wrap:nowrap">'+(st!=='current'?'<button class="btn sm primary" type="button" data-act="update" data-id="'+id+'">v'+esc(l.v)+'로 업데이트</button>':'')
     +'<button class="btn sm danger" type="button" data-act="remove" data-id="'+id+'">삭제</button></div></td></tr>';}).join('');
  app.innerHTML='<div class="page-head"><h1>내 다운로드</h1><p class="muted">내려받은 에이전트의 설치 버전과 최신 버전을 한눈에 비교합니다.</p></div>'
   +'<div class="sumbar"><div class="panel"><b>'+n+'</b><span class="muted">설치된 에이전트</span></div><div class="panel"><b style="color:'+(u?'var(--warn)':'inherit')+'">'+u+'</b><span class="muted">업데이트 필요</span></div>'
   +(u?'<button class="btn primary" type="button" data-act="updateall" style="margin-left:auto">모두 업데이트</button>':'')+'</div>'
   +(n?'<div class="tablewrap"><table><thead><tr><th>에이전트</th><th>설치 버전</th><th>최신 버전</th><th>상태</th><th>내려받은 날</th><th></th></tr></thead><tbody>'+rows+'</tbody></table></div>'
      :'<div class="empty">아직 내려받은 에이전트가 없습니다.<br><a href="#browse" class="btn primary" style="margin-top:14px">에이전트 둘러보기</a></div>');
}

/* =====================================================================
   6. [화면 ④] 에이전트 등록
   ===================================================================== */
function manifestFor(name,version){return JSON.stringify({name:slug(name)||'my-agent',version:version||'1.0.0',entry:'main.py',runtime:'python>=3.10',tools:[],permissions:['network']},null,2);}
function slug(s){return String(s).toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'');}
function field(id,label,control,hint){return '<div class="field"><label for="'+id+'">'+label+'</label>'+control+(hint?'<p class="hint">'+hint+'</p>':'')+'<p class="err" id="'+id+'-err"></p></div>';}

function viewRegister(){
  state.file=null;state.tags=[];state.submitted=false;
  app.innerHTML='<div class="page-head"><h1>에이전트 등록</h1><p class="muted">패키지를 올리고 정보를 입력하면 마켓플레이스 목록에 바로 공개됩니다.</p></div>'
  +'<div class="reg-grid"><form class="form panel" id="reg-form" novalidate>'
  +field('f-name','에이전트 이름','<input id="f-name" maxlength="40" placeholder="예: 보고서 초안 에이전트" autocomplete="off">')
  +'<div class="two">'+field('f-cat','분류','<select id="f-cat">'+CATS.map(function(c){return '<option>'+esc(c)+'</option>';}).join('')+'</select>')
  +field('f-ver','버전','<input id="f-ver" class="mono" value="1.0.0" inputmode="numeric">','major.minor.patch 형식')+'</div>'
  +field('f-sum','한 줄 소개','<input id="f-sum" maxlength="80" placeholder="목록 카드에 표시되는 소개 문장 (10~80자)">')
  +field('f-desc','상세 설명','<textarea id="f-desc" rows="4" placeholder="무엇을 하는 에이전트인지, 어떤 입력을 받는지 적어 주세요"></textarea>')
  +'<div class="field"><span class="lbl">태그 <span class="muted" style="font-weight:400">(최대 5개)</span></span><div class="taginput" id="taginput"><span id="tagchips" class="row" style="gap:6px"></span><input id="f-tag" placeholder="입력 후 Enter" aria-label="태그 입력"></div></div>'
  +'<div class="two">'+field('f-lic','라이선스','<select id="f-lic"><option>MIT</option><option>Apache-2.0</option><option>GPL-3.0</option><option>비공개 사용 허가</option></select>')+'<div></div></div>'
  +'<div class="field"><span class="lbl">에이전트 패키지</span><label class="drop" id="drop" for="f-file"><strong id="file-name">파일을 끌어다 놓거나 클릭해서 선택</strong><span id="file-meta">.zip, .tar.gz · 최대 50MB</span><input id="f-file" type="file" accept=".zip,.gz,.tgz,.json"></label><p class="err" id="f-file-err"></p></div>'
  +'<div class="field"><div class="row" style="justify-content:space-between"><label for="f-man" class="lbl">manifest.json</label><button class="btn sm" type="button" data-act="genman">이름·버전으로 자동 생성</button></div><textarea id="f-man" class="code" spellcheck="false"></textarea><p class="mstatus" id="man-status"></p><p class="err" id="f-man-err"></p></div>'
  +'<div class="row"><button class="btn primary" type="submit">등록하기</button><a class="btn" href="#browse">취소</a></div></form>'
  +'<aside class="sticky"><h2 class="side-title">목록에서 보이는 모습</h2><div id="preview"></div><p class="hint">등록하면 이 카드가 탐색 화면에 나타나고, 상세 화면에서 새 버전을 배포할 수 있습니다.</p></aside></div>';
  var form=document.getElementById('reg-form');
  document.getElementById('f-man').value=manifestFor('','1.0.0');
  paintTags();paintPreview();checkManifest();
  form.addEventListener('input',function(e){paintPreview();if(e.target.id==='f-man')checkManifest();if(state.submitted)showErrors(validate());});
  form.addEventListener('submit',function(e){e.preventDefault();submitRegister();});
  document.getElementById('f-tag').addEventListener('keydown',function(e){
    if(e.key==='Enter'||e.key===','){e.preventDefault();var v=this.value.replace(/,/g,'').trim();
      if(v&&state.tags.length<5&&state.tags.indexOf(v)<0){state.tags.push(v);paintTags();paintPreview();}this.value='';}
    else if(e.key==='Backspace'&&!this.value&&state.tags.length){state.tags.pop();paintTags();paintPreview();}});
  var fi=document.getElementById('f-file'),drop=document.getElementById('drop');
  fi.addEventListener('change',function(){setFile(fi.files[0]);});
  ['dragenter','dragover'].forEach(function(n){drop.addEventListener(n,function(e){e.preventDefault();drop.classList.add('over');});});
  ['dragleave','drop'].forEach(function(n){drop.addEventListener(n,function(e){e.preventDefault();drop.classList.remove('over');});});
  drop.addEventListener('drop',function(e){setFile(e.dataTransfer.files[0]);});
}
function setFile(f){
  if(!f)return;
  var ok=/\.(zip|gz|tgz|json)$/i.test(f.name);
  state.file=ok&&f.size<=50*1024*1024?{name:f.name,kb:Math.max(1,Math.round(f.size/1024))}:null;
  document.getElementById('file-name').textContent=state.file?f.name:'지원하지 않는 파일입니다';
  document.getElementById('file-meta').textContent=state.file?size(state.file.kb):'.zip, .tar.gz 형식, 50MB 이하만 올릴 수 있습니다';
  if(state.submitted)showErrors(validate());
}
function paintTags(){
  document.getElementById('tagchips').innerHTML=state.tags.map(function(t){return '<span class="chip">'+esc(t)+'<button type="button" data-act="rmtag" data-tag="'+esc(t)+'" aria-label="'+esc(t)+' 태그 삭제">×</button></span>';}).join('');
}
function val(id){return document.getElementById(id).value.trim();}
function paintPreview(){
  var el=document.getElementById('preview');if(!el)return;
  var v=isSemver(val('f-ver'))?val('f-ver'):'1.0.0';
  el.innerHTML=cardHTML({name:val('f-name'),publisher:'내 팀',category:val('f-cat'),summary:val('f-sum'),tags:state.tags,rating:0,downloads:0,versions:[{v:v,status:'stable'}]},true);
}
function checkManifest(){
  var s=document.getElementById('man-status'),r=parseManifest();
  s.className='mstatus '+(r.ok?'ok':'bad');s.textContent=r.ok?'✓ 올바른 manifest입니다':'✗ '+r.msg;
}
function parseManifest(){
  var m;try{m=JSON.parse(document.getElementById('f-man').value);}catch(e){return {ok:false,msg:'JSON 형식이 올바르지 않습니다'};}
  if(!m||typeof m!=='object'||Array.isArray(m))return {ok:false,msg:'객체 형태의 JSON이어야 합니다'};
  var miss=['name','version','entry'].filter(function(k){return !m[k];});
  if(miss.length)return {ok:false,msg:'필수 항목이 없습니다: '+miss.join(', ')};
  return {ok:true,data:m};
}
function validate(){
  var e={},name=val('f-name'),ver=val('f-ver');
  if(name.length<2)e['f-name']='이름을 2자 이상 입력해 주세요.';
  else if(agents.some(function(a){return a.name===name;}))e['f-name']='같은 이름의 에이전트가 이미 있습니다.';
  if(!isSemver(ver))e['f-ver']='1.0.0 같은 형식으로 입력해 주세요.';
  if(val('f-sum').length<10)e['f-sum']='한 줄 소개를 10자 이상 입력해 주세요.';
  if(val('f-desc').length<20)e['f-desc']='상세 설명을 20자 이상 입력해 주세요.';
  if(!state.file)e['f-file']='패키지 파일을 선택해 주세요.';
  var m=parseManifest();
  if(!m.ok)e['f-man']=m.msg;
  else if(isSemver(ver)&&m.data.version!==ver)e['f-man']='manifest의 version('+m.data.version+')이 위 버전('+ver+')과 다릅니다.';
  return e;
}
function showErrors(errs){
  ['f-name','f-ver','f-sum','f-desc','f-file','f-man'].forEach(function(id){
    var el=document.getElementById(id+'-err');if(el)el.textContent=errs[id]||'';
    var input=document.getElementById(id);if(input&&id!=='f-file')input.setAttribute('aria-invalid',errs[id]?'true':'false');});
}
function submitRegister(){
  state.submitted=true;var errs=validate();showErrors(errs);
  var first=Object.keys(errs)[0];
  if(first){var t=document.getElementById(first);if(t&&t.focus)t.focus();toast('입력 내용을 확인해 주세요');return;}
  var id=slug(val('f-name'))||'agent-'+(agents.length+1),base=id,n=2;
  while(find(id)){id=base+'-'+n++;}
  agents.unshift({id:id,name:val('f-name'),publisher:'내 팀',category:val('f-cat'),mine:true,summary:val('f-sum'),description:val('f-desc'),
    tools:(parseManifest().data.tools||[]).map(String),tags:state.tags.slice(),license:val('f-lic'),compat:parseManifest().data.runtime||'미지정',rating:0,reviews:0,downloads:0,
    versions:[mk(val('f-ver'),TODAY,'첫 공개 버전입니다.',state.file.kb)]});
  toast('에이전트를 등록했습니다');state.tab='overview';location.hash='agent-'+id;
}

/* =====================================================================
   7. 이벤트 처리 (data-act 위임) + 해시 라우터
   ===================================================================== */
document.addEventListener('click',function(e){
  var b=e.target.closest('[data-act]');if(!b)return;
  var act=b.getAttribute('data-act'),id=b.getAttribute('data-id'),a=id&&find(id);
  if(act==='cat'){state.cat=b.getAttribute('data-cat');paintChips();paintResults();}
  else if(act==='tab'){state.tab=b.getAttribute('data-tab');paintPanel(find(document.getElementById('panel').getAttribute('data-id')));}
  else if(act==='dl'){download(id,b.getAttribute('data-v'),b);}
  else if(act==='dl-select'){download(id,document.getElementById('ver-select').value,b);}
  else if(act==='update'){download(id,latest(a).v,b);}
  else if(act==='updateall'){agents.forEach(function(x){var s=stateOf(x);if(s==='outdated'||s==='deprecated'){state.dl[x.id]={version:latest(x).v,at:TODAY};x.downloads++;}});toast('모든 에이전트를 최신 버전으로 업데이트했습니다');updateNav();route();}
  else if(act==='remove'){delete state.dl[id];toast(a.name+' 삭제됨');updateNav();route();}
  else if(act==='deprec'){
    var v=a.versions.filter(function(x){return x.v===b.getAttribute('data-v');})[0];
    var active=a.versions.filter(function(x){return x.status!=='deprecated';});
    if(v.status!=='deprecated'&&active.length<2){toast('사용 가능한 버전이 하나뿐이라 지원 중단할 수 없습니다');return;}
    v.status=v.status==='deprecated'?'stable':'deprecated';toast('v'+v.v+(v.status==='deprecated'?' 지원 중단':' 지원 복원'));updateNav();viewDetail(a);
  }
  else if(act==='copy'){
    var text=b.getAttribute('data-text');
    (navigator.clipboard?navigator.clipboard.writeText(text):Promise.reject()).then(function(){toast('복사했습니다');},function(){toast('복사하지 못했습니다. 직접 선택해 복사해 주세요');});
  }
  else if(act==='rmtag'){state.tags=state.tags.filter(function(t){return t!==b.getAttribute('data-tag');});paintTags();paintPreview();}
  else if(act==='genman'){document.getElementById('f-man').value=manifestFor(val('f-name'),isSemver(val('f-ver'))?val('f-ver'):'1.0.0');checkManifest();if(state.submitted)showErrors(validate());}
});
document.addEventListener('submit',function(e){
  if(e.target.id!=='newver-form')return;
  e.preventDefault();
  var a=find(document.getElementById('panel').getAttribute('data-id')),v=val('nv-v'),n=val('nv-n'),ok=true;
  var ev=document.getElementById('nv-v-err'),en=document.getElementById('nv-n-err');ev.textContent='';en.textContent='';
  if(!isSemver(v)){ev.textContent='1.0.0 같은 형식으로 입력해 주세요.';ok=false;}
  else if(cmp(v,highest(a))<=0){ev.textContent='현재 최신 v'+highest(a)+'보다 큰 버전이어야 합니다.';ok=false;}
  if(n.length<5){en.textContent='변경 내용을 5자 이상 적어 주세요.';ok=false;}
  if(!ok)return;
  var kb=latest(a).size+Math.round(Math.random()*12);
  a.versions.unshift(mk(v,TODAY,n,kb));toast('v'+v+' 배포 완료');updateNav();viewDetail(a);
});

function updateNav(){
  var n=updateCount(),c=document.getElementById('nav-count');c.textContent=n;c.hidden=!n;
}
function route(){
  var h=location.hash.slice(1)||'browse';
  var key=h.indexOf('agent-')===0?'browse':h;
  Array.prototype.forEach.call(document.querySelectorAll('[data-nav]'),function(a){
    if(a.getAttribute('data-nav')===key)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');});
  if(h==='register')viewRegister();
  else if(h==='downloads')viewDownloads();
  else if(h.indexOf('agent-')===0){var a=find(h.slice(6));
    if(a)viewDetail(a);else app.innerHTML='<div class="empty">찾을 수 없는 에이전트입니다.<br><a class="btn primary" href="#browse" style="margin-top:14px">목록으로</a></div>';}
  else viewBrowse();
}
window.addEventListener('hashchange',function(){state.tab='overview';route();window.scrollTo(0,0);});
updateNav();route();
})();
