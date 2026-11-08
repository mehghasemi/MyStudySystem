const element=(tag,text)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;return e;};
function populate(sel,values,blank){const prev=sel.value;sel.replaceChildren(...(blank===undefined?[]:[new Option(blank,'')]),...values.map(([v,t])=>new Option(t,v)));if([...sel.options].some(o=>o.value===prev))sel.value=prev;}
const latin=s=>String(s).replace(/[۰-۹]/g,n=>String(n.charCodeAt(0)-1776)).replace(/[٠-٩]/g,n=>String(n.charCodeAt(0)-1632));
export function dailyUI({$,api,refresh,state,go,calendar,fa,dateLabel,addDays,openNote,readSource,openItem,openTopic,openReview,noteContext,status,configureDates,clock}){
 let list='due',editing=null,due='',from='',to='',prefsDirty=false,policyDirty=false,batchDate='',batchPlan=null,baseRev=0,preview=null,pending={},searchSeq=0,actionBusy=false,activityBusy=false;
 const cfg=()=>state().daily.config;
 const msg=t=>status(t);
 const btn=(parent,label,fn)=>{const b=element('button',label);b.type='button';b.onclick=()=>Promise.resolve().then(fn).catch(e=>msg(e.message));parent.append(b);return b;};
 async function send(command,data={},slot=command){const body={command,...data},sig=JSON.stringify(body);if(pending[slot]?.sig!==sig)pending[slot]={sig,req:{...body,operation_id:crypto.randomUUID()}};const r=await api('daily',pending[slot].req);delete pending[slot];return r;}
 function noteName(id){return state().notes.find(n=>n.id===id)?.title||'یادداشت';}
 function actionForm(a){
  editing=a;due=a.due;$('actText').value=a.description;$('actStatus').value=a.status;$('actResult').value=a.result;$('actDate').textContent=dateLabel(due)||'انتخاب موعد';$('actError').textContent='';$('actionDialog').showModal();$('actText').focus();
 }
 $('newAction').onclick=()=>{const n=noteContext();if(!n.saved)return msg('ابتدا یادداشت را ذخیره کنید.');actionForm({id:crypto.randomUUID(),note:n.id,revision:0,description:'',result:'',due:'',status:'open'});};
 $('actDate').onclick=()=>calendar.open(due,false,$('actDate'),v=>{due=v;$('actDate').textContent=dateLabel(v);});$('actClear').onclick=()=>{due='';$('actDate').textContent='انتخاب موعد';};$('actClose').onclick=()=>$('actionDialog').close();
 $('actionForm').onsubmit=async e=>{e.preventDefault();if(actionBusy)return;actionBusy=true;try{await send('action',{id:editing.id,note:editing.note,revision:editing.rev??0,description:$('actText').value,status:$('actStatus').value,result:$('actResult').value,due});$('actionDialog').close();await refresh();msg('اقدام ذخیره شد.');}catch(err){$('actError').textContent=err.message;}finally{actionBusy=false;}};
 function actionEntry(h,a){const row=element('div');row.className='daily-row';btn(row,a.description,()=>actionForm(a));row.append(element('small',[noteName(a.note),{done:'انجام شد',open:'در انتظار',cancelled:'کنار گذاشته شد'}[a.status],dateLabel(a.due),a.result,a.completed?dateLabel(a.completed.slice(0,10)):''].filter(Boolean).join(' · ')));h.append(row);}
 function noteActions(){const h=$('noteActions');h.replaceChildren();for(const a of state().daily.actions.filter(a=>a.note===noteContext().id))actionEntry(h,a);}
 function lastRead(){
  const s=state();const recent=s.daily.activities.find(a=>a.target.startsWith('note:')?s.notes.some(n=>'note:'+n.id===a.target):s.sources.some(n=>'source:'+n.id===a.target&&n.status==='active'));
  const source=s.sources.find(n=>n.status==='active');return recent?.target||(source?'source:'+source.id:s.notes[0]?'note:'+s.notes[0].id:'');
 }
 async function read(key){if(!key)return msg('ابتدا یک منبع یا یادداشت ثبت کنید.');const [k,id]=key.split(':');if(k==='source')await readSource(id);else await openNote(state().notes.find(n=>n.id===id));}
 function board(){
  const s=state(),r=s.review,t=r.today,was=s.daily.activities.filter(a=>a.kind==='logged');
  const last=lastRead();if(last){$('homeContent').hidden=false;$('welcome').hidden=true;const [k,id]=last.split(':'),item=(k==='source'?s.sources:s.notes).find(n=>n.id===id);$('continueTitle').textContent=$('coverTitle').textContent=item.title;$('continuePage').parentElement.hidden=k!=='source';if(k==='source')$('continuePage').textContent=fa(item.page);}
  $('shortStudy').disabled=!last;$('logStudy').disabled=!last;$('shortStudy').textContent='شروع مطالعه کوتاه · '+fa(cfg().minutes)+' دقیقه';
  const groups={
   due:['مرور امروز',r.rows.filter(x=>x.status==='active'&&x.due===t)],
   overdue:['مرور عقب‌افتاده',r.rows.filter(x=>x.status==='active'&&x.due<t)],
   actions:['اقدام موعددار',s.daily.actions.filter(a=>a.status==='open'&&a.due&&a.due<=t)],
   allActions:['همهٔ اقدام‌ها',s.daily.actions],
   inbox:['ورودی',s.notes.filter(n=>!s.catalog.reflections.some(x=>x.note_id===n.id)&&!s.catalog.membership.some(x=>x.target==='note:'+n.id)&&!s.catalog.placements.some(x=>x.target==='note:'+n.id))],
   recent:['یادداشت اخیر',s.notes.slice(0,5)],
   queue:['برای مطالعه',s.catalog.reading_queue.filter(q=>['پیشنهادی','بعداً','در حال مطالعه'].includes(q.status)&&s.sources.some(x=>x.id===q.source&&x.status==='active'))],
   logged:['مطالعهٔ ثبت‌شده',was],
   attempts:['مرور ثبت‌شدهٔ امروز',s.daily.completed_today]
  };
  const counts=$('dayCounts');counts.replaceChildren();for(const [k,[name,items]] of Object.entries(groups)){const b=btn(counts,name+' · '+fa(items.length),()=>{list=k;board();});b.setAttribute('aria-pressed',String(k===list));}
  const h=$('dayList');h.replaceChildren();const [label,items]=groups[list];h.append(element('h3',label));
  for(const x of items){
   if(list==='actions'||list==='allActions')actionEntry(h,x);
   else if(list==='due'||list==='overdue'||list==='attempts')btn(h,(x.target.startsWith('note:')?'یادداشت':'گزیده')+' · '+(x.cue||'مرور')+' '+(dateLabel(x.due||t)),()=>openReview(x.target));
   else if(list==='queue')btn(h,s.sources.find(v=>v.id===x.source)?.title||'منبع',()=>readSource(x.source));
   else if(list==='logged'){h.append(element('p',[x.target.startsWith('note:')?noteName(x.target.slice(5)):s.sources.find(n=>'source:'+n.id===x.target)?.title,x.minutes?fa(x.minutes)+' دقیقه':'بدون زمان',x.rating?'خودارزیابی '+fa(x.rating)+' از ۵':''].filter(Boolean).join(' · ')));}
   else btn(h,x.title,()=>openNote(x));
  }
  if(!items.length)h.append(element('p','موردی در این فهرست نیست.'));
  $('daySignal').textContent=r.backlog?'اگر مدتی فاصله افتاده، با یک مطلب شروع کنید.':'';
  const forecast=$('forecastList');forecast.replaceChildren();const active=r.rows.filter(x=>x.status==='active');
  for(const days of [7,30]){const range=active.filter(x=>x.due>=t&&x.due<addDays(t,days));const d=element('details'),sm=element('summary',fa(days)+' روز · '+fa(range.length)+' موعد ثبت‌شده');d.append(sm);for(const row of range)btn(d,dateLabel(row.due)+' · '+(row.cue||'مرور مطلب'),()=>openReview(row.target));if(!range.length)d.append(element('p','موعدی ثبت نشده است.'));forecast.append(d);}
  $('forecastHint').textContent='بر پایهٔ موعد فعلی هر مطلب، از امروز؛ نتیجه‌های آینده هنوز معلوم نیستند.';
 }
 $('continueStudy').onclick=$('shortStudy').onclick=()=>read(lastRead()).catch(e=>msg(e.message));
 $('logStudy').onclick=()=>{const opts=[...state().sources.filter(s=>s.status==='active').map(n=>['source:'+n.id,n.title]),...state().notes.map(n=>['note:'+n.id,n.title])];populate($('activityTarget'),opts);$('activityTarget').value=lastRead();$('activityMinutes').value='';$('activityRating').value='';$('ratingLabel').hidden=!cfg().feedback;$('activityError').textContent='';$('activityDialog').showModal();};
 $('activityClose').onclick=()=>$('activityDialog').close();$('activityForm').onsubmit=async e=>{e.preventDefault();if(activityBusy)return;activityBusy=true;try{await send('activity',{target:$('activityTarget').value,minutes:Number($('activityMinutes').value)||null,rating:cfg().feedback?Number($('activityRating').value)||null:null,logged:true});$('activityDialog').close();await refresh();msg('مطالعه ثبت شد.');}catch(err){$('activityError').textContent=err.message;}finally{activityBusy=false;}};
 const keys=['font','size','contrast','autosave','zone','digits','week','display','cap','boundary','minutes','cues','feedback','initial_folder'];
 function applyPrefs(){const d=cfg();configureDates(d);document.documentElement.style.fontFamily=d.font+', Tahoma, sans-serif';document.documentElement.style.fontSize=d.size+'%';document.documentElement.classList.toggle('high-contrast',d.contrast);clock();}
 function prefs(force=false){const d=cfg();if(!prefsDirty&&!policyDirty||force)baseRev=d.rev;if(!prefsDirty||force){
  populate($('pref-initial_folder'),state().catalog.folders.filter(f=>!f.archived).map(f=>[f.id,f.rel]),'ورودی');
  for(const k of keys){const field=$('pref-'+k);if(field.type==='checkbox')field.checked=d[k];else if(k==='boundary')field.value=String(Math.floor(d[k]/60)).padStart(2,'0')+':'+String(d[k]%60).padStart(2,'0');else field.value=d[k];}
  }if(!policyDirty||force){$('intervals').value=state().daily.policy.intervals.join(', ');$('policyRepeat').checked=state().daily.policy.repeat_last;}
  const pick=$('batchTargets'),old=new Set([...pick.selectedOptions].map(o=>o.value));const active=new Set(state().review.rows.filter(r=>['active','paused'].includes(r.status)).map(r=>r.target));pick.replaceChildren(...[...state().notes.map(n=>['note:'+n.id,n.title]),...state().highlights.map(n=>['highlight:'+n.id,n.body.slice(0,60)])].filter(([k])=>!active.has(k)).map(([k,t])=>new Option(t,k,false,old.has(k))));
 }
 function policyBody(){return {intervals:latin($('intervals').value).split(/[,،\s]+/).filter(Boolean).map(Number),repeat_last:$('policyRepeat').checked,scope:$('policyScope').value,revision:baseRev};}
 $('settings').addEventListener('input',e=>{if(e.target.id.startsWith('pref-'))prefsDirty=true;else if(['intervals','policyRepeat','policyScope'].includes(e.target.id))policyDirty=true;preview=null;$('applyPolicy').hidden=true;$('policyReport').textContent='';});
 $('prefsTheme').onclick=()=>$('theme').click();$('prefsNav').onclick=()=>$('collapse').click();
 $('prefsSave').onclick=async()=>{try{const values={};for(const k of keys){const f=$('pref-'+k);if(!f.reportValidity())return;values[k]=f.type==='checkbox'?f.checked:k==='boundary'?Number(f.value.slice(0,2))*60+Number(f.value.slice(3)):f.type==='number'||k==='week'?Number(f.value):f.value;}
 await send('settings',{revision:baseRev,values});prefsDirty=false;baseRev++;await refresh();msg('تنظیمات ذخیره شد.');}catch(e){msg(e.message);}};
 $('policyPreview').onclick=async()=>{try{preview=await api('daily',{command:'preview',...policyBody()});$('policyReport').textContent='برنامه‌های متأثر: '+fa(preview.affected)+'؛ مرحلهٔ '+fa(preview.clamped)+' مورد کوتاه می‌شود. موعد فعلی حفظ می‌شود. در موارد متأثر، برگشت نتیجهٔ پیش از تغییر سیاست بسته می‌شود.';$('applyPolicy').hidden=false;}catch(e){msg(e.message);}};
 $('applyPolicy').onclick=async()=>{if(!preview)return;try{await send('policy',{...policyBody(),token:preview.token});policyDirty=false;baseRev++;preview=null;$('applyPolicy').hidden=true;await refresh();$('policyReport').textContent='نسخهٔ سیاست ذخیره شد.';}catch(e){msg(e.message);}};
 $('prefsReload').onclick=async()=>{if((prefsDirty||policyDirty)&&!window.confirm('تغییرات ذخیره‌نشدهٔ تنظیمات کنار گذاشته شود؟'))return;prefsDirty=policyDirty=false;preview=null;$('applyPolicy').hidden=true;await refresh();};
 function batchBody(){return {targets:[...$('batchTargets').selectedOptions].map(o=>o.value),due:batchDate||state().review.first};}
 function resetBatch(){batchPlan=null;$('batchApply').hidden=true;$('batchReport').textContent='';}
 $('batchTargets').onchange=resetBatch;
 $('batchDate').onclick=()=>calendar.open(batchDate||state().review.first,false,$('batchDate'),v=>{batchDate=v;$('batchDate').textContent=dateLabel(v);resetBatch();});
 $('batchPreview').onclick=async()=>{try{const body=batchBody();batchPlan=await api('daily',{command:'batch-preview',...body});$('batchReport').textContent=dateLabel(body.due)+' · موعدهای این روز پس از ثبت: '+fa(batchPlan.total)+' · سقف روزانه: '+fa(batchPlan.cap)+(batchPlan.total>batchPlan.cap?' · تعداد از سقف عبور می‌کند.':'')+(body.due===state().review.today?' · مرور دوبارهٔ امروز را تأیید می‌کنید.':'');$('batchApply').hidden=false;}catch(e){resetBatch();msg(e.message);}};
 $('batchApply').onclick=async()=>{if(!batchPlan)return;try{await send('batch',{...batchBody(),token:batchPlan.token,confirm_today:true});resetBatch();await refresh();msg('برنامه‌های انتخاب‌شده ثبت شدند.');}catch(e){msg(e.message);}};
 $('checkHealth').onclick=async()=>{try{const h=await api('daily',{command:'health'});$('healthReport').textContent=(h.healthy?'بررسی SQLite موفق بود.':'داده نیازمند بررسی است.')+' نسخهٔ داده '+fa(h.schema);}catch(e){$('healthReport').textContent=e.message;}};
 function searchOptions(){populate($('findType'),[...new Set(state().sources.map(s=>s.type))].map(t=>[t,({book:'کتاب',pdf:'PDF',article:'مقاله',website:'وب‌سایت',video:'ویدئو',course:'دوره',conversation:'گفت‌وگو',personal_experience:'تجربهٔ شخصی',other:'سایر'})[t]||t]),'همه');populate($('findTopic'),state().catalog.topics.filter(t=>t.status==='active').map(t=>[t.id,t.label]),'همه');}
 for(const [id,set,get] of [['findFrom',v=>from=v,()=>from],['findTo',v=>to=v,()=>to]])$(id).onclick=()=>calendar.open(get(),false,$(id),v=>{set(v);$(id).textContent=dateLabel(v);});
 $('findClear').onclick=()=>{from=to='';$('findFrom').textContent='از موعد';$('findTo').textContent='تا موعد';for(const id of ['findKind','findType','findTopic','findTag','findReview'])$(id).value='';};
 $('searchForm').onsubmit=async e=>{e.preventDefault();const seq=++searchSeq;try{const q=$('query').value.trim(),params=new URLSearchParams({q,kind:$('findKind').value,type:$('findType').value,topic:$('findTopic').value,tag:$('findTag').value,review:$('findReview').value,from,to});
 if(from&&to&&from>to)throw Error('انتهای بازه پیش از شروع است.');$('searchStatus').textContent='در حال جست‌وجو…';const {results}=await api('search?'+params);if(seq!==searchSeq)return;const h=$('results');h.replaceChildren();$('searchStatus').textContent=results.length?fa(results.length)+' نتیجه'+(results.length===200?' (حداکثر نمایش)':''):'نتیجه‌ای پیدا نشد.';for(const n of results){const box=element('article');box.className='result';box.append(element('h2',n.title));const p=element('p');p.dir='auto';const ix=q?n.body.indexOf(q):-1;if(ix>=0)p.append(document.createTextNode(n.body.slice(0,ix)),element('mark',q),document.createTextNode(n.body.slice(ix+q.length)));else p.textContent=n.body;box.append(p);btn(box,({topics:'خواندن موضوع',sources:'خواندن منبع',notes:'بازکردن یادداشت',highlights:'خواندن گزیده'})[n.kind],()=>n.kind==='topics'?openTopic(n.id):n.kind==='sources'?readSource(n.id):n.kind==='highlights'?openItem('highlight:'+n.id):openNote(state().notes.find(x=>x.id===n.id)));h.append(box);}}catch(err){$('searchStatus').textContent=err.message;}};
 return {render(){applyPrefs();prefs();board();searchOptions();noteActions();},noteActions,opened:async key=>{await send('activity',{target:key},'open-'+key);await refresh();}};
}
