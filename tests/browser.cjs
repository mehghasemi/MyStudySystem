const { chromium } = require(process.env.PLAYWRIGHT_MODULE || require('path').join(process.env.APPDATA,'npm/node_modules/playwright'));
const fs=require('fs'),path=require('path'),os=require('os'),assert=require('assert/strict');
const {spawn}=require('child_process');
const root=path.resolve(__dirname,'..');
const runDir=path.join(root,'.test-runs','آزمون مرورگر '+Date.now());fs.mkdirSync(runDir,{recursive:true});
const evidence=path.join(root,'docs/evidence');fs.mkdirSync(evidence,{recursive:true});
const executable=process.argv[2];
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

(async()=>{
const data=path.join(runDir,'داده آزمایشی');session=await start(data);
browser=await chromium.launch({channel:'chrome',headless:true});
const context=await cleanContext(browser),page=await context.newPage();page.on('pageerror',e=>failures.push(e.message));
await page.goto(session.url);await page.waitForLoadState('networkidle');await page.waitForFunction(()=>document.querySelector('#globalStatus').textContent.startsWith('آماده'));
const dom=await page.locator('main').innerText();assert.ok(dom.includes('ایجاد دادهٔ آزمایشی'));passed('fresh profile, explicit seed, local requests only');
await page.locator('#seed').click();await page.waitForSelector('#homeContent:not([hidden])');
await page.screenshot({path:path.join(evidence,'home-light-1280.png'),fullPage:true});
await clickRoute(page,'capture');await page.locator('#noteTitle').focus();await page.keyboard.insertText('آزمون فارسی و English');await page.keyboard.press('Tab');
const text='يادگيري كافي ۱۲۳\nمی‌توانم مکث کنم.\n# عنوان **خام**\nhttps://example.org/a?b=1\n<script>window.bad=true</script>';
await page.evaluate(t=>navigator.clipboard.writeText(t),text);await page.locator('#noteBody').focus();await page.keyboard.press('Control+V');assert.equal(await page.locator('#noteBody').inputValue(),text);
passed('mixed Persian/English clipboard paste preserves exact text');
await page.locator('#duePicker').focus();await page.keyboard.press('Enter');await page.waitForSelector('#calendar[open]');
await page.locator('#calendarYear').selectOption('1403');await page.locator('#calendarMonth').selectOption('12');assert.equal(await page.locator('#calendarDays button').count(),30);
await page.locator('#calendarDays button').last().focus();await page.keyboard.press('Enter');await page.keyboard.press('ArrowLeft');assert.equal(await page.locator('#calendarMonth').inputValue(),'1');assert.equal(await page.locator('#calendarYear').inputValue(),'1404');
await page.locator('#calendarApply').focus();await page.keyboard.press('Enter');assert.equal(await page.locator('#duePicker').innerText(),'۱ فروردین ۱۴۰۴');
assert.equal(await page.evaluate(()=>document.activeElement.id),'duePicker');passed('Jalali leap year/year boundary and keyboard focus restoration');
await page.locator('#timePicker').click();await page.locator('#calendarYear').selectOption('1405');await page.locator('#calendarMonth').selectOption('8');await page.locator('#calendarDays button').nth(14).click();await page.locator('#hour').fill('23');await page.locator('#minute').fill('45');await page.locator('#calendarApply').click();
await save(page);const stored=await page.evaluate(()=>fetch('/api/state').then(r=>r.json()));const saved=stored.notes.find(n=>n.title==='آزمون فارسی و English');assert.equal(saved.body,text);assert.equal(saved.due,'2025-03-21');assert.equal(saved.at_utc,'2026-11-06T20:15:00.000Z');passed('date-only and Tehran datetime stored independently');
await page.screenshot({path:path.join(evidence,'capture-light-1280.png'),fullPage:true});
// Browser-level rejection after storage committed: replay must not add a revision.
let drop=true;await page.route('**/api/save',async r=>{if(drop){drop=false;await r.fetch();await r.abort('connectionfailed');}else await r.continue();});
await page.locator('#noteBody').fill(text+'\nپس از قطع پاسخ');await page.locator('#saveNote').click();await page.waitForSelector('#saveError:not([hidden])');assert.ok((await page.locator('#noteBody').inputValue()).endsWith('پس از قطع پاسخ'));
await save(page);await page.unroute('**/api/save');let after=await page.evaluate(()=>fetch('/api/state').then(r=>r.json()));assert.equal(after.notes.find(n=>n.id===saved.id).revision,2);passed('lost HTTP response after commit, retry is idempotent');
// Two real tabs load the same revision, second one must keep its draft.
const second=await context.newPage();await second.goto(session.url);await second.waitForLoadState('networkidle');await clickRoute(second,'capture');await second.locator('#noteList button').filter({hasText:'آزمون فارسی و English'}).click();
await page.locator('#noteBody').fill('متن برنده از تب اول');await save(page);
await second.locator('#noteBody').fill('پیش‌نویس تب دوم');await second.locator('#saveNote').click();await second.waitForSelector('#conflictActions:not([hidden])');assert.equal(await second.locator('#noteBody').inputValue(),'پیش‌نویس تب دوم');
await second.locator('#showLatest').click();await second.waitForSelector('#latestDialog[open]');assert.ok((await second.locator('#latestText').innerText()).includes('متن برنده'));await second.locator('#closeLatest').click();
let blocked=await api(page,'shutdown',{});assert.equal(blocked.status,409);passed('two tabs conflict, retained draft, latest dialog and dirty-tab exit guard');
await second.locator('#saveSeparate').click();await second.waitForFunction(()=>document.querySelector('#saveStatus').textContent==='ذخیره شد');await second.close();
await clickRoute(page,'study');await page.locator('#bookPage').fill('48');await page.locator('#savePage').click();await page.waitForFunction(()=>document.querySelector('#pageStatus').textContent.includes('ثبت شد'));
await page.locator('#bookBody').focus();await page.evaluate(()=>{const e=document.querySelector('#bookBody'),r=document.createRange();r.setStart(e.firstChild,0);r.setEnd(e.firstChild,40);const s=getSelection();s.removeAllRanges();s.addRange(r);});await page.locator('#highlight').click();await page.waitForFunction(()=>document.querySelectorAll('#highlightList blockquote').length===2);
await page.screenshot({path:path.join(evidence,'study-light-1280.png'),fullPage:true});passed('study marker and selected highlight persist');
await clickRoute(page,'review');await page.locator('#reviewSelect').selectOption('note-1');assert.equal(await page.locator('#answerBody').textContent(),'');let tree=await page.locator('#review').ariaSnapshot();assert.ok(!tree.includes('Pause'));assert.ok(!tree.includes('نفس آرام'));await page.locator('#reveal').focus();await page.keyboard.press('Enter');await page.waitForSelector('#answerArea:not([hidden])');assert.ok((await page.locator('#answerBody').innerText()).includes('Pause'));assert.equal(await page.evaluate(()=>document.activeElement.id),'answerHeading');
await page.locator('#gradeButtons button').last().focus();await page.keyboard.press('Enter');assert.ok((await page.locator('#gradePreview').innerText()).includes('ثبت نشد'));await page.screenshot({path:path.join(evidence,'review-revealed-light-1280.png'),fullPage:true});await page.locator('#hideAnswer').click();await page.screenshot({path:path.join(evidence,'review-cue-light-1280.png'),fullPage:true});passed('review answer absent from DOM/accessibility before reveal, grades are preview only');
await clickRoute(page,'search');await page.locator('#query').fill('يادگيري');await page.locator('#searchForm button').click();await page.waitForFunction(()=>document.querySelector('#searchStatus').textContent.includes('نتیجه'));assert.ok(await page.locator('#results article').count()>0);assert.equal(await page.evaluate(()=>window.bad),undefined);passed('Persian search variants and content rendered without script execution');
// Accessibility and reflow matrix (CSS zoom is explicitly a simulation, not OS/browser zoom).
for(const theme of ['light','dark']){
 if(await page.locator('html').getAttribute('data-theme')!==theme)await page.locator('#theme').click();
 for(const width of [1024,1280]){await page.setViewportSize({width,height:1100});for(const zoom of [1,2]){
  await page.evaluate(z=>document.documentElement.style.zoom=String(z),zoom);
  for(const screen of ['capture','study','review']){await clickRoute(page,screen);assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+2),`horizontal overflow ${screen} ${width} ${zoom}`);await page.screenshot({path:path.join(evidence,`${screen}-${theme}-${width}-zoom${zoom}.png`),fullPage:true});}
 }}
}
await page.evaluate(()=>document.documentElement.style.zoom='1');await page.setViewportSize({width:1280,height:1000});passed('3 screens x 2 themes x 2 widths x 2 simulated zoom levels, no horizontal overflow');
const contrast=await page.evaluate(()=>{function rgb(s){return s.match(/[\d.]+/g).slice(0,3).map(Number);}function lum(a){return a.map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;}).reduce((s,v,i)=>s+v*[.2126,.7152,.0722][i],0);}const c=getComputedStyle(document.documentElement);const pairs=[['--ink','--paper'],['--muted','--paper'],['--ink','--bg'],['--muted','--bg'],['--accent','--paper'],['--error','--paper']];return pairs.map(([a,b])=>{const el=document.createElement('span');document.body.append(el);el.style.color=c.getPropertyValue(a);const x=lum(rgb(getComputedStyle(el).color));el.style.color=c.getPropertyValue(b);const y=lum(rgb(getComputedStyle(el).color));el.remove();return {a,b,ratio:(Math.max(x,y)+.05)/(Math.min(x,y)+.05)};});});assert.ok(contrast.every(x=>x.ratio>=4.5),JSON.stringify(contrast));passed('dark theme text-token contrast >= 4.5');
// Dialog keyboard containment and Escape return.
await clickRoute(page,'capture');await page.locator('#duePicker').click();for(let i=0;i<20;i++){await page.keyboard.press('Tab');assert.ok(await page.evaluate(()=>document.querySelector('#calendar').contains(document.activeElement)));}await page.keyboard.press('Escape');assert.equal(await page.evaluate(()=>document.activeElement.id),'duePicker');passed('calendar modal keyboard containment and Escape');
const denied=await page.evaluate(async()=>{let r=await fetch('/api/save',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});return r.status;});assert.equal(denied,403);const unknown=await page.request.get(new URL('/media',page.url()).href);assert.equal(unknown.status(),404);passed('missing CSRF rejected and deferred media endpoint absent');
await page.locator('#collapse').click();await quit(page);await browser.close();browser=null;
assert.ok(!fs.existsSync(path.join(data,'session.json')));passed('full exit removes session and releases backend');
// Restart using a clean Edge profile and a different working directory.
session=await start(data);browser=await chromium.launch({channel:'msedge',headless:true});const edgeContext=await cleanContext(browser),edge=await edgeContext.newPage();await edge.goto(session.url);await edge.waitForLoadState('networkidle');await edge.waitForFunction(()=>document.querySelector('#globalStatus').textContent.startsWith('آماده'));
const reopened=await edge.evaluate(()=>fetch('/api/state').then(r=>r.json()));assert.equal(reopened.sources.find(s=>s.id==='book-1').page,48);assert.equal(reopened.notes.find(n=>n.id===saved.id).due,'2025-03-21');assert.equal(reopened.notes.find(n=>n.id===saved.id).at_utc,'2026-11-06T20:15:00.000Z');assert.equal(reopened.settings.theme,'dark');assert.equal(reopened.settings.collapsed,true);assert.ok(reopened.notes.some(n=>n.body==='پیش‌نویس تب دوم'));passed('Edge fresh profile reopen preserves text, dates, bookmark, theme and menu');
// Duplicate process should exit without altering active session or opening a second writer.
const before=fs.readFileSync(path.join(data,'session.json'),'utf8');const duplicate=spawn(executable||'C:/Python314/python.exe',executable?['--data',data,'--no-browser']:[path.join(root,'app/main.py'),'--data',data,'--no-browser'],{windowsHide:true,stdio:'ignore'});await new Promise(resolve=>duplicate.once('exit',resolve));assert.equal(duplicate.exitCode,0);assert.equal(fs.readFileSync(path.join(data,'session.json'),'utf8'),before);passed('duplicate launch reuses active data owner');
await clickRoute(edge,'review');await edge.locator('#reviewSelect').selectOption('note-1');await edge.locator('#reveal').focus();await edge.keyboard.press('Enter');assert.ok((await edge.locator('#answerBody').innerText()).includes('Pause'));await edge.screenshot({path:path.join(evidence,'edge-review-dark.png'),fullPage:true});
await quit(edge);await browser.close();browser=null;assert.deepEqual(failures,[]);passed('Chrome has no uncaught page errors; Edge keyboard review and shutdown');
} )().catch(e=>{console.error(e.stack);results.push({name:e.message,status:'fail'});process.exitCode=1;}).finally(async()=>{if(browser)await browser.close().catch(()=>{});if(child&&child.exitCode===null)child.kill();fs.writeFileSync(path.join(evidence,executable?'browser-packaged.json':'browser-source.json'),JSON.stringify({timestamp:new Date().toISOString(),executable:executable||'source',runDir,results},null,2));console.log('RESULT '+results.filter(r=>r.status==='pass').length+' pass; '+results.filter(r=>r.status==='fail').length+' fail');});
