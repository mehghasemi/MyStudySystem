import {dailyUI} from './daily.js';
import {catalogUI} from './catalog.js';
import {Calendar,fa,dateLabel,timeLabel,todayISO,addDays,configureDates,selectedZone,locale} from './calendar.js';
const $=id=>document.getElementById(id);
const calendar=new Calendar();
let state,csrf,route='home',noteId=crypto.randomUUID(),revision=0,due='',atUTC='',dirty=false,busy=false,pending=null,sourceId='book-1',pageDirty=false,stopped=false;
const tab=crypto.randomUUID();
let sourceEditId=crypto.randomUUID(),sourceRevision=0,sourceDirty=false,sourceBusy=false,sourcePending=null,sourceStatusValue='active';
let autosaveTimer,draftTimer,draftId=crypto.randomUUID(),draftRevision=0,draftQueue=Promise.resolve(),draftFailure=false,draftPending=null,autoBlocked=false;
let progressRevision=0,progressPending=null,navigationEpoch=0;

const status=(text,error=false,quiet=false)=>{$('globalStatus').classList.toggle('visually-quiet',quiet);$('globalStatus').textContent=text;$('globalStatus').classList.toggle('problem',error);};
async function api(path,body) {
  const response=await fetch('/api/'+path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-CSRF':csrf},body:JSON.stringify(body)});
  const data=await response.json();if(!response.ok){const error=new Error(data.error||'عمل انجام نشد.');error.status=response.status;throw error;}return data;
}
const hasDraft=()=>dirty||pageDirty||busy||sourceDirty||sourceBusy||rvDirty||rvWorking||!!$('rvReflection').value.trim();
async function heartbeat(){if(!csrf||stopped)return;try{await api('heartbeat',{tab,dirty:hasDraft()});}catch{status('ارتباط با برنامه برقرار نیست. نوشته را نگه دارید و برنامه را دوباره باز کنید.',true);}}
function changed(){dirty=true;autoBlocked=false;$('saveStatus').textContent='تغییرات ذخیره نشده';$('charCount').textContent=fa($('noteBody').value.length)+' نویسه';heartbeat();clearTimeout(draftTimer);draftTimer=setTimeout(()=>persistDraft(),250);clearTimeout(autosaveTimer);autosaveTimer=setTimeout(()=>{if(state.daily.config.autosave&&dirty&&!autoBlocked&&$('noteTitle').value.trim()&&$('noteBody').value.trim())saveNote();},1100);}
function dateButtons(){$('duePicker').textContent=dateLabel(due)||'انتخاب تاریخ شمسی';$('timePicker').textContent=timeLabel(atUTC)||'انتخاب تاریخ و ساعت';}
function errorMessage(error){status(error.message||'ارتباط برقرار نشد؛ دوباره تلاش کنید.',true);}
async function run(task){try{await task();}catch(e){errorMessage(e);}}
async function refresh(){state=await api('state');csrf=state.csrf;configureDates(state.daily.config);renderLists();daily.render();dateButtons();return state;}
function renderLists(){
  desk.render();$('newNoteTopics').hidden=!!revision;renderLibrary();renderDrafts();const active=state.sources.filter(s=>s.status==='active');const hasSource=active.length>0;$('welcome').hidden=hasSource;$('homeContent').hidden=!hasSource;
  $('studyEmpty').hidden=hasSource;$('studyContent').hidden=!hasSource;$('dataPath').value=state.data_path;
  if(active[0]){$('continueTitle').textContent=active[0].title;$('coverTitle').textContent=active[0].title;$('continuePage').textContent=fa(active[0].page);}
  $('noteList').replaceChildren();
  for(const n of state.notes){const b=document.createElement('button');b.className='note-item';b.textContent=n.title;const small=document.createElement('small');small.textContent=n.due?dateLabel(n.due):'بدون تاریخ';b.append(small);b.onclick=()=>run(()=>openNote(n));$('noteList').append(b);}
  if(!state.notes.length)$('noteList').textContent='هنوز یادداشتی ذخیره نشده است.';
  $('sourceList').replaceChildren();for(const src of active){const b=document.createElement('button');b.className='note-item';b.textContent=src.title;const small=document.createElement('small');small.textContent='صفحهٔ '+fa(src.page);b.append(small);b.onclick=()=>run(async()=>{if(pageDirty){status('ابتدا جای مطالعهٔ تغییرکرده را ثبت کنید.',true);return;}await readSource(src.id);});$('sourceList').append(b);}
  renderReview();
  if(!pageDirty)renderStudy();
}
function renderStudy(){const src=state.sources.find(s=>s.id===sourceId&&s.status==='active')||state.sources.find(s=>s.status==='active');if(!src)return;sourceId=src.id;desk.files('source:'+src.id,$('studyFiles'));$('bookTitle').textContent=src.title;if($('bookBody').textContent!==src.body)$('bookBody').textContent=src.body;$('bookPage').value=src.page;$('bookChapter').value=src.chapter;progressRevision=src.progress_revision;$('studyTopic').textContent=src.creator||'نویسنده ثبت نشده';$('highlightList').replaceChildren();for(const h of state.highlights.filter(h=>h.source===src.id)){const q=document.createElement('blockquote');q.textContent=h.body;const small=document.createElement('small');small.textContent='نقل‌قول از منبع · '+h.location;q.append(small);const add=document.createElement('button');add.textContent='برنامهٔ مرور گزیده';add.onclick=()=>beginEnroll('highlight:'+h.id,add);q.append(add);$('highlightList').append(q);}if(!$('highlightList').children.length)$('highlightList').textContent='هنوز گزیده‌ای از این کتاب ثبت نشده است.';}
function go(next){
  if(!['home','capture','library','study','review','search','help','organize','settings'].includes(next))return;
  if(route==='review'&&next!=='review')clearAnswer();
  navigationEpoch++;route=next;for(const s of document.querySelectorAll('main>section'))s.hidden=s.id!==next;
  for(const b of document.querySelectorAll('nav [data-route]')){if(b.dataset.route===next)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');}
  if(next==='review')renderReview();if(next==='capture')daily.noteActions();
  $('main').focus();window.scrollTo(0,0);
}
for(const b of document.querySelectorAll('[data-route]'))b.onclick=()=>go(b.dataset.route);
function confirm(text,label='ادامه') {return new Promise(resolve=>{const dialog=$('confirmDialog'),opener=document.activeElement;$('confirmText').textContent=text;$('confirmAccept').textContent=label;let result=false;$('confirmAccept').onclick=()=>{result=true;dialog.close();};$('confirmCancel').onclick=()=>dialog.close();dialog.addEventListener('close',()=>{opener?.focus();resolve(result);},{once:true});dialog.showModal();$('confirmCancel').focus();});}
async function openNote(n){if(busy)return;if(dirty&&!await confirm('این فرم نوشتهٔ ذخیره‌نشده دارد. برای کنارگذاشتن آن و بازکردن یادداشت دیگر تأیید کنید.','کنار گذاشتن تغییرات'))return;
  await abandonDraft();noteId=n.id;revision=n.revision;setNoteExtras(n);due=n.due;atUTC=n.at_utc;$('noteTitle').value=n.title;$('noteBody').value=n.body;dirty=false;pending=null;dateButtons();$('saveError').hidden=true;$('conflictActions').hidden=true;$('saveStatus').textContent='نسخهٔ ذخیره‌شده';$('charCount').textContent=fa(n.body.length)+' نویسه';go('capture');$('noteTitle').focus();heartbeat();await daily.opened('note:'+n.id);}
async function newNote(){if(busy)return;if(dirty&&!await confirm('نوشتهٔ ذخیره‌نشدهٔ فعلی کنار گذاشته می‌شود. ادامه می‌دهید؟','کنار گذاشتن تغییرات'))return;await abandonDraft();noteId=crypto.randomUUID();revision=0;setNoteExtras({});due='';atUTC='';$('noteTitle').value='';$('noteBody').value='';dirty=false;pending=null;dateButtons();$('saveError').hidden=true;$('conflictActions').hidden=true;$('saveStatus').textContent='یادداشت تازه';$('charCount').textContent='۰ نویسه';$('noteTitle').focus();heartbeat();}
async function saveNote(separate=false){
  if(busy)return;if(!$('noteForm').reportValidity())return;clearTimeout(autosaveTimer);busy=true;await persistDraft();
  if(separate){noteId=crypto.randomUUID();revision=0;pending=null;}
  const body=noteSnapshot();
  const fingerprint=JSON.stringify(body);if(!pending||pending.fingerprint!==fingerprint)pending={fingerprint,request:{...body,operation_id:crypto.randomUUID()}};
  const sent=pending.request;busy=true;$('saveNote').disabled=true;$('saveStatus').textContent='در حال ذخیره…';$('saveError').hidden=true;await heartbeat();
  try{
    const result=await api('save',sent);revision=result.revision;
    const unchanged=JSON.stringify({...noteSnapshot(),revision:sent.revision})===JSON.stringify(Object.fromEntries(Object.entries(sent).filter(([k])=>k!=='operation_id')));
    dirty=!unchanged;pending=null;if(unchanged)await abandonDraft();else {await persistDraft();clearTimeout(autosaveTimer);if(state.daily.config.autosave)autosaveTimer=setTimeout(()=>saveNote(),1100);}$('saveStatus').textContent=unchanged?'ذخیره شد':'متن قبلی ذخیره شد؛ تغییرات تازه هنوز ذخیره نشده';$('conflictActions').hidden=true;await refresh();status('یادداشت روی این رایانه ذخیره شد.');
  }catch(e){dirty=true;autoBlocked=true;$('saveStatus').textContent='ذخیره انجام نشد';$('saveError').textContent=e.message||'ارتباط قطع شد؛ متن را نگه دارید و دوباره ذخیره کنید.';$('saveError').hidden=false;$('conflictActions').hidden=e.status!==409;}
  finally{busy=false;$('saveNote').disabled=false;await heartbeat();}
}
$('noteForm').onsubmit=e=>{e.preventDefault();saveNote();};$('noteTitle').oninput=changed;$('noteBody').oninput=changed;for(const id of ['noteSummary','notePersonal','noteApplication','noteLocator'])$(id).oninput=changed;$('noteSource').onchange=()=>{changed();noteSourceHint();};
$('newNote').onclick=()=>run(newNote);for(const [i,id] of ['direction','dirSummary','dirPersonal','dirApplication'].entries())$(id).onchange=()=>{$(['noteBody','noteSummary','notePersonal','noteApplication'][i]).dir=$(id).value;changed();};
$('duePicker').onclick=()=>calendar.open(due,false,$('duePicker'),v=>{due=v;dateButtons();changed();});
$('timePicker').onclick=()=>calendar.open(atUTC,true,$('timePicker'),v=>{atUTC=v;dateButtons();changed();});
$('clearDue').onclick=()=>{due='';dateButtons();changed();};$('clearTime').onclick=()=>{atUTC='';dateButtons();changed();};
$('showLatest').onclick=()=>run(async()=>{await refresh();const n=state.notes.find(n=>n.id===noteId);$('latestText').textContent=n?`${n.title}\n\n${n.body}`:'این یادداشت در دادهٔ فعلی پیدا نشد.';$('latestDialog').showModal();});
$('closeLatest').onclick=()=>$('latestDialog').close();$('latestDialog').addEventListener('close',()=>$('showLatest').focus());$('saveSeparate').onclick=()=>saveNote(true);
function pageChanged(){pageDirty=true;progressPending=null;$('pageStatus').textContent='ثبت نشده';heartbeat();}
$('bookPage').oninput=pageChanged;$('bookChapter').oninput=pageChanged;
$('savePage').onclick=()=>run(async()=>{if(!$('bookPage').reportValidity())return;const sent={id:sourceId,page:Number($('bookPage').value),chapter:$('bookChapter').value,revision:progressRevision};if(!progressPending)progressPending={...sent,operation_id:crypto.randomUUID()};try{const result=await api('bookmark',progressPending);progressRevision=result.revision;pageDirty=$('bookPage').value!==String(sent.page)||$('bookChapter').value!==sent.chapter;progressPending=null;await refresh();$('pageStatus').textContent=pageDirty?'جای قبلی ثبت شد؛ تغییر تازه را ثبت کنید':'جای مطالعه ثبت شد';$('reloadPage').hidden=true;heartbeat();}catch(e){$('pageStatus').textContent=e.message;$('reloadPage').hidden=e.status!==409;}});
$('reloadPage').onclick=()=>run(async()=>{const fresh=await api('state');const src=fresh.sources.find(s=>s.id===sourceId);if(!src)return;if(await confirm('جای ثبت‌شده: صفحهٔ '+fa(src.page)+'، فصل '+src.chapter+'. تغییر ثبت‌نشدهٔ این تب کنار گذاشته شود؟','استفاده از جای ثبت‌شده')){state=fresh;pageDirty=false;progressPending=null;renderStudy();$('reloadPage').hidden=true;heartbeat();}});
$('highlight').onclick=()=>run(async()=>{const sel=getSelection(),body=sel.toString();if(!body||!$('bookBody').contains(sel.anchorNode)||!$('bookBody').contains(sel.focusNode))throw new Error('عبارت را در متن همین منبع انتخاب کنید.');await desk.excerpt('source:'+sourceId,body,'صفحهٔ '+fa(Number($('bookPage').value)));});

let rvKey='',rvAttempt=null,rvGrade='',rvDue='',rvDirty=false,rvWorking=false,rvPending=null,rvEnrollKey='',rvEnrollDue='',rvOpener=null;
const rvRow=()=>state?.review.rows.find(r=>r.target===rvKey);
const rvNotify=t=>{$('rvMsg').textContent=t;};
const rvLabels={again:'یادم نبود',partial:'ناقص یادم بود',good:'توانستم توضیح بدهم'};
const rvStatuses={active:'فعال',paused:'متوقف',ended:'پایان چرخه',cancelled:'پایان‌یافته'};
function clearAnswer(){
  $('answerArea').hidden=true;$('answerBody').replaceChildren();$('rvHistory').textContent='';$('gradeButtons').replaceChildren();$('rvResult').hidden=true;rvGrade='';rvDue='';$('rvChoice').textContent='';
}
function resetAttempt(){
  clearAnswer();rvAttempt=null;rvDirty=false;$('recallBody').value='';$('rvAttempt').hidden=true;
}
function renderReview(){
  const v=state.review;
  $('rvQuota').textContent='مرورهای ثبت‌شدهٔ امروز: '+fa(v.used)+' از '+fa(v.cap)+' · آمادهٔ مرور: '+fa(v.queue.length)+' · در انتظار: '+fa(v.backlog);
  if($('rvHome'))$('rvHome').textContent=fa(v.queue.length)+' مطلب برای مرور امروز';
  $('rvQueue').disabled=!v.queue.length;
  $('rvEmpty').hidden=!!v.rows.length;$('rvPanel').hidden=!v.rows.length;
  if(!rvRow())rvKey=v.queue[0]||v.rows[0]?.target||'';
  $('rvSelect').replaceChildren(...v.rows.map((r,i)=>new Option((r.target.startsWith('note:')?'یادداشت ':'گزیده ')+fa(i+1)+' · '+((state.daily.config.cues&&r.cue)||rvStatuses[r.status]),r.target)));
  $('rvSelect').value=rvKey;const r=rvRow();if(!r)return;
  $('rvCue').textContent=(state.daily.config.cues&&r.cue)||'از این مطلب چه چیزی به یاد داری؟';
  $('rvInfo').textContent='مرور نوبت '+fa(r.turn)+' · مرحلهٔ '+fa(r.step)+' از '+fa(r.stages)+' · '+rvStatuses[r.status]+(r.due?' · موعد '+dateLabel(r.due):'');
  $('rvUndo').disabled=!r.undo;$('rvPause').disabled=r.status!=='active';$('rvResume').disabled=r.status!=='paused';$('rvStart').disabled=r.status!=='active'||v.used>=v.cap;
  $('rvSnooze').disabled=$('rvReschedule').disabled=r.status!=='active';$('rvCancel').disabled=!['active','paused'].includes(r.status);
}
async function rvCommand(cmd,extra={},key=rvKey,revision=rvRow()?.rev||0){
  const body={command:cmd,target:key,revision,...extra},signature=JSON.stringify(body);
  if(!rvPending||rvPending.signature!==signature)rvPending={signature,req:{...body,operation_id:crypto.randomUUID()}};
  const result=await api('review',rvPending.req);rvPending=null;return result;
}
async function rvRun(f){
  if(rvWorking)return;rvWorking=true;$('recallBody').readOnly=true;try{await f();}catch(e){rvNotify(e.message);$('rvEnrollMsg').textContent=e.message;$('rvReload').hidden=false;}finally{rvWorking=false;$('recallBody').readOnly=false;heartbeat();}
}
async function persistRecall(){
  if(!rvDirty||!rvAttempt)return;
  const answer=$('recallBody').value;
  const r=await rvCommand('draft',{attempt:rvAttempt.id,draft_revision:rvAttempt.rev,answer},rvKey,rvAttempt.schedule);
  rvAttempt.rev=r.rev;rvDirty=$('recallBody').value!==answer;rvNotify('پیش‌نویس پاسخ ذخیره شد.');
}
async function chooseReview(key){
  if(rvWorking)return false;
  try{await persistRecall();}catch(e){rvNotify(e.message);$('rvSelect').value=rvKey;return false;}
  if(rvDirty||($('rvReflection').value&&!await confirm('برداشت ثبت‌نشده کنار گذاشته شود؟'))){$('rvSelect').value=rvKey;return false;}
  $('rvReflection').value='';resetAttempt();rvKey=key;rvPending=null;rvNotify('');renderReview();return true;
}
function beginEnroll(key,opener){
  if(rvWorking)return;
  const row=state.review.rows.find(r=>r.target===key);
  if(row&&['active','paused'].includes(row.status)){run(async()=>{if(await chooseReview(key))go('review');});return;}
  rvEnrollKey=key;$('rvRepeat').checked=state.daily.policy.repeat_last;$('rvFirstHint').textContent='پیشنهاد اولین مرور: '+dateLabel(state.review.first);rvOpener=opener;rvEnrollDue=state.review.first;$('rvCueInput').value='';$('rvEnrollMsg').textContent='';$('rvEnrollDate').textContent=dateLabel(rvEnrollDue);$('rvEnroll').showModal();
}
$('rvAddNote').onclick=()=>{if(dirty||!revision){status('ابتدا یادداشت را ذخیره کنید.',true);return;}beginEnroll('note:'+noteId,$('rvAddNote'));};
$('rvEnrollClose').onclick=()=>$('rvEnroll').close();$('rvEnroll').onclose=()=>rvOpener?.focus();
$('rvEnrollDate').onclick=()=>calendar.open(rvEnrollDue,false,$('rvEnrollDate'),v=>{rvEnrollDue=v;$('rvEnrollDate').textContent=dateLabel(v);});
async function confirmToday(due){return due!==state.review.today||await confirm('مرور دوباره امروز ثبت شود؟','تأیید امروز');}
$('rvEnrollOk').onclick=()=>rvRun(async()=>{if(!await confirmToday(rvEnrollDue))return;await rvCommand('enroll',{due:rvEnrollDue,confirm_today:true,cue:$('rvCueInput').value,repeat_last:$('rvRepeat').checked},rvEnrollKey,state.review.rows.find(r=>r.target===rvEnrollKey)?.rev||0);$('rvEnroll').close();await refresh();status('به برنامهٔ مرور اضافه شد.');});
$('rvSelect').onchange=()=>chooseReview($('rvSelect').value);
$('rvQueue').onclick=()=>run(async()=>{const key=state.review.queue[0];if(key&&await chooseReview(key))$('rvStart').focus();});
$('rvStart').onclick=()=>rvRun(async()=>{await persistRecall();const r=rvRow();const a=await rvCommand('start');resetAttempt();rvAttempt={...a,schedule:r.rev};$('rvAttempt').hidden=false;$('recallBody').value=a.answer;$('recallBody').focus();rvNotify(r.due>state.review.today?'مرور زودهنگام است. ثبت نتیجه موعد بعدی را تغییر می‌دهد.':'پاسخ شفاهی هم کافی است.');});
let rvTimer;
$('recallBody').oninput=()=>{rvDirty=true;heartbeat();clearTimeout(rvTimer);rvTimer=setTimeout(()=>rvRun(persistRecall),700);};
$('rvSaveDraft').onclick=()=>rvRun(persistRecall);
async function revealReview(isAttempt){
  await persistRecall();const data=await rvCommand('reveal');
  clearAnswer();$('answerArea').hidden=false;$('answerBody').textContent=data.body;$('rvHistory').textContent=data.history.filter(h=>h.answer).map(h=>'یادآوری قبلی · '+dateLabel(h.day)+(h.status==='undone'?' (برگشت‌خورده)':'')+'\n'+h.answer).join('\n\n');
  $('rvResult').hidden=!isAttempt;
  if(isAttempt)for(const [grade,label] of Object.entries(rvLabels)){
    const button=document.createElement('button'),p=rvRow().choices[grade];button.textContent=label+' · '+(p.due?dateLabel(p.due):'پایان چرخه');const why=document.createElement('small');why.textContent=grade==='again'?'بازگشت به مرحلهٔ اول':grade==='partial'?'تکرار همین مرحله':rvRow().step<rvRow().stages?'رفتن به مرحلهٔ بعد':'آخرین مرحله';button.append(why);
    button.onclick=()=>{rvGrade=grade;rvDue=p.due;$('rvChoice').textContent=label+' · مرحلهٔ '+fa(p.step)+' · '+(rvDue?dateLabel(rvDue):'پایان چرخه');for(const b of $('gradeButtons').children)b.setAttribute('aria-pressed',String(b===button));};$('gradeButtons').append(button);
  }
  $('answerHeading').focus();
}
$('rvRead').onclick=()=>rvRun(async()=>{await persistRecall();resetAttempt();await revealReview(false);});
$('reveal').onclick=()=>rvRun(()=>revealReview(true));
$('hideAnswer').onclick=()=>{clearAnswer();(rvAttempt?$('reveal'):$('rvRead')).focus();};
$('rvDate').onclick=()=>{if(!rvGrade){rvNotify('ابتدا نتیجه را انتخاب کنید.');return;}calendar.open(rvDue||state.review.first,false,$('rvDate'),v=>{rvDue=v;$('rvChoice').textContent=rvLabels[rvGrade]+' · موعد انتخابی '+dateLabel(v);});};
$('rvCommit').onclick=()=>rvRun(async()=>{if(!rvGrade||!rvAttempt){rvNotify('نتیجه را انتخاب کنید.');return;}if(!await confirmToday(rvDue))return;clearTimeout(rvTimer);const answer=$('recallBody').value;$('recallBody').readOnly=true;try{await rvCommand('grade',{expected_day:state.review.today,attempt:rvAttempt.id,draft_revision:rvAttempt.rev,grade:rvGrade,due:rvDue,answer,confirm_today:true},rvKey,rvAttempt.schedule);}finally{$('recallBody').readOnly=false;}resetAttempt();await refresh();rvNotify('نتیجه ثبت شد.');$('rvInfo').setAttribute('tabindex','-1');$('rvInfo').focus();});
$('rvReflect').onclick=()=>rvRun(async()=>{const answer=$('rvReflection').value;await rvCommand('reflect',{answer});if($('rvReflection').value===answer)$('rvReflection').value='';await refresh();rvNotify('برداشت جداگانه ثبت شد.');});
for(const [id,cmd] of [['rvPause','pause'],['rvCancel','cancel'],['rvUndo','undo']])$(id).onclick=()=>rvRun(async()=>{if(!await confirm($(id).textContent+' انجام شود؟'))return;await persistRecall();await rvCommand(cmd);resetAttempt();await refresh();rvNotify('برنامهٔ مرور به‌روز شد.');});
for(const [id,cmd] of [['rvSnooze','snooze'],['rvReschedule','reschedule'],['rvResume','resume']])$(id).onclick=()=>calendar.open(cmd==='resume'&&rvRow().due>=state.review.today?rvRow().due:cmd==='resume'?state.review.today:state.review.first,false,$(id),v=>rvRun(async()=>{if(!await confirmToday(v))return;await persistRecall();await rvCommand(cmd,{due:v,confirm_today:true});resetAttempt();await refresh();rvNotify('موعد ثبت شد.');}));
$('rvReload').onclick=()=>rvRun(async()=>{await refresh();$('rvReload').hidden=true;if(rvAttempt){const current=await rvCommand('start');rvAttempt={...current,schedule:rvRow().rev};rvDirty=true;clearAnswer();}rvNotify('وضعیت تازه دریافت شد. پاسخ خود را بررسی کنید.');});

function setTheme(value){document.documentElement.dataset.theme=value;$('theme').textContent=value==='dark'?'حالت روشن':'حالت تاریک';}
$('theme').onclick=()=>run(async()=>{const theme=document.documentElement.dataset.theme==='dark'?'light':'dark';setTheme(theme);await api('preferences',{theme});});
function collapse(value){document.querySelector('.shell').classList.toggle('collapsed',value);$('collapse').setAttribute('aria-expanded',String(!value));$('collapse').querySelector('.nav-text').textContent=value?'باز کردن منو':'جمع کردن منو';}
$('collapse').onclick=()=>run(async()=>{const collapsed=!document.querySelector('.shell').classList.contains('collapsed');collapse(collapsed);await api('preferences',{collapsed});});
$('quit').onclick=()=>run(async()=>{if(hasDraft()){status('نوشته یا جای مطالعهٔ ذخیره‌نشده دارید. ابتدا در همان صفحه ذخیره کنید.',true);return;}if(!await confirm('برنامهٔ محلی بسته می‌شود. برای اجرای دوباره فایل MyStudySystem.exe را باز کنید.','خروج کامل'))return;await heartbeat();await api('shutdown',{});stopped=true;clearInterval(heartbeatTimer);status('برنامه کامل بسته شد. اکنون می‌توانید این تب را ببندید.');document.body.classList.add('shutdown');});
window.addEventListener('beforeunload',e=>{if(hasDraft()&&!stopped){e.preventDefault();e.returnValue='';}});
window.addEventListener('pagehide',()=>{if(csrf&&!stopped)fetch('/api/close-tab',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF':csrf},body:JSON.stringify({tab}),keepalive:true}).catch(()=>{});});
document.addEventListener('keydown',e=>{if(e.ctrlKey&&e.key.toLowerCase()==='s'){e.preventDefault();if(route==='capture')saveNote();if(route==='library')saveBook();}if(e.altKey&&e.key.toLowerCase()==='m'){e.preventDefault();$('collapse').click();}});
// Keep Tab inside the modal, including the transition that Chromium otherwise sends to browser chrome.
for(const dialog of document.querySelectorAll('dialog'))dialog.addEventListener('keydown',e=>{
  if(e.key!=='Tab')return;
  const nodes=[...dialog.querySelectorAll('button,input,select,textarea,a[href],[tabindex]')].filter(n=>!n.disabled&&n.tabIndex>=0&&n.getClientRects().length);
  const first=nodes[0],last=nodes.at(-1);
  if(e.shiftKey&&document.activeElement===first){e.preventDefault();last?.focus();}
  else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first?.focus();}
});
function clock(){$('clock').textContent=new Intl.DateTimeFormat(locale(),{dateStyle:'full',timeStyle:'short',timeZone:selectedZone()}).format(new Date());}
function noteSnapshot(){return {directions:Object.fromEntries(['body','summary','personal','application'].map((k,i)=>[k,$(['direction','dirSummary','dirPersonal','dirApplication'][i]).value])),initial_topics:[...$('captureTopics').selectedOptions].map(o=>o.value),id:noteId,revision,title:$('noteTitle').value,body:$('noteBody').value,due,at_utc:atUTC,sections:{summary:$('noteSummary').value,personal:$('notePersonal').value,application:$('noteApplication').value},source_id:$('noteSource').value,locator:$('noteLocator').value};}
function setNoteExtras(n){for(const [i,k] of ['body','summary','personal','application'].entries()){const id=n.section_records?.find(s=>s.kind===k)?.id,dir=n.directions?.[k]||state?.daily.directions[id]||'auto';$(['direction','dirSummary','dirPersonal','dirApplication'][i]).value=dir;$(['noteBody','noteSummary','notePersonal','noteApplication'][i]).dir=dir;}$('newNoteTopics').hidden=!!revision;for(const o of $('captureTopics').options)o.selected=(n.initial_topics||[]).includes(o.value);for(const [id,key] of [['noteSummary','summary'],['notePersonal','personal'],['noteApplication','application']])$(id).value=n.sections?.[key]||'';$('noteSource').value=n.source_id||'';$('noteLocator').value=n.locator||'';noteSourceHint();}
function noteSourceHint(){const src=state?.sources.find(s=>s.id===$('noteSource').value);$('sourceHint').textContent=src?(src.status==='active'?'متن کتاب از یادداشت مستقل است.':'این کتاب بایگانی یا حذف شده؛ ارجاع حفظ شده است.'):'این یادداشت بدون کتاب هم ذخیره می‌شود.';$('openNoteSource').disabled=!src||src.status!=='active';}
function persistDraft(){
  clearTimeout(draftTimer);if(!dirty)return draftQueue;
  const payload=noteSnapshot(),id=draftId;
  draftQueue=draftQueue.catch(()=>{}).then(async()=>{if(id!==draftId)return;try{if(draftPending){const r=await api('draft',draftPending);draftRevision=r.revision;draftPending=null;}draftPending={id,revision:draftRevision,payload,operation_id:crypto.randomUUID()};const r=await api('draft',draftPending);draftRevision=r.revision;draftPending=null;draftFailure=false;$('draftStatus').textContent='پیش‌نویس روی رایانه ثبت شد';}catch(e){draftFailure=true;$('draftStatus').textContent='پیش‌نویس ثبت نشد؛ این تب را نبندید.';}});
  return draftQueue;
}
async function abandonDraft(){
  clearTimeout(autosaveTimer);clearTimeout(draftTimer);await draftQueue;
  if(draftRevision){try{await api('discard-draft',{id:draftId,revision:draftRevision,operation_id:crypto.randomUUID()});}catch(e){status('نسخه‌ای از پیش‌نویس باقی ماند؛ از فهرست پیش‌نویس‌ها بررسی کنید.',true);}}
  draftId=crypto.randomUUID();draftRevision=0;draftPending=null;autoBlocked=false;$('draftStatus').textContent='';
}
function renderDrafts(){
  $('draftList').replaceChildren();
  for(const d of state.drafts||[]){if(d.id===draftId)continue;const b=document.createElement('button');b.className='note-item';b.textContent=d.payload.title||'پیش‌نویس بدون عنوان';b.onclick=()=>run(async()=>{if(busy)return;if(dirty&&!await confirm('پیش‌نویس فعلی کنار گذاشته شود؟'))return;await abandonDraft();const n=d.payload;noteId=n.id;revision=n.revision;due=n.due||'';atUTC=n.at_utc||'';$('noteTitle').value=n.title||'';$('noteBody').value=n.body||'';setNoteExtras(n);draftId=d.id;draftRevision=d.revision;dirty=true;pending=null;autoBlocked=true;dateButtons();go('capture');$('saveStatus').textContent='پیش‌نویس باز شد؛ پس از بررسی ذخیره کنید';$('draftStatus').textContent='پیش‌نویس روی رایانه ثبت شده';heartbeat();});$('draftList').append(b);}
  if(!$('draftList').children.length)$('draftList').textContent='پیش‌نویس ناتمامی ندارید.';
}
function renderLibrary(){
  const selected=$('noteSource').value;$('noteSource').replaceChildren(new Option('بدون کتاب',''),...state.sources.map(s=>new Option(s.title+(s.status==='active'?'':' · در دسترس نیست'),s.id)));$('noteSource').value=selected;noteSourceHint();
  $('libraryList').replaceChildren();
  for(const src of state.sources.filter(s=>s.status===$('libraryFilter').value&&desk.sourceMatches(s))){const b=document.createElement('button');b.className='note-item';b.textContent=src.title;const small=document.createElement('small');small.textContent=src.creator||'کتاب';b.append(small);b.onclick=()=>run(()=>openBook(src));$('libraryList').append(b);}
  if(!$('libraryList').children.length)$('libraryList').textContent='کتابی در این فهرست ندارید.';
}
async function openBook(src){if(sourceBusy)return;if(sourceDirty&&!await confirm('متن ویرایش‌شدهٔ کتاب هنوز ذخیره نشده است. کنار گذاشته شود؟'))return;sourceEditId=src?.id||crypto.randomUUID();sourceRevision=src?.revision||0;sourceStatusValue=src?.status||'active';$('sourceKind').value=src?.type||'book';kindFields();const web=state.catalog.source_meta.find(m=>m.source===src?.id);$('siteName').value=web?.site||'';accessed=web?.accessed||'';$('accessedDate').textContent=dateLabel(accessed)||'تاریخ دسترسی';$('sourceURL').value=state.catalog.source_meta.find(m=>m.source===src?.id)?.url||'';sourcePending=null;sourceDirty=false;for(const [id,key] of [['sourceTitle','title'],['sourceCreator','creator'],['sourcePublisher','publisher'],['sourceBody','body']])$(id).value=src?.[key]||'';$('sourceError').hidden=true;$('sourceConflict').hidden=true;$('sourceStatus').textContent=src?'نسخهٔ ذخیره‌شده':'کتاب تازه';$('archiveBook').disabled=!src;$('deleteBook').disabled=!src;go('library');$('sourceTitle').focus();heartbeat();}
let accessed='';
function kindFields(){const kind=$('sourceKind').value;$('webFields').hidden=kind!=='website';$('sourcePublisher').closest('div').hidden=kind!=='book';}
$('captureTopics').onchange=changed;
$('accessedDate').onclick=()=>calendar.open(accessed,false,$('accessedDate'),v=>{accessed=v;$('accessedDate').textContent=dateLabel(v);$('sourceBody').oninput();});$('clearAccessed').onclick=()=>{accessed='';$('accessedDate').textContent='تاریخ دسترسی';$('sourceBody').oninput();};
function sourceSnapshot(){return {id:sourceEditId,revision:sourceRevision,type:$('sourceKind').value,site:$('siteName').value,accessed,url:$('sourceURL').value,title:$('sourceTitle').value,body:$('sourceBody').value,creator:$('sourceCreator').value,publisher:$('sourcePublisher').value,status:sourceStatusValue};}
async function saveBook(separate=false){if(sourceBusy||!$('bookForm').reportValidity())return false;if(separate){sourceEditId=crypto.randomUUID();sourceRevision=0;sourceStatusValue='active';sourcePending=null;}const body=sourceSnapshot(),fingerprint=JSON.stringify(body);if(!sourcePending||sourcePending.fingerprint!==fingerprint)sourcePending={fingerprint,request:{...body,operation_id:crypto.randomUUID()}};const sent=sourcePending.request;sourceBusy=true;$('saveBook').disabled=true;$('sourceStatus').textContent='در حال ذخیره…';await heartbeat();try{const result=await api('source-save',sent);sourceRevision=result.revision;sourceDirty=JSON.stringify({...sourceSnapshot(),revision:sent.revision})!==fingerprint;sourcePending=null;$('sourceStatus').textContent=sourceDirty?'متن قبلی ذخیره شد؛ تغییر تازه را ذخیره کنید':'کتاب ذخیره شد';$('sourceError').hidden=true;$('sourceConflict').hidden=true;$('archiveBook').disabled=false;$('deleteBook').disabled=false;await refresh();return !sourceDirty;}catch(e){sourceDirty=true;$('sourceStatus').textContent='ذخیره انجام نشد';$('sourceError').textContent=e.message;$('sourceError').hidden=false;$('sourceConflict').hidden=e.status!==409;return false;}finally{sourceBusy=false;$('saveBook').disabled=false;heartbeat();}}
async function readSource(id){if(pageDirty){status('ابتدا جای مطالعهٔ تغییرکرده را ثبت کنید.',true);return;}const epoch=navigationEpoch;sourceId=id;await api('read-source',{id});await refresh();renderStudy();if(epoch===navigationEpoch)go('study');}
for(const id of ['sourceTitle','sourceCreator','sourcePublisher','sourceBody','sourceKind','sourceURL','siteName'])$(id).oninput=()=>{sourceDirty=true;$('sourceStatus').textContent='تغییرات ذخیره نشده';heartbeat();};
$('sourceKind').onchange=kindFields;
$('bookForm').onsubmit=e=>{e.preventDefault();saveBook();};$('newBook').onclick=()=>run(()=>openBook(null));$('libraryFilter').onchange=renderLibrary;
$('readBook').onclick=()=>run(async()=>{if(sourceDirty||!sourceRevision){if(!await saveBook())return;}if(sourceStatusValue!=='active')throw new Error('کتاب بایگانی شده است.');await readSource(sourceEditId);});
$('sourceSeparate').onclick=()=>saveBook(true);$('sourceLatest').onclick=()=>run(async()=>{const fresh=await api('state'),s=fresh.sources.find(s=>s.id===sourceEditId);$('latestText').textContent=s?`${s.title}\n${s.creator}\n${s.publisher}\n\n${s.body}`:'کتاب پیدا نشد.';$('latestDialog').showModal();});
for(const [id,value] of [['archiveBook','archived'],['deleteBook','deleted']])$(id).onclick=()=>run(async()=>{if(!sourceRevision)return;if(!await confirm(value==='deleted'?'کتاب از فهرست حذف می‌شود. متن و ارجاع‌ها می‌مانند؛ بازیابی حذف‌شده‌ها هنوز در دسترس نیست.':'کتاب از فهرست در دست مطالعه به بایگانی منتقل می‌شود.',value==='deleted'?'حذف از فهرست':'بایگانی'))return;const previous=sourceStatusValue;sourceStatusValue=value;if(await saveBook()){sourceDirty=false;await openBook(null);}else sourceStatusValue=previous;});
$('continueStudy').onclick=()=>run(()=>readSource(state.sources.find(s=>s.status==='active')?.id));
$('editCurrentBook').onclick=()=>run(()=>openBook(state.sources.find(s=>s.id===sourceId)));
$('noteFromBook').onclick=()=>run(async()=>{const old=noteId;await newNote();if(old===noteId)return;$('noteSource').value=sourceId;$('noteLocator').value='صفحهٔ '+fa(Number($('bookPage').value));noteSourceHint();go('capture');$('noteTitle').focus();});
$('openNoteSource').onclick=()=>run(()=>readSource($('noteSource').value));
const desk=catalogUI({$,api,refresh,go,confirm,calendar,fa,dateLabel,beginEnroll,getState:()=>state,renderLibrary,openNote,readSource,status});
$('orgNote').onclick=()=>{if(!revision||dirty)return status('ابتدا یادداشت را ذخیره کنید.',true);desk.open('note:'+noteId);};
$('orgSource').onclick=()=>{if(!sourceRevision||sourceDirty)return status('ابتدا منبع را ذخیره کنید.',true);desk.open('source:'+sourceEditId);};
const daily=dailyUI({$,api,refresh,state:()=>state,go,calendar,fa,dateLabel,addDays,openNote,readSource,openItem:desk.open,openTopic:desk.openTopic,openReview:async k=>{if(await chooseReview(k))go('review');},noteContext:()=>({id:noteId,saved:revision>0&&!dirty}),status,configureDates,clock});
clock();setInterval(async()=>{clock();if(state&&!stopped){try{const d=await api('day');if(state.review.today!==d.today){await refresh();status('روز مطالعه تغییر کرد؛ موعدهای امروز به‌روز شد.');}}catch{ /* heartbeat reports connection failures */ } }},30000);const heartbeatTimer=setInterval(heartbeat,3000);
run(async()=>{await refresh();setTheme(state.settings.theme||'light');collapse(!!state.settings.collapsed);status('آماده · نوشته‌ها روی همین رایانه ذخیره می‌شوند.',false,true);await heartbeat();});
