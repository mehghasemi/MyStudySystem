"""Verify the actual ZIP with an empty PATH and a default relative data directory."""
import hashlib
import http.cookiejar
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.request
import urllib.error
import zipfile

ROOT=Path(__file__).resolve().parents[1]
archive=ROOT/'dist/MyStudySystem-M1a-r3-win.zip'
base=ROOT/'.test-runs'/('چرخه بسته '+str(time.time_ns()))
base.mkdir(parents=True)
results=[]
process=None

def passed(name,**detail):
    results.append(dict(name=name,status='pass',**detail));print('PASS '+name)

def extract(target):
    with zipfile.ZipFile(archive) as z:
        for name in z.namelist():
            assert (target/name).resolve().is_relative_to(target.resolve())
            assert not name.startswith('data/')
            assert not name.endswith(('.db','.sqlite','.mp3','.m4a','.log'))
        z.extractall(target)

def start(target, *args):
    global process
    env={**os.environ,'PATH':str(Path(os.environ['WINDIR'])/'System32'),'PYTHONHOME':'','PYTHONPATH':''}
    process=subprocess.Popen([str(target/'app/MyStudySystem.exe'),'--no-browser',*args],cwd=os.environ['TEMP'],env=env)
    session=target/'data/session.json'
    for _ in range(150):
        if session.exists():
            info=json.loads(session.read_text(encoding='utf-8'));break
        if process.poll() is not None:raise AssertionError('launcher exited '+str(process.returncode))
        time.sleep(.1)
    else:raise AssertionError('session not created')
    opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),urllib.request.ProxyHandler({}))
    opener.open(info['url']).read()
    origin=f"http://127.0.0.1:{info['port']}"
    state=json.loads(opener.open(origin+'/api/state').read())
    return opener,origin,state,info

def post(client,origin,state,route,body):
    req=urllib.request.Request(origin+'/api/'+route,data=json.dumps(body).encode(),headers={'Content-Type':'application/json','X-CSRF':state['csrf'],'Origin':origin})
    return json.loads(client.open(req).read())

def stop(client,origin,state):
    post(client,origin,state,'shutdown',{})
    assert process.wait(timeout=15)==0

try:
    target=base/'نصب تازه';extract(target)
    manifest=json.loads((target/'BUILD_MANIFEST.json').read_text())
    with zipfile.ZipFile(archive) as z:
        assert set(z.namelist()) == set(manifest['files']) | {'BUILD_MANIFEST.json'}
    assert all(hashlib.sha256((target/p).read_bytes()).hexdigest()==h for p,h in manifest['files'].items())
    passed('ZIP allowlist and all manifest hashes verified',sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),source_id=manifest['source_id'])
    client,origin,state,info=start(target)
    assert Path(state['data_path'])==target/'data'
    assert state['notes']==[]
    passed('launcher creates sibling data with different cwd and no system Python PATH')
    req=urllib.request.Request(origin+'/api/state',headers={'Host':'attacker.invalid'})
    try:client.open(req);raise AssertionError('untrusted Host accepted')
    except urllib.error.HTTPError as e:assert e.code==403
    req=urllib.request.Request(origin+'/api/seed',data=b'{}',headers={'Origin':'https://attacker.invalid','X-CSRF':state['csrf'],'Content-Type':'application/json'})
    try:client.open(req);raise AssertionError('foreign origin accepted')
    except urllib.error.HTTPError as e:assert e.code==403
    passed('Host and Origin rejection verified on packaged executable')
    seed=post(client,origin,state,'seed',{})
    note={'id':'lifecycle','title':'متن چرخه بسته','body':'سلام؛ محتوا پس از تعویض app می‌ماند.','revision':0,'due':'2026-11-07','at_utc':'2026-11-06T23:29:00Z','operation_id':'lifecycle-1'}
    post(client,origin,state,'save',note)
    stop(client,origin,state)
    assert not (target/'data/session.json').exists()
    # All renamed directories are resolved and verified to remain under this test root.
    old=(target/'app').resolve();keep=(target/'app-previous').resolve()
    assert old.is_relative_to(base.resolve()) and keep.is_relative_to(base.resolve())
    old.rename(keep)
    replacement=base/'نسخه سازگار';extract(replacement)
    shutil.copytree(replacement/'app',target/'app')
    client,origin,state,info=start(target)
    current=next(n for n in state['notes'] if n['id']=='lifecycle')
    assert all(current[k]==note[k] for k in ['title','body','due','at_utc'])
    stop(client,origin,state)
    passed('full exit releases app; compatible app replacement preserves existing DB and dates')
    prior=base/'قبلی';prior.mkdir()
    with zipfile.ZipFile(ROOT/'dist/MyStudySystem-M1a-r2-win.zip') as z:z.extractall(prior)
    client,origin,state,info=start(prior)
    post(client,origin,state,'source-save',dict(id='reading',title='کتاب نمونه',body='اصل متن',revision=0,operation_id='book'))
    post(client,origin,state,'bookmark',dict(id='reading',page=47,chapter='فصل اول',revision=1,operation_id='page'))
    post(client,origin,state,'save',dict(note,source_id='reading',sections={'personal':'برداشت من'}))
    stop(client,origin,state)
    src=(prior/'app').resolve();dst=(prior/'app-r2').resolve()
    assert src.is_relative_to(base.resolve()) and dst.is_relative_to(base.resolve())
    src.rename(dst);shutil.copytree(replacement/'app',src)
    client,origin,state,info=start(prior)
    assert state['version']=='M1a-r3' and len(state['notes'])==len(state['sources'])==1
    assert state['notes'][0]['body']==note['body'] and state['notes'][0]['sections']['personal']=='برداشت من' and state['notes'][0]['source_id']=='reading'
    assert state['sources'][0]['page']==47 and state['sources'][0]['body']=='اصل متن'
    stop(client,origin,state)
    passed('r2 to r3 keeps personal library, note sections, reference and reading page')
    # Upgrade a real G0 package with persisted data, not a reconstructed schema fixture.
    upgrade=base/'ارتقای G0';upgrade.mkdir()
    with zipfile.ZipFile(ROOT/'dist/MyStudySystem-G0-r1-win.zip') as z:z.extractall(upgrade)
    client,origin,state,info=start(upgrade)
    post(client,origin,state,'seed',{});post(client,origin,state,'save',note);stop(client,origin,state)
    old=(upgrade/'app').resolve();keep=(upgrade/'app-g0').resolve()
    assert old.is_relative_to(base.resolve()) and keep.is_relative_to(base.resolve())
    old.rename(keep);shutil.copytree(replacement/'app',upgrade/'app')
    client,origin,state,info=start(upgrade)
    assert state['schema']==3
    current=next(n for n in state['notes'] if n['id']=='lifecycle')
    assert all(current[k]==note[k] for k in ['title','body','due','at_utc'])
    assert next(s for s in state['sources'] if s['id']=='book-1')['page']==47
    stop(client,origin,state)
    before=(upgrade/'data/study.sqlite').read_bytes()
    p=subprocess.run([str(keep/'MyStudySystem.exe'),'--no-browser','--data',str(upgrade/'data')],timeout=15)
    assert p.returncode==1 and (upgrade/'data/study.sqlite').read_bytes()==before
    passed('real G0 app upgrade preserves text/page/date; old executable refuses schema 3 unchanged')
    # Retain unsupported or corrupt database bytes exactly; do not create an empty replacement.
    db=target/'data/study.sqlite'
    with sqlite3.connect(db) as c:c.execute('PRAGMA user_version=999')
    before=db.read_bytes()
    p=subprocess.run([str(target/'app/MyStudySystem.exe'),'--no-browser'],cwd=os.environ['TEMP'],timeout=15)
    assert p.returncode==1 and db.read_bytes()==before
    passed('future schema refused by real executable without modifying DB')
    blocked=base/'OneDrive'/'نمونه';extract(blocked)
    p=subprocess.run([str(blocked/'app/MyStudySystem.exe'),'--no-browser'],timeout=15)
    assert p.returncode==1 and not (blocked/'data/study.sqlite').exists()
    passed('unattended Sync path requires explicit choice before creating DB')
    client,origin,state,info=start(blocked,'--allow-sync');post(client,origin,state,'save',note);stop(client,origin,state)
    client,origin,state,info=start(blocked,'--allow-sync')
    assert next(n for n in state['notes'] if n['id']==note['id'])['body']==note['body']
    stop(client,origin,state)
    passed('explicit Sync path choice allows save and reopen in same folder')
    # Real Windows read-only attribute on an existing database yields a write error, not deletion.
    readonly=base/'آزمون فقط خواندنی';extract(readonly)
    client,origin,state,info=start(readonly);post(client,origin,state,'seed',{});stop(client,origin,state)
    rdb=readonly/'data/study.sqlite';before=rdb.read_bytes();rdb.chmod(0o444)
    try:
        client,origin,state,info=start(readonly)
        try:post(client,origin,state,'save',note);raise AssertionError('read-only DB write accepted')
        except urllib.error.HTTPError as e:assert e.code==500
        stop(client,origin,state);assert rdb.read_bytes()==before
        passed('Windows read-only DB: write rejected and original bytes unchanged')
    finally:rdb.chmod(0o666)
except Exception as e:
    results.append({'name':str(e),'status':'fail'});raise
finally:
    if process and process.poll() is None:process.terminate()
    (ROOT/'docs/evidence/m1a/package-lifecycle-r3.json').write_text(json.dumps({'results':results,'test_directory':str(base)},ensure_ascii=False,indent=2),encoding='utf-8')
    print(f"RESULT {sum(r['status']=='pass' for r in results)} pass; {sum(r['status']=='fail' for r in results)} fail")
