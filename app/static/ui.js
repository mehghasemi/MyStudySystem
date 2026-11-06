import {Calendar,fa,dateLabel,timeLabel,todayISO,addDays} from './calendar.js';
const $=id=>document.getElementById(id);
const calendar=new Calendar();
let state,csrf,route='home',noteId=crypto.randomUUID(),revision=0,due='',atUTC='',dirty=false,busy=false,pending=null,sourceId='book-1',pageDirty=false,stopped=false;
const tab=crypto.randomUUID();
const status=(text,error=false)=>{$('globalStatus').textContent=text;$('globalStatus').classList.toggle('problem',error);};
async function api(path,body) {
  const response=await fetch('/api/'+path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-CSRF':csrf},body:JSON.stringify(body)});
  const data=await response.json();if(!response.ok){const error=new Error(data.error||'عمل انجام نشد.');error.status=response.status;throw error;}return data;
}
const hasDraft=()=>dirty||pageDirty||busy||!!$('recallBody').value.trim();
async function heartbeat(){if(!csrf||stopped)return;try{await api('heartbeat',{tab,dirty:hasDraft()});}catch{status('ارتباط با برنامه برقرار نیست. نوشته را نگه دارید و برنامه را دوباره باز کنید.',true);}}
function changed(){dirty=true;pending=null;$('saveStatus').textContent='تغییرات ذخیره نشده';$('charCount').textContent=fa($('noteBody').value.length)+' نویسه';heartbeat();}
function dateButtons(){$('duePicker').textContent=dateLabel(due)||'انتخاب تاریخ شمسی';$('timePicker').textContent=timeLabel(atUTC)||'انتخاب تاریخ و ساعت';}
function errorMessage(error){status(error.message||'ارتباط برقرار نشد؛ دوباره تلاش کنید.',true);}
async function run(task){try{await task();}catch(e){errorMessage(e);}}
async function refresh(){state=await api('state');csrf=state.csrf;renderLists();return state;}
function renderLists(){
  const hasSource=state.sources.length>0;$('welcome').hidden=hasSource||state.notes.length>0;$('homeContent').hidden=!hasSource;
  $('studyEmpty').hidden=hasSource;$('studyContent').hidden=!hasSource;$('dataPath').value=state.data_path;
  if(state.sources[0]){$('continueTitle').textContent=state.sources[0].title;$('continuePage').textContent=fa(state.sources[0].page);}
  $('noteList').replaceChildren();
  for(const n of state.notes){const b=document.createElement('button');b.className='note-item';b.textContent=n.title;const small=document.createElement('small');small.textContent=n.due?dateLabel(n.due):'بدون تاریخ';b.append(small);b.onclick=()=>run(()=>openNote(n));$('noteList').append(b);}
  if(!state.notes.length)$('noteList').textContent='هنوز یادداشتی ذخیره نشده است.';
  $('sourceList').replaceChildren();for(const src of state.sources){const b=document.createElement('button');b.className='note-item';b.textContent=src.title;const small=document.createElement('small');small.textContent='صفحهٔ '+fa(src.page);b.append(small);b.onclick=()=>run(async()=>{if(pageDirty){status('ابتدا جای مطالعهٔ تغییرکرده را ثبت کنید.',true);return;}sourceId=src.id;renderStudy();});$('sourceList').append(b);}
  const previous=$('reviewSelect').value;$('reviewSelect').replaceChildren(...state.notes.map((n,i)=>new Option(`مطلب ${fa(i+1)}${n.id==='note-1'?' · موضوع خشم':n.id==='note-2'?' · موضوع یادگیری':''}`,n.id)));
  if(state.notes.some(n=>n.id===previous))$('reviewSelect').value=previous;
  $('reviewEmpty').hidden=!!state.notes.length;$('reviewContent').hidden=!state.notes.length;
  if(!pageDirty)renderStudy();
}
function renderStudy(){const src=state.sources.find(s=>s.id===sourceId)||state.sources[0];if(!src)return;sourceId=src.id;$('bookTitle').textContent=src.title;if($('bookBody').textContent!==src.body)$('bookBody').textContent=src.body;$('bookPage').value=src.page;$('studyTopic').textContent=src.id==='book-1'?'موضوع خشم':'موضوع یادگیری';$('highlightList').replaceChildren();for(const h of state.highlights.filter(h=>h.source===src.id)){const q=document.createElement('blockquote');q.textContent=h.body;const small=document.createElement('small');small.textContent='نقل‌قول از منبع · '+h.location;q.append(small);$('highlightList').append(q);}if(!$('highlightList').children.length)$('highlightList').textContent='هنوز گزیده‌ای از این کتاب ثبت نشده است.';}
function go(next){
  if(!['home','capture','study','review','search','help'].includes(next))return;
  route=next;for(const s of document.querySelectorAll('main>section'))s.hidden=s.id!==next;
  for(const b of document.querySelectorAll('nav [data-route]')){if(b.dataset.route===next)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');}
  if(next==='review')hideAnswer();
  $('main').focus();window.scrollTo(0,0);
}
for(const b of document.querySelectorAll('[data-route]'))b.onclick=()=>go(b.dataset.route);
function confirm(text,label='ادامه') {return new Promise(resolve=>{const dialog=$('confirmDialog'),opener=document.activeElement;$('confirmText').textContent=text;$('confirmAccept').textContent=label;let result=false;$('confirmAccept').onclick=()=>{result=true;dialog.close();};$('confirmCancel').onclick=()=>dialog.close();dialog.addEventListener('close',()=>{opener?.focus();resolve(result);},{once:true});dialog.showModal();$('confirmCancel').focus();});}
async function openNote(n){if(busy)return;if(dirty&&!await confirm('این فرم نوشتهٔ ذخیره‌نشده دارد. برای کنارگذاشتن آن و بازکردن یادداشت دیگر تأیید کنید.','کنار گذاشتن تغییرات'))return;
  noteId=n.id;revision=n.revision;due=n.due;atUTC=n.at_utc;$('noteTitle').value=n.title;$('noteBody').value=n.body;dirty=false;pending=null;dateButtons();$('saveError').hidden=true;$('conflictActions').hidden=true;$('saveStatus').textContent='نسخهٔ ذخیره‌شده';$('charCount').textContent=fa(n.body.length)+' نویسه';go('capture');$('noteTitle').focus();heartbeat();}
async function newNote(){if(busy)return;if(dirty&&!await confirm('نوشتهٔ ذخیره‌نشدهٔ فعلی کنار گذاشته می‌شود. ادامه می‌دهید؟','کنار گذاشتن تغییرات'))return;noteId=crypto.randomUUID();revision=0;due='';atUTC='';$('noteTitle').value='';$('noteBody').value='';dirty=false;pending=null;dateButtons();$('saveError').hidden=true;$('conflictActions').hidden=true;$('saveStatus').textContent='یادداشت تازه';$('charCount').textContent='۰ نویسه';$('noteTitle').focus();heartbeat();}
async function saveNote(separate=false){
  if(busy)return;if(!$('noteForm').reportValidity())return;
  if(separate){noteId=crypto.randomUUID();revision=0;pending=null;}
  const body={id:noteId,revision,title:$('noteTitle').value,body:$('noteBody').value,due,at_utc:atUTC};
  const fingerprint=JSON.stringify(body);if(!pending||pending.fingerprint!==fingerprint)pending={fingerprint,request:{...body,operation_id:crypto.randomUUID()}};
  const sent=pending.request;busy=true;$('saveNote').disabled=true;$('saveStatus').textContent='در حال ذخیره…';$('saveError').hidden=true;await heartbeat();
  try{
    const result=await api('save',sent);revision=result.revision;
    const unchanged=$('noteTitle').value===sent.title&&$('noteBody').value===sent.body&&due===sent.due&&atUTC===sent.at_utc;
    dirty=!unchanged;pending=null;$('saveStatus').textContent=unchanged?'ذخیره شد':'متن قبلی ذخیره شد؛ تغییرات تازه هنوز ذخیره نشده';$('conflictActions').hidden=true;await refresh();status('یادداشت روی این رایانه ذخیره شد.');
  }catch(e){dirty=true;$('saveStatus').textContent='ذخیره انجام نشد';$('saveError').textContent=e.message||'ارتباط قطع شد؛ متن را نگه دارید و دوباره ذخیره کنید.';$('saveError').hidden=false;$('conflictActions').hidden=e.status!==409;}
  finally{busy=false;$('saveNote').disabled=false;await heartbeat();}
}
$('noteForm').onsubmit=e=>{e.preventDefault();saveNote();};$('noteTitle').oninput=changed;$('noteBody').oninput=changed;
$('newNote').onclick=()=>run(newNote);$('direction').onchange=()=>{$('noteBody').dir=$('direction').value;};
$('duePicker').onclick=()=>calendar.open(due,false,$('duePicker'),v=>{due=v;dateButtons();changed();});
$('timePicker').onclick=()=>calendar.open(atUTC,true,$('timePicker'),v=>{atUTC=v;dateButtons();changed();});
$('clearDue').onclick=()=>{due='';dateButtons();changed();};$('clearTime').onclick=()=>{atUTC='';dateButtons();changed();};
$('showLatest').onclick=()=>run(async()=>{await refresh();const n=state.notes.find(n=>n.id===noteId);$('latestText').textContent=n?`${n.title}\n\n${n.body}`:'این یادداشت در دادهٔ فعلی پیدا نشد.';$('latestDialog').showModal();});
$('closeLatest').onclick=()=>$('latestDialog').close();$('latestDialog').addEventListener('close',()=>$('showLatest').focus());$('saveSeparate').onclick=()=>saveNote(true);
$('seed').onclick=()=>run(async()=>{$('seed').disabled=true;try{await api('seed',{});await refresh();status('دو کتاب و یادداشت‌های ساختگی آماده‌اند؛ از مطالعه شروع کنید.');}finally{$('seed').disabled=false;}});
$('bookPage').oninput=()=>{pageDirty=true;$('pageStatus').textContent='ثبت نشده';heartbeat();};
$('savePage').onclick=()=>run(async()=>{if(!$('bookPage').reportValidity())return;await api('bookmark',{id:sourceId,page:Number($('bookPage').value)});pageDirty=false;await refresh();$('pageStatus').textContent='جای مطالعه ثبت شد';heartbeat();});
$('highlight').onclick=()=>run(async()=>{const selection=window.getSelection(),body=selection.toString().trim();if(!body||!$('bookBody').contains(selection.anchorNode)||!$('bookBody').contains(selection.focusNode))throw new Error('ابتدا عبارتی از متن همین کتاب انتخاب کنید.');await api('highlight',{body,source:sourceId,location:'صفحهٔ '+fa(Number($('bookPage').value))});await refresh();status('گزیده ثبت شد؛ در پایین متن کتاب دیده می‌شود.');});
function hideAnswer(){$('answerArea').hidden=true;$('answerBody').replaceChildren();$('gradeButtons').replaceChildren();$('gradePreview').textContent='';$('reveal').hidden=false;const id=$('reviewSelect').value;$('reviewCue').textContent=id==='note-1'?'دربارهٔ موضوع خشم چه چیزی به یاد داری؟':id==='note-2'?'چطور یک مفهوم را برای دیگری توضیح می‌دهی؟':'از این مطلب چه چیزی به یاد داری؟';}
$('reviewSelect').onchange=hideAnswer;$('hideAnswer').onclick=()=>{hideAnswer();$('reveal').focus();};
$('reveal').onclick=()=>{const n=state.notes.find(n=>n.id===$('reviewSelect').value);if(!n)return;$('answerBody').textContent=n.body;$('answerArea').hidden=false;$('reveal').hidden=true;$('gradeButtons').replaceChildren();for(const [label,days] of [['یادم نبود',1],['ناقص یادم بود',1],['توانستم توضیح بدهم',3]]){const b=document.createElement('button');b.textContent=label;b.setAttribute('aria-pressed','false');const small=document.createElement('small');small.textContent='پیشنهاد: '+dateLabel(addDays(todayISO(),days));b.append(small);b.onclick=()=>{for(const other of $('gradeButtons').children)other.setAttribute('aria-pressed','false');b.setAttribute('aria-pressed','true');$('gradePreview').textContent=`پیش‌نمایش «${label}»: ${dateLabel(addDays(todayISO(),days))}. نتیجه و موعدی ثبت نشد.`;};$('gradeButtons').append(b);}$('answerHeading').focus();};
$('recallBody').oninput=heartbeat;
$('saveRecall').onclick=()=>run(async()=>{const text=$('recallBody').value;if(!text.trim())throw new Error('برای ذخیره، چند کلمه از یادآوری خود بنویسید.');$('saveRecall').disabled=true;try{await api('save',{id:crypto.randomUUID(),revision:0,title:'یادآوری آزمایشی من',body:text,due:'',at_utc:'',operation_id:crypto.randomUUID()});if($('recallBody').value===text)$('recallBody').value='';await refresh();status('یادآوری به‌عنوان یادداشت جدا ذخیره شد.');await heartbeat();}finally{$('saveRecall').disabled=false;}});
$('searchForm').onsubmit=e=>{e.preventDefault();run(async()=>{$('searchStatus').textContent='در حال جست‌وجو…';const {results}=await api('search?q='+encodeURIComponent($('query').value));$('results').replaceChildren();$('searchStatus').textContent=results.length?fa(results.length)+' نتیجه پیدا شد':'نتیجه‌ای پیدا نشد؛ عبارت کوتاه‌تر یا شکل دیگری از کلمه را امتحان کنید.';for(const n of results){const d=document.createElement('article');d.className='result';const h=document.createElement('h2');h.textContent=n.title||'گزیده از منبع';const p=document.createElement('p');p.dir='auto';p.textContent=n.body;d.append(h,p);if(n.kind!=='highlights'){const b=document.createElement('button');b.textContent=n.kind==='notes'?'بازکردن یادداشت':'خواندن منبع';b.onclick=()=>n.kind==='notes'?run(()=>openNote(n)):(sourceId=n.id,renderStudy(),go('study'));d.append(b);}$('results').append(d);}});};
function setTheme(value){document.documentElement.dataset.theme=value;$('theme').textContent=value==='dark'?'حالت روشن':'حالت تاریک';}
$('theme').onclick=()=>run(async()=>{const theme=document.documentElement.dataset.theme==='dark'?'light':'dark';setTheme(theme);await api('preferences',{theme});});
function collapse(value){document.querySelector('.shell').classList.toggle('collapsed',value);$('collapse').setAttribute('aria-expanded',String(!value));$('collapse').querySelector('.nav-text').textContent=value?'باز کردن منو':'جمع کردن منو';}
$('collapse').onclick=()=>run(async()=>{const collapsed=!document.querySelector('.shell').classList.contains('collapsed');collapse(collapsed);await api('preferences',{collapsed});});
$('quit').onclick=()=>run(async()=>{if(hasDraft()){status('نوشته یا جای مطالعهٔ ذخیره‌نشده دارید. ابتدا در همان صفحه ذخیره کنید.',true);return;}if(!await confirm('برنامهٔ محلی بسته می‌شود. برای اجرای دوباره فایل MyStudySystem.exe را باز کنید.','خروج کامل'))return;await heartbeat();await api('shutdown',{});stopped=true;clearInterval(heartbeatTimer);status('برنامه کامل بسته شد. اکنون می‌توانید این تب را ببندید.');document.body.classList.add('shutdown');});
window.addEventListener('beforeunload',e=>{if(hasDraft()&&!stopped){e.preventDefault();e.returnValue='';}});
window.addEventListener('pagehide',()=>{if(csrf&&!stopped)fetch('/api/close-tab',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF':csrf},body:JSON.stringify({tab}),keepalive:true}).catch(()=>{});});
document.addEventListener('keydown',e=>{if(e.ctrlKey&&e.key.toLowerCase()==='s'){e.preventDefault();if(route==='capture')saveNote();}if(e.altKey&&e.key.toLowerCase()==='m'){e.preventDefault();$('collapse').click();}});
// Keep Tab inside the modal, including the transition that Chromium otherwise sends to browser chrome.
for(const dialog of document.querySelectorAll('dialog'))dialog.addEventListener('keydown',e=>{
  if(e.key!=='Tab')return;
  const nodes=[...dialog.querySelectorAll('button,input,select,textarea,a[href],[tabindex]')].filter(n=>!n.disabled&&n.tabIndex>=0&&n.getClientRects().length);
  const first=nodes[0],last=nodes.at(-1);
  if(e.shiftKey&&document.activeElement===first){e.preventDefault();last?.focus();}
  else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first?.focus();}
});
function clock(){$('clock').textContent=new Intl.DateTimeFormat('fa-IR',{dateStyle:'full',timeStyle:'short',timeZone:'Asia/Tehran'}).format(new Date());}
clock();setInterval(clock,30000);const heartbeatTimer=setInterval(heartbeat,3000);
run(async()=>{await refresh();setTheme(state.settings.theme||'light');collapse(!!state.settings.collapsed);status('آماده · نوشته‌ها روی همین رایانه ذخیره می‌شوند.');await heartbeat();});
