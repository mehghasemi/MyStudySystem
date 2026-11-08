const types={book:'کتاب',website:'وب‌سایت',article:'مقاله',pdf:'PDF',video:'ویدئو',course:'دوره',conversation:'گفت‌وگو',personal_experience:'تجربهٔ شخصی',other:'سایر'};
const statuses=['پیشنهادی','بعداً','در حال مطالعه','تکمیل','کنارگذاشته'];
const norm=s=>String(s||'').normalize('NFKC').replace(/ي/g,'ی').replace(/ك/g,'ک').replace(/\u200c/g,' ').toLowerCase();
function node(tag,text){const e=document.createElement(tag);if(text!==undefined)e.textContent=text;return e;}
function options(s,rows,empty){const old=s.value,selected=new Set([...s.selectedOptions].map(x=>x.value));s.replaceChildren(...(empty===undefined?[]:[new Option(empty,'')]),...rows.map(([id,label])=>new Option(label,id)));if(s.multiple){for(const o of s.options)o.selected=selected.has(o.value);}else if(rows.some(([id])=>id===old)||old===''&&empty!==undefined)s.value=old;}
function pathLabel(rows,id,field){const parts=[],seen=new Set();while(id&&!seen.has(id)){seen.add(id);const r=rows.find(x=>x.id===id);if(!r)break;parts.unshift(r[field]);id=r.parent;}return parts.join(' / ');}
export function catalogUI({$,api,refresh,go,confirm,calendar,fa,dateLabel,beginEnroll,getState,renderLibrary,status}){
 const cat=()=>getState().catalog, sources=()=>getState().sources;
 let topic='',folder='',key='',planned='',filterDay='',pending=null,busy=false,items=[];
 const val=id=>$(id).value;
 const note=t=>{$('orgMessage').textContent=t;status(t);};
 for(const id of ['sourceKind','libKind','itemType'])options($(id),Object.entries(types),id==='sourceKind'?undefined:'همه');
 options($('queueStatus'),statuses.map(x=>[x,x]));options($('queueFilter'),statuses.map(x=>[x,x]),'همه');
 function action(fn){return async()=>{if(busy)return;busy=true;try{await fn();}catch(e){$('orgMessage').textContent=e.message;status(e.message,true);if(e.status===409)await refresh();}finally{busy=false;}};}
 const on=(id,fn)=>{$(id).onclick=action(fn);};
 function button(host,label,fn){const b=node('button',label);b.type='button';b.onclick=action(fn);host.append(b);return b;}
 async function mutate(action,extra={}){$('orgMessage').textContent='در حال ذخیره…';const q={action,revision:cat().rev,...extra},signature=JSON.stringify(q);if(pending?.signature!==signature)pending={signature,q:{...q,operation_id:crypto.randomUUID()}};const r=await api('catalog',pending.q);pending=null;await refresh();note('تغییرات ذخیره شد.');return r;}
 async function preview(action,fields){const {plan,token}=await api('catalog',{action,revision:cat().rev,...fields});if(await confirm('از «'+(plan.old||'بدون ریشه')+'» به «'+plan.new+'». مسیرهای فایل مرتبط: '+fa(plan.count)+(action==='move'?'؛ پوشه روی دیسک منتقل می‌شود.':'؛ فایل‌های روی دیسک منتقل نمی‌شوند.'),'تأیید تغییر'))await mutate(action,{...fields,confirm:token});}
 const members=(table,t)=>cat()[table].filter(r=>r.target===t);
 const fileRows=t=>members('attached',t).map(r=>cat().file_refs.find(f=>f.id===r.file)).filter(Boolean);
 function files(t,host){host.replaceChildren();for(const f of fileRows(t)){if(f.available){const a=node('a','بازکردن '+f.rel);a.target='_blank';a.rel='noopener';a.href='/api/document?id='+encodeURIComponent(f.id);host.append(a);}else host.append(node('span',f.rel+' · فایل یافت نشد'));}}
 const srcName=id=>sources().find(s=>s.id===id)?.title||'منبع در دسترس نیست';
 function sourceMatches(s){const k='source:'+s.id,f=fileRows(k),v=val('libFile');return (!val('libKind')||val('libKind')===s.type)&&norm(s.title+' '+members('tags',k).map(x=>x.label).join(' ')).includes(norm(val('libQuery')))&&(!v||(v==='none'?!f.length:v==='available'?f.some(x=>x.available):f.some(x=>!x.available)));}
 function collect(){
  items=['note','highlight','source'].flatMap(kind=>getState()[{note:'notes',highlight:'highlights',source:'sources'}[kind]].filter(r=>!r.status||r.status==='active').map(r=>({...r,kind,key:kind+':'+r.id})));
  for(const i of items){i.name=i.title||'گزیده · '+i.body.slice(0,55);const a=cat().anchors.find(a=>a.highlight===i.id),orig=a&&items.find(r=>r.key===a.origin);
   i.created=i.created_at||a?.stamp||'';i.updated=i.updated_at||i.created;
   const first=i.kind==='source'?i.id:i.source_id||i.source||orig?.source_id;
   i.refs=[...(first?[{source:first,locator:i.locator||i.location||''}]:[]),...members('citations',i.key)];
   i.topics=members('membership',i.key).map(x=>x.topic);i.tags=members('tags',i.key).map(x=>x.label);
   i.review=getState().review.rows.find(r=>r.target===i.key);i.stale=a?.revision&&orig&&a.revision!==(orig.content_revision||orig.section_records?.find(s=>s.kind==='body')?.revision);
  }
 }
 function article(i,host,chosen=false){
  const box=node('article');box.className='catalog-article';box.append(node('h3',i.name));const body=node('div',i.body);body.className='prose';body.dir='auto';if(chosen)body.id='orgBody';box.append(body);
  for(const [k,v] of Object.entries(i.sections||{}))if(k!=='body'&&v)box.append(node('strong',({personal:'برداشت شخصی',summary:'خلاصه',application:'کاربرد'})[k]||k),node('p',v));
  if(i.refs.length)box.append(node('small',i.refs.map(r=>srcName(r.source)+(r.locator?' · '+r.locator:'')).join(' | ')));
  if(i.tags.length)box.append(node('p',i.tags.map(t=>'#'+t).join(' ')));if(i.stale)box.append(node('p','لنگر نیازمند بررسی است؛ متن مبدأ تغییر کرده است.'));
  if(i.review?.due)box.append(node('p','موعد مرور: '+dateLabel(i.review.due)));
  const links=node('div');links.className='actions';files(i.key,links);box.append(links);if(!chosen)button(box,'دسته‌بندی و ارجاع‌ها',()=>open(i.key));host.append(box);
 }
 function tree(rows,host,field,current,choose,filter=''){
  host.replaceChildren();const visible=rows.filter(r=>!r.archived&&r.status!=='deleted'),ids=new Set();
  for(const r of visible.filter(r=>norm(pathLabel(rows,r.id,field)).includes(norm(filter)))){let a=r;while(a&&!ids.has(a.id)){ids.add(a.id);a=visible.find(x=>x.id===a.parent);}}
  function branch(id,h){const ul=node('ul');for(const r of visible.filter(r=>ids.has(r.id)&&(r.parent===id||!id&&r.parent&&!visible.some(p=>p.id===r.parent)))){const li=node('li');button(li,r[field],()=>choose(r)).setAttribute('aria-pressed',String(current===r.id));branch(r.id,li);ul.append(li);}if(ul.children.length)h.append(ul);}
  branch('',host);if(!host.children.length)host.textContent='موردی در این درخت وجود ندارد.';
 }
 function showTopics(){
  tree(cat().topics,$('topicTree'),'label',topic,r=>{topic=r.id;$('topicName').value=r.label;$('topicParent').value=r.parent;showTopics();},val('topicFind'));
  $('topicHeading').textContent=pathLabel(cat().topics,topic,'label')||'مطالعهٔ موضوعی';const h=$('topicArticles');h.replaceChildren();const src=val('topicSource'),ord=val('topicOrder');
  for(const i of items.filter(i=>i.kind!=='source'&&i.topics.includes(topic)&&(!src||i.refs.some(r=>r.source===src))).sort((a,b)=>b[ord].localeCompare(a[ord])))article(i,h);
  if(!h.children.length)h.textContent='برای خواندن، موضوع را انتخاب کنید و یادداشت یا گزیده‌ای را به آن وصل کنید.';
 }
 function showFolders(){
  tree(cat().folders,$('folderTree'),'name',folder,r=>{folder=r.id;$('folderName').value=r.name;$('folderParent').value=r.parent;showFolders();});$('rootDisplay').textContent=cat().root||'هنوز پوشهٔ مادر انتخاب نشده است.';$('folderRecover').hidden=!cat().pending;
  const h=$('folderArticles');h.replaceChildren();for(const i of items.filter(i=>members('placements',i.key).some(p=>p.folder===folder)))article(i,h);
 }
 function matches(i){const k=val('itemKind'),rv=val('itemReview');
  if(k==='inbox'&&(i.kind!=='note'||i.topics.length||cat().reflections.some(r=>r.note_id===i.id)||members('placements',i.key).length))return false;
  if(k==='unclassified'&&(i.kind!=='highlight'||i.topics.length||i.tags.length))return false;
  if(k==='unsourced'&&(i.kind!=='highlight'||i.refs.length))return false;
  return (!['note','source','highlight'].includes(k)||i.kind===k)&&(!val('itemTopic')||i.topics.includes(val('itemTopic')))&&(!val('itemSource')||i.refs.some(r=>r.source===val('itemSource')))&&(!val('itemType')||i.refs.some(r=>sources().find(s=>s.id===r.source)?.type===val('itemType')))&&(!rv||(i.review?.status||'none')===rv)&&(!filterDay||i.created.startsWith(filterDay))&&norm([i.name,i.body,...i.tags].join(' ')).includes(norm(val('itemText')));
 }
 function showItems(){
  const ord=val('itemOrder');const sort=i=>ord==='source'?srcName(i.refs[0]?.source):ord==='topic'?pathLabel(cat().topics,i.topics[0],'label'):ord==='due'?i.review?.due||'9999':i.created;
  const rows=items.filter(matches).sort((a,b)=>ord==='created'?sort(b).localeCompare(sort(a)):sort(a).localeCompare(sort(b),'fa'));
  options($('itemPick'),rows.map(i=>[i.key,i.name]));const group=val('itemGroup');
  if(group){
    const groups=new Map();
    for(const item of rows){
      const values=group==='topic'?item.topics.map(t=>pathLabel(cat().topics,t,'label')):group==='tag'?item.tags:group==='source'?item.refs.map(r=>srcName(r.source)):group==='type'?item.refs.map(r=>types[sources().find(s=>s.id===r.source)?.type]):group==='day'?[item.created.slice(0,10)?dateLabel(item.created.slice(0,10)):'']: [({active:'فعال',paused:'متوقف',ended:'پایان',cancelled:'پایان'})[item.review?.status]||'بدون مرور'];
      for(const name of new Set(values.length?values:['بدون دسته'])){const label=name||'بدون دسته';if(!groups.has(label))groups.set(label,[]);groups.get(label).push(item);}
    }
    $('itemPick').replaceChildren();for(const [label,entries] of groups){const g=node('optgroup');g.label=label;g.append(...entries.map(i=>new Option(i.name,i.key)));$('itemPick').append(g);}
  }
  if(rows.some(i=>i.key===key))$('itemPick').value=key;key=val('itemPick');const i=rows.find(i=>i.key===key),h=$('itemArticle'),links=$('itemLinks');
  h.replaceChildren();links.replaceChildren();$('itemTools').hidden=!i;if(!i){h.textContent='مطلبی با این فیلتر پیدا نشد.';return;}article(i,h,true);
  const unlink=(kind,id,title)=>button(links,'قطع '+title,()=>mutate('unlink',{target:key,kind,id}));
  for(const r of members('membership',key))unlink('topic',r.topic,pathLabel(cat().topics,r.topic,'label'));
  for(const r of members('tags',key))unlink('tag',r.norm,'برچسب '+r.label);
  for(const r of members('citations',key))unlink('citation',r.id,srcName(r.source)+' '+r.locator);
  for(const f of fileRows(key)){unlink('file',f.id,'پیوند '+f.rel);if(f.available)button(links,'در Explorer: '+f.rel,()=>api('catalog',{action:'explorer',id:f.id}));}
  $('linkFolder').value=members('placements',key)[0]?.folder||'';$('orgReview').hidden=i.kind==='source';$('archiveNote').hidden=$('deleteNote').hidden=i.kind!=='note';$('manualAdd').disabled=$('selectExcerpt').disabled=i.kind==='highlight';
 }
 function loadQueue(){const q=cat().reading_queue.find(q=>q.source===val('queueSource'));$('queueStatus').value=q?.status||'بعداً';$('queuePriority').value=q?.priority||3;$('queueReason').value=q?.reason||'';planned=q?.planned||'';$('queueDate').textContent=dateLabel(planned)||'تاریخ شروع پیشنهادی';}
 function showQueue(){const h=$('queueList');h.replaceChildren();for(const q of cat().reading_queue.filter(q=>!val('queueFilter')||q.status===val('queueFilter')).sort((a,b)=>a.priority-b.priority)){const box=node('article');box.className='catalog-article';box.append(node('h3',srcName(q.source)),node('p',[q.status,'اولویت '+fa(q.priority),dateLabel(q.planned),q.reason].filter(Boolean).join(' · ')));button(box,'ویرایش در فهرست',()=>{$('queueSource').value=q.source;loadQueue();});h.append(box);}if(!h.children.length)h.textContent='منبعی با این وضعیت ثبت نشده است.';}
 function render(){collect();const ts=cat().topics.filter(t=>t.status==='active').map(t=>[t.id,pathLabel(cat().topics,t.id,'label')]),fs=cat().folders.filter(f=>!f.archived).map(f=>[f.id,f.rel]),ss=sources().filter(s=>s.status==='active').map(s=>[s.id,s.title]);
  options($('captureTopics'),ts);for(const id of ['topicParent','linkTopic','itemTopic'])options($(id),ts,id==='linkTopic'?undefined:id==='itemTopic'?'همه':'سطح اول');
  for(const id of ['folderParent','linkFolder'])options($(id),fs,id==='folderParent'?'زیر پوشهٔ مادر':'بدون پوشه');
  for(const id of ['topicSource','itemSource','summaryRefs','linkSource','queueSource'])options($(id),ss,['topicSource','itemSource'].includes(id)?'همهٔ منابع':undefined);
  if(!ts.some(([id])=>id===topic))topic=ts[0]?.[0]||'';if(!fs.some(([id])=>id===folder))folder=fs[0]?.[0]||'';showTopics();showFolders();showItems();showQueue();
 }
 function mode(m){for(const b of document.querySelectorAll('[data-mode]')){const v=b.dataset.mode;b.setAttribute('aria-pressed',String(v===m));$('org'+v[0].toUpperCase()+v.slice(1)).hidden=v!==m;}if(m==='queue')loadQueue();}
 function open(t){go('organize');mode('items');key=t;for(const id of ['itemKind','itemSource','itemTopic','itemType','itemReview','itemText'])$(id).value='';filterDay='';$('itemDate').textContent='روز ثبت';showItems();$('itemPick').focus();}
 for(const b of document.querySelectorAll('[data-mode]'))b.onclick=()=>mode(b.dataset.mode);
 const tfields=()=>({name:val('topicName'),parent:val('topicParent')});on('topicCreate',()=>mutate('topic',tfields()));on('topicChange',()=>mutate('topic',{id:topic,...tfields()}));
 on('topicRemove',async()=>{if(topic&&await confirm('موضوع از درخت حذف شود؟ نوشته‌ها و منابع حفظ می‌شوند.'))await mutate('topic-delete',{id:topic});});
 on('saveSummary',async()=>{const body=val('topicSummary');await mutate('summary',{id:topic,title:val('topicSummaryTitle'),body,sources:[...$('summaryRefs').selectedOptions].map(o=>o.value)});if(body===val('topicSummary'))$('topicSummary').value='';});
 const ff=()=>({id:folder,name:val('folderName'),parent:val('folderParent')});on('folderCreate',()=>mutate('folder',ff()));on('folderMove',()=>preview('move',ff()));on('folderRelink',()=>preview('relink',ff()));on('setRoot',()=>preview('root',{path:val('rootPath')}));
 on('folderArchive',async()=>{if(await confirm('پوشه از درخت بایگانی شود؟ فایل‌ها حفظ می‌شوند.'))await mutate('folder-archive',{id:folder});});on('folderRecover',async()=>{const r=await api('catalog',{action:'recover'});await refresh();note(r.result==='ambiguous'?'مسیرها نیاز به بررسی دستی دارند.':'وضعیت انتقال بررسی شد.');});
 on('addTopic',()=>mutate('topic-link',{target:key,id:val('linkTopic')}));on('tagAdd',()=>mutate('tag',{target:key,name:val('tagText')}));on('placeItem',()=>mutate('place',{target:key,id:val('linkFolder')}));on('citeAdd',()=>mutate('citation',{target:key,id:val('linkSource'),locator:val('linkLocator')}));
 on('attachFile',()=>mutate('file',{target:key,path:val('filePath')}));on('browseFile',()=>browse(''));
 async function browse(path){const {entries}=await api('catalog',{action:'browse',path});const h=$('fileBrowser');h.replaceChildren();if(path)button(h,'پوشهٔ بالاتر',()=>browse(path.split('/').slice(0,-1).join('/')));for(const x of entries){const r=(path?path+'/':'')+x.name;button(h,(x.folder?'پوشه · ':'')+x.name,()=>{if(x.folder)return browse(r);$('filePath').value=r;h.replaceChildren();});}if(!entries.length)h.append(node('p','فایل پشتیبانی‌شده‌ای پیدا نشد.'));}
 function excerpt(target,body,locator,manual=false){const i=items.find(r=>r.key===target);let offset;const sel=getSelection();if(!manual&&sel.rangeCount){const range=sel.getRangeAt(0);const field=[$('orgBody'),$('bookBody')].find(e=>e&&e.contains(range.startContainer)&&e.contains(range.endContainer));if(field){const prefix=range.cloneRange();prefix.selectNodeContents(field);prefix.setEnd(range.startContainer,range.startOffset);offset=Array.from(prefix.toString()).length;}}return mutate('excerpt',{target,body,locator,manual,offset,content_revision:i?.content_revision||i?.section_records?.find(s=>s.kind==='body')?.revision});}
 on('manualAdd',()=>excerpt(key,val('manualExcerpt'),val('manualLocation'),true));on('selectExcerpt',()=>{const s=getSelection();if(!s.toString()||!$('orgBody').contains(s.anchorNode)||!$('orgBody').contains(s.focusNode))throw Error('عبارت را در متن همین مطلب انتخاب کنید.');return excerpt(key,s.toString(),val('manualLocation'));});
 for(const [id,v] of [['archiveNote','archived'],['deleteNote','deleted']])on(id,async()=>{if(await confirm('یادداشت از فهرست فعال خارج و مرور آن متوقف شود؟'))await mutate('note-status',{target:key,status:v});});
 $('orgReview').onclick=()=>beginEnroll(key,$('orgReview'));$('queueDate').onclick=()=>calendar.open(planned,false,$('queueDate'),v=>{planned=v;$('queueDate').textContent=dateLabel(v);});$('clearQueueDate').onclick=()=>{planned='';$('queueDate').textContent='تاریخ شروع پیشنهادی';};
 on('queueSave',()=>mutate('queue',{id:val('queueSource'),status:val('queueStatus'),reason:val('queueReason'),priority:Number(val('queuePriority')),planned}));
 $('queueFilter').onchange=showQueue;$('queueSource').onchange=loadQueue;$('topicFind').oninput=showTopics;$('topicSource').onchange=$('topicOrder').onchange=showTopics;
 $('itemPick').onchange=()=>{key=val('itemPick');showItems();};for(const id of ['itemKind','itemSource','itemTopic','itemType','itemReview','itemOrder','itemGroup'])$(id).onchange=showItems;$('itemText').oninput=showItems;
 $('itemDate').onclick=()=>calendar.open(filterDay,false,$('itemDate'),v=>{filterDay=v;$('itemDate').textContent=dateLabel(v);showItems();});$('itemDateClear').onclick=()=>{filterDay='';$('itemDate').textContent='روز ثبت';showItems();};
 $('libQuery').oninput=$('libKind').onchange=$('libFile').onchange=renderLibrary;
 function openTopic(id){topic=id;go('organize');mode('topics');showTopics();$('topicHeading').tabIndex=-1;$('topicHeading').focus();}
 return {render,open,openTopic,files,sourceMatches,excerpt};
}
