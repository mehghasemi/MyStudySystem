const { chromium } = require(process.env.PLAYWRIGHT_MODULE || require('path').join(process.env.APPDATA,'npm/node_modules/playwright'));
const fs=require('fs'),path=require('path'),os=require('os'),assert=require('assert/strict');
const {spawn}=require('child_process');
const root=path.resolve(__dirname,'..');
const runDir=path.join(root,'.test-runs','آزمون مرورگر '+Date.now());fs.mkdirSync(runDir,{recursive:true});
const evidence=path.join(root,'docs/evidence/m1b');fs.mkdirSync(evidence,{recursive:true});
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
const candidate=path.resolve(process.argv[2]),prior=path.resolve(process.argv[3]),data=path.join(runDir,'داده');
executable=prior;session=await start(data);
browser=await chromium.launch({channel:'chrome',headless:true});let ctx=await cleanContext(browser),p=await ctx.newPage();await ready(p);
await api(p,'seed',{});let before=await stateOf(p);assert.equal(before.version,'M1a-r3');await quit(p);await ctx.close();
executable=candidate;session=await start(data);ctx=await cleanContext(browser);p=await ctx.newPage();p.on('pageerror',e=>failures.push(e.message));await ready(p);
let after=await stateOf(p);assert.equal(after.schema,4);assert.deepEqual(after.notes,before.notes);assert.deepEqual(after.sources,before.sources);assert.deepEqual(after.highlights,before.highlights);assert.equal(after.review.rows.length,0);passed('real app upgrade from r3 preserves existing notes, sections, sources, bookmarks and excerpts without automatic scheduling');
await clickRoute(p,'capture');await p.locator('#noteList button').first().click();const title=await p.locator('#noteTitle').inputValue(),body=await p.locator('#noteBody').inputValue();
await p.locator('#rvAddNote').focus();await p.keyboard.press('Enter');await p.locator('#rvCueInput').fill('سرنخ ساختگی');await p.locator('#rvEnrollOk').click();await p.waitForSelector('#rvEnroll',{state:'hidden'});await clickRoute(p,'review');await p.waitForSelector('#rvPanel:visible');
assert.ok(!(await p.locator('#review').ariaSnapshot()).includes(title));assert.equal(await p.locator('#answerBody').textContent(),'');passed('explicit keyboard enrollment and neutral cue');
await p.locator('#rvRead').click();await p.waitForSelector('#answerArea:visible');assert.equal(await p.locator('#answerBody').textContent(),body);assert.equal((await stateOf(p)).review.used,0);await p.locator('#hideAnswer').click();passed('read only reveals original content without consuming quota');
await p.locator('#rvStart').click();await p.locator('#recallBody').fill('پاسخ شخصی فارسی English');await p.waitForFunction(()=>document.getElementById('rvMsg').textContent.includes('پیش‌نویس پاسخ ذخیره شد'));await quit(p);await ctx.close();await browser.close();browser=null;
session=await start(data);browser=await chromium.launch({channel:'msedge',headless:true});ctx=await cleanContext(browser);p=await ctx.newPage();p.on('pageerror',e=>failures.push(e.message));await ready(p);await clickRoute(p,'review');await p.locator('#rvStart').click();await p.waitForFunction(()=>document.getElementById('recallBody').value==='پاسخ شخصی فارسی English');passed('Edge fresh profile resumes durable answer after full exit');
await p.locator('#reveal').focus();await p.keyboard.press('Enter');await p.waitForSelector('#gradeButtons button');await p.locator('#gradeButtons button').last().click();
await p.locator('#rvDate').click();await p.locator('#calendarDays button.selected').press('ArrowLeft');await p.locator('#calendarApply').click();const stale=await ctx.newPage();await ready(stale);await clickRoute(stale,'review');await stale.locator('#rvStart').click();await stale.locator('#reveal').click();await stale.locator('#gradeButtons button').first().click();
let dropped=false;
await p.route('**/api/review',async route=>{if(!dropped&&route.request().postDataJSON().command==='grade'){dropped=true;await route.fetch();await route.abort();}else await route.continue();});
await p.locator('#rvCommit').click();await p.waitForSelector('#rvReload:visible');await p.locator('#rvCommit').click();await p.waitForFunction(()=>document.getElementById('rvMsg').textContent==='نتیجه ثبت شد.');await p.unroute('**/api/review');assert.equal((await stateOf(p)).review.used,1);
await stale.locator('#rvCommit').click();await stale.waitForSelector('#rvReload:visible');assert.equal(await stale.locator('#recallBody').inputValue(),'پاسخ شخصی فارسی English');assert.equal((await stateOf(stale)).review.used,1);await stale.close();passed('lost grade response retries once; second real tab cannot record stale grade and retains answer');

after=await stateOf(p);assert.equal(after.review.used,1);assert.equal(after.review.rows[0].turn,2);assert.equal(after.review.rows[0].step,2);passed('result plus Jalali date commits one attempt and advances stage');
assert.equal(await p.locator('#rvHistory').textContent(),'');await p.locator('#rvRead').click();await p.waitForFunction(()=>document.getElementById('rvHistory').textContent.includes('پاسخ شخصی فارسی English'));await p.locator('#rvReflection').evaluate(e=>e.closest('details').open=true);await p.locator('#rvReflection').fill('برداشت جدا');await p.locator('#rvReflect').click();await p.waitForFunction(()=>document.getElementById('rvReflection').value==='');await p.locator('#hideAnswer').click();
await p.locator('#rvUndo').evaluate(e=>e.closest('details').open=true);await p.locator('#rvUndo').click();await p.locator('#confirmAccept').click();await p.waitForFunction(()=>document.getElementById('rvInfo').textContent.includes('نوبت ۱'));after=await stateOf(p);assert.equal(after.review.used,0);assert.equal(after.review.rows[0].step,1);assert.ok(after.notes.some(n=>n.body==='برداشت جدا'));passed('Undo restores previous due, turn and quota while retaining answer and reflection');
for(const width of [1024,1280])for(const zoom of [1,2])for(const theme of ['dark','light']){
 await p.setViewportSize({width,height:900});await p.evaluate(({zoom,theme})=>{document.body.style.zoom=zoom;document.documentElement.dataset.theme=theme},{zoom,theme});
 assert.ok(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));await p.screenshot({path:path.join(evidence,'review-'+width+'-'+zoom+'-'+theme+'.png'),fullPage:true});
}
passed('review reflows in eight width/theme/CSS zoom combinations');await p.evaluate(()=>document.body.style.zoom=1);
assert.deepEqual(failures,[]);await quit(p);passed('clean exit with no uncaught browser errors');
})().catch(e=>{console.error(e.stack);results.push({name:e.message,status:'fail'});process.exitCode=1;}).finally(async()=>{if(browser)await browser.close().catch(()=>{});if(child&&child.exitCode===null)child.kill();fs.writeFileSync(path.join(evidence,'browser.json'),JSON.stringify(results,null,2));});
