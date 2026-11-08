const { chromium } = require(process.env.PLAYWRIGHT_MODULE || require('path').join(process.env.APPDATA,'npm/node_modules/playwright'));
const fs=require('fs'),path=require('path'),os=require('os'),assert=require('assert/strict');
const {spawn}=require('child_process');
const root=path.resolve(__dirname,'..');
const runDir=path.join(root,'.test-runs','آزمون مرورگر '+Date.now());fs.mkdirSync(runDir,{recursive:true});
const evidence=path.join(root,'docs/evidence/ui-before');fs.mkdirSync(evidence,{recursive:true});
let executable=process.argv[2];
const results=[];let child,browser,session,failures=[];
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
function passed(name){results.push({name,status:'pass'});console.log('PASS '+name);}
async function start(data){
  const command=executable||'C:/Python314/python.exe';
  const args=executable?['--data',data,'--no-browser']:[path.join(root,'app/main.py'),'--data',data,'--no-browser'];
  child=spawn(command,args,{cwd:os.tmpdir(),windowsHide:true,stdio:'pipe',env:{...process.env,PYTHONPATH:'',PYTHONHOME:''}});
  let errors='';child.stderr.on('data',d=>errors+=d);
  const sessionPath=path.join(data,'session.json');
  for(let i=0;i<150;i++){if(fs.existsSync(sessionPath)){try{return JSON.parse(fs.readFileSync(sessionPath,'utf8'));}catch{}}if(child.exitCode!==null)throw new Error('Backend exited '+child.exitCode+' '+errors);await sleep(100);}
  throw new Error('No session '+errors);
}
async function clickRoute(page,route){await page.locator('nav [data-route="'+route+'"]').click();}
async function api(page,route,body){return page.evaluate(async({route,body})=>{const state=await fetch('/api/state').then(r=>r.json());const r=await fetch('/api/'+route,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF':state.csrf},body:JSON.stringify(body)});return {status:r.status,body:await r.json()};},{route,body});}
async function save(page){await page.locator('#saveNote').click();await page.waitForFunction(()=>document.querySelector('#saveStatus').textContent==='ذخیره شد');}
async function quit(page){await page.locator('#quit').click();await page.locator('#confirmAccept').click();await page.waitForFunction(()=>document.body.classList.contains('shutdown'));for(let i=0;i<100&&child.exitCode===null;i++)await sleep(100);assert.equal(child.exitCode,0,'backend should exit');}
async function cleanContext(browser){const ctx=await browser.newContext({viewport:{width:1280,height:1000},permissions:['clipboard-read','clipboard-write']});await ctx.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());return ctx;}

async function stateOf(page){return page.evaluate(()=>fetch('/api/state').then(r=>r.json()));}
async function ready(page){await page.goto(session.url);await page.waitForLoadState('networkidle');await page.waitForFunction(()=>document.querySelector('#globalStatus').textContent.startsWith('آماده'));}
async function saved(page){await page.waitForFunction(()=>document.querySelector('#saveStatus').textContent==='ذخیره شد');}
async function bookSaved(page){await page.waitForFunction(()=>document.querySelector('#sourceStatus').textContent==='کتاب ذخیره شد');}
async function tabTo(page,id){for(let i=0;i<60;i++){if(await page.evaluate(id=>document.activeElement.id===id,id))return;await page.keyboard.press('Tab');}throw Error('Unreachable '+id);}
(async()=>{
executable=path.join(root,'dist/Current/app/MyStudySystem.exe');session=await start(path.join(runDir,'synthetic'));
browser=await chromium.launch({channel:'chrome',headless:true});const ctx=await cleanContext(browser),p=await ctx.newPage();
await p.addInitScript(()=>{window.shifts=[];new PerformanceObserver(list=>{for(const x of list.getEntries())window.shifts.push({value:x.value,input:x.hadRecentInput});}).observe({type:'layout-shift',buffered:true});});
p.on('pageerror',e=>failures.push(e.message));await ready(p);await api(p,'seed',{});await api(p,'review',{command:'enroll',target:'note:note-1',revision:0,operation_id:'audit-enroll'});
await api(p,'catalog',{action:'topic',revision:0,name:'یادگیری و تمرین',id:'audit-topic',operation_id:'audit-topic'});
await api(p,'catalog',{action:'topic-link',revision:1,target:'note:note-1',id:'audit-topic',operation_id:'audit-link'});await p.reload();await p.waitForLoadState('networkidle');await p.evaluate(()=>document.fonts.ready);
const info={browser:browser.version(),version:(await stateOf(p)).version,metrics:[],dialogs:[],special:[],errors:failures};
try{info.axe=require.resolve('axe-core')}catch{info.axe='unavailable'}
const route=async r=>{await p.locator('nav [data-route="'+r+'"]').evaluate(b=>b.click());await p.evaluate(()=>window.scrollTo(0,0));};
async function measure(){return p.evaluate(()=>{
 const q=s=>document.querySelector(s),rect=e=>e.getBoundingClientRect(),box=s=>{const e=q(s);if(!e)return null;const r=rect(e);return [r.x,r.y,r.width,r.height].map(Math.round);},sec=q('main>section:not([hidden])'),h=sec.querySelector('h1'),controls=[...sec.querySelectorAll('button,input,select,textarea,summary')].filter(e=>e.checkVisibility({contentVisibilityAuto:true,visibilityProperty:true})&&(!e.closest('details:not([open])')||e.tagName==='SUMMARY'&&e.parentElement===e.closest('details:not([open])'))&&e.getClientRects().length&&rect(e).width&&rect(e).height);
 const overlaps=[];for(let i=0;i<controls.length;i++)for(let j=i+1;j<controls.length;j++){const a=rect(controls[i]),b=rect(controls[j]);if(Math.min(a.right,b.right)-Math.max(a.left,b.left)>2&&Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top)>2)overlaps.push([controls[i].id||controls[i].textContent.trim().slice(0,20),controls[j].id||controls[j].textContent.trim().slice(0,20)]);}
 const nav=q('nav'),buttons=[...nav.querySelectorAll('button')];return {view:sec.id,main:box('main'),content:Math.round(rect(sec).width),heading:Math.round(rect(h).top+scrollY),side:box('.sidebar'),head:box('.topbar'),status:box('#globalStatus'),card:box('.continue-panel'),navCount:buttons.filter(b=>b.getClientRects().length).length,navScroll:nav.scrollWidth-nav.clientWidth,overflow:document.documentElement.scrollWidth-innerWidth,overlaps,viewportHeight:innerHeight,firstAction:controls[0]?Math.round(rect(controls[0]).top+scrollY):null,shortControls:controls.filter(e=>rect(e).height<32).map(e=>e.id||e.tagName),font:getComputedStyle(h).fontSize,base:getComputedStyle(document.body).fontSize,leading:getComputedStyle(document.body).lineHeight,dir:getComputedStyle(sec).direction};
});}
await route('capture');await p.locator('#duePicker').click();await p.keyboard.press('Escape');
await route('search');await p.locator('#query').fill('مکث');await p.locator('#searchForm button').click();await p.waitForSelector('#results article');
const cdp=await ctx.newCDPSession(p);await cdp.send('DOM.enable');await cdp.send('CSS.enable');const doc=await cdp.send('DOM.getDocument');const id=await cdp.send('DOM.querySelector',{nodeId:doc.root.nodeId,selector:'#searchHeading'});info.fonts=(await cdp.send('CSS.getPlatformFontsForNode',{nodeId:id.nodeId})).fonts;
for(const theme of ['light','dark']){
 if(await p.evaluate(()=>document.documentElement.dataset.theme)!==theme)await p.locator('#theme').click();
 for(const w of [375,768,1024,1280,1366,1440,1536,1645,1920,2560]){
 const ht=w===375?667:w===768?768:w<=1440?720:w===1536?864:w===2560?1440:1080;await p.setViewportSize({width:w,height:ht});
 for(const view of ['home','capture','library','organize','study','review','search','help']){
 await route(view);
 for(const mode of view==='organize'?['topics','folders','items','queue']:['']){
 if(mode)await p.locator('[data-mode="'+mode+'"]').evaluate(b=>b.click());
 const m=await measure();info.metrics.push({theme,w,mode,...m});
 if(theme==='light'&&[1024,1280,1920,2560].includes(w)||theme==='dark'&&w===1280&&['home','organize','review','study'].includes(view)||w===375&&theme==='light'&&['study','capture','home'].includes(view))await p.screenshot({path:path.join(evidence,[view,mode,theme,w].filter(Boolean).join('-')+'.png')});
 }}
 for(const id of ['calendar','rvEnroll','confirmDialog','latestDialog']){
 await p.locator('#'+id).evaluate(d=>d.showModal());
 const geom=await p.locator('#'+id).evaluate(d=>{const r=d.getBoundingClientRect();return {width:r.width,height:r.height,out:r.left<0||r.right>innerWidth+1||r.top<0||r.bottom>innerHeight+1,internalOverflow:d.scrollHeight-d.clientHeight};});
 await p.keyboard.press('Escape');info.dialogs.push({theme,w,id,...geom,closed:!await p.locator('#'+id).isVisible()});}
 }console.log('Measured '+theme);
}
await p.setViewportSize({width:1645,height:900});await route('organize');for(const collapsed of [true,false]){await p.locator('#collapse').click();info.special.push({collapsed,...await measure()});}
await p.setViewportSize({width:1280,height:540});await route('capture');await p.locator('#duePicker').click();info.special.push({calendar540:await p.locator('#calendar').boundingBox(),days:await p.locator('#calendarDays button').count()});await p.keyboard.press('Escape');
await route('review');await p.locator('#rvStart').click();info.special.push({answerBefore:await p.locator('#answerBody').textContent()});await p.locator('#reveal').click();await p.waitForSelector('#gradeButtons button');info.special.push({revealedFocus:await p.evaluate(()=>document.activeElement.id)});
await route('library');await p.locator('#newBook').click();await p.locator('#sourceKind').selectOption('website');info.special.push({websiteVisible:await p.locator('#webFields').isVisible()});
info.shifts=await p.evaluate(()=>window.shifts);fs.writeFileSync(path.join(evidence,'baseline.json'),JSON.stringify(info,null,2));
await p.locator('#sourceTitle').fill('منبع ساختگی بررسی');await p.locator('#saveBook').click();await bookSaved(p);await quit(p);console.log(info.metrics.length+' route states, '+info.dialogs.length+' dialog states');
})().catch(e=>{console.error(e);process.exitCode=1}).finally(async()=>{if(browser)await browser.close().catch(()=>{});if(child&&child.exitCode===null){if(session?.pid)try{process.kill(session.pid)}catch{}child.kill();}});
