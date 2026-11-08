"""Daily work, settings and search. All writes use the existing operation ledger."""
import hashlib
import json
import uuid
from datetime import date,datetime,timedelta,timezone
from store import Problem,normalized,now,text_field

DEFAULT=dict(cap=20,boundary=180,zone='local',digits='fa',week=6,display='persian',font='Vazirmatn',size=100,contrast=False,autosave=True,minutes=5,cues=True,feedback=True,initial_folder='')
OPTIONS=dict(zone=('local','Asia/Tehran','UTC'),digits=('fa','latn'),week=(6,0,1),display=('persian','gregory'),font=('Vazirmatn','Tahoma'))
def install(c):
    stmts=[
        'CREATE TABLE daily_config(id INTEGER PRIMARY KEY CHECK(id=1),rev INTEGER NOT NULL,settings TEXT NOT NULL,policy INTEGER NOT NULL)',
        'CREATE TABLE policies(id INTEGER PRIMARY KEY,intervals TEXT NOT NULL,repeat_last INTEGER NOT NULL,created TEXT NOT NULL)',
        'CREATE TABLE target_policy(target TEXT PRIMARY KEY,policy INTEGER NOT NULL REFERENCES policies(id))',
        'CREATE TABLE actions(id TEXT PRIMARY KEY,note TEXT NOT NULL REFERENCES notes(id),description TEXT NOT NULL,due TEXT NOT NULL,status TEXT NOT NULL,result TEXT NOT NULL,completed TEXT NOT NULL,rev INTEGER NOT NULL)',
        'CREATE TABLE activities(id TEXT PRIMARY KEY,target TEXT NOT NULL,stamp TEXT NOT NULL,minutes INTEGER,rating INTEGER,kind TEXT NOT NULL)',
        'CREATE TABLE section_direction(section TEXT PRIMARY KEY REFERENCES note_sections(id),direction TEXT NOT NULL)',
        'ALTER TABLE review_events ADD COLUMN policy_id INTEGER',
    ]
    for sql in stmts:c.execute(sql)
    c.execute('INSERT INTO policies VALUES(1,?,0,?)',(json.dumps([1,3,7,14,30,60]),now()))
    c.execute('INSERT INTO daily_config VALUES(1,0,?,1)',(json.dumps(DEFAULT),))
    c.execute('INSERT INTO target_policy SELECT target,1 FROM schedules')
    c.execute('UPDATE review_events SET policy_id=1')
    c.execute('PRAGMA user_version=6')

def config(c):
    r=c.execute('SELECT * FROM daily_config').fetchone()
    return {**DEFAULT,**json.loads(r['settings']),'rev':r['rev'],'policy_id':r['policy']}
def policy(c,target=None):
    r=c.execute('SELECT p.* FROM policies p JOIN target_policy t ON t.policy=p.id WHERE t.target=?',(target,)).fetchone() if target else None
    if not r:r=c.execute('SELECT p.* FROM policies p JOIN daily_config d ON p.id=d.policy').fetchone()
    return dict(id=r['id'],intervals=json.loads(r['intervals']),repeat_last=bool(r['repeat_last']))
def clock_day(c):
    from review import day
    cfg=config(c)
    if cfg['zone']=='local' and cfg['boundary']==180:return day()
    clock=datetime.now(timezone.utc)
    local=clock.astimezone() if cfg['zone']=='local' else clock.astimezone(timezone(timedelta(minutes=210)) if cfg['zone']=='Asia/Tehran' else timezone.utc)
    return (local.date()-timedelta(days=int(local.hour*60+local.minute<cfg['boundary']))).isoformat()

def snapshot(c):
    return dict(config=config(c),policy=policy(c),completed_today=[dict(r) for r in c.execute("SELECT target,day FROM attempts WHERE day=? AND status='completed'",(clock_day(c),))],actions=[dict(r) for r in c.execute('SELECT a.* FROM actions a JOIN notes n ON n.id=a.note WHERE n.status=\'active\' ORDER BY due,id')],activities=[dict(r) for r in c.execute('SELECT * FROM activities ORDER BY stamp DESC,rowid DESC')],directions={r[0]:r[1] for r in c.execute('SELECT section,direction FROM section_direction')})

def validate_date(d):
    if d:
        try:
            if date.fromisoformat(d).isoformat()!=d:raise ValueError()
        except (ValueError,TypeError):raise Problem('تاریخ معتبر انتخاب کنید.')
    return d

def policy_plan(c,q):
    values=q.get('intervals')
    if not isinstance(values,list) or not 1<=len(values)<=32 or any(type(v)!=int or not 1<=v<=3650 for v in values) or sorted(set(values))!=values:raise Problem('فاصله‌ها باید مثبت، صعودی و بدون تکرار باشند.')
    scope=q.get('scope')
    if scope not in ('new','active') or type(q.get('repeat_last'))!=bool:raise Problem('دامنهٔ تغییر سیاست را انتخاب کنید.')
    rows=[dict(r) for r in c.execute("SELECT target,rev,step,due FROM schedules WHERE status IN ('active','paused') ORDER BY target")] if scope=='active' else []
    previous=config(c)
    payload=[previous['rev'],values,scope,q['repeat_last'],rows]
    return dict(token=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest(),affected=len(rows),clamped=sum(r['step']>len(values) for r in rows),rows=rows)
def batch_plan(c,q):
    keys=q.get('targets')
    if not isinstance(keys,list) or not 1<=len(keys)<=500 or any(not isinstance(k,str) for k in keys) or len(set(keys))!=len(keys):raise Problem('بین یک تا ۵۰۰ هدف متفاوت انتخاب کنید.')
    due=validate_date(q.get('due',''));today=clock_day(c)
    if not due or due<today:raise Problem('موعد امروز یا آینده لازم است.')
    targets=[]
    for k in keys:
        kind,_,ident=k.partition(':')
        if kind not in ('note','highlight'):raise Problem('نوع هدف معتبر نیست.')
        if not c.execute("SELECT 1 FROM notes WHERE id=? AND status='active'" if kind=='note' else 'SELECT 1 FROM highlights WHERE id=?',(ident,)).fetchone():raise Problem('مطلب انتخابی در دسترس نیست.')
        s=c.execute('SELECT status,rev FROM schedules WHERE target=?',(k,)).fetchone()
        if s and s[0] not in ('ended','cancelled'):raise Problem('یکی از مطالب قبلاً برنامه‌ریزی شده است.',409)
        targets.append((k,s[1] if s else 0))
    already=c.execute("SELECT count(*) FROM schedules WHERE status='active' AND due=?",(due,)).fetchone()[0]
    digest=hashlib.sha256(json.dumps([targets,due,today,already,config(c)['rev']]).encode()).hexdigest()
    return dict(token=digest,already=already,total=already+len(keys),cap=config(c)['cap'],targets=targets,today=today)

def command(store,q):
    op=q.get('command')
    if op=='batch-preview':
        with store.connect() as c:return {k:v for k,v in batch_plan(c,q).items() if k!='targets'}
    if op=='preview':
        with store.connect() as c:
            p=policy_plan(c,q);return {k:v for k,v in p.items() if k!='rows'}
    if op=='health':
        with store.connect() as c:return dict(healthy=c.execute('PRAGMA quick_check').fetchone()[0]=='ok',schema=c.execute('PRAGMA user_version').fetchone()[0])
    def write(c):
        cfg=config(c)
        if op in ('settings','policy') and q.get('revision')!=cfg['rev']:raise Problem('تنظیمات تغییر کرده است. دوباره باز کنید.',409)
        if op=='settings':
            d=q.get('values')
            if not isinstance(d,dict) or set(d)-DEFAULT.keys():raise Problem('تنظیمات معتبر نیست.')
            settings={k:d.get(k,cfg[k]) for k in DEFAULT}
            for k,allowed in OPTIONS.items():
                if settings[k] not in allowed:raise Problem('گزینهٔ نامعتبر: '+k)
            for k,a,b in [('cap',1,500),('minutes',1,120),('boundary',0,1439),('size',85,150)]:
                if type(settings[k])!=int or not a<=settings[k]<=b:raise Problem('عدد تنظیمات بیرون از بازه است: '+k)
            for k in ('contrast','autosave','cues','feedback'):
                if type(settings[k])!=bool:raise Problem('ترجیح نامعتبر است.')
            folder=settings['initial_folder']
            if folder and not c.execute('SELECT 1 FROM folders WHERE id=? AND archived=0',(folder,)).fetchone():raise Problem('پوشهٔ اولیه در دسترس نیست.')
            c.execute('UPDATE daily_config SET settings=?,rev=rev+1',(json.dumps(settings),))
        elif op=='policy':
            p=policy_plan(c,q)
            if p['token']!=q.get('token'):raise Problem('وضعیت پیش‌نمایش تغییر کرده است؛ دوباره بررسی کنید.',409)
            pid=c.execute('INSERT INTO policies(intervals,repeat_last,created) VALUES(?,?,?)',(json.dumps(q['intervals']),int(q['repeat_last']),now())).lastrowid
            c.execute('UPDATE daily_config SET policy=?,rev=rev+1',(pid,))
            for row in p['rows']:
                t=row['target'];old=dict(c.execute('SELECT * FROM schedules WHERE target=?',(t,)).fetchone())
                c.execute('UPDATE schedules SET step=min(step,?),repeat_last=?,rev=rev+1 WHERE target=?',(len(q['intervals']),int(q['repeat_last']),t))
                c.execute('INSERT OR REPLACE INTO target_policy VALUES(?,?)',(t,pid))
                new=dict(c.execute('SELECT * FROM schedules WHERE target=?',(t,)).fetchone())
                c.execute("INSERT INTO review_events(target,command,old_state,new_state,attempt,day,policy_id) VALUES(?,'policy',?,?,'',?,?)",(t,json.dumps(old),json.dumps(new),clock_day(c),pid))
        elif op=='batch':
            from review import command as enroll
            p=batch_plan(c,q)
            if p['token']!=q.get('token'):raise Problem('بار مرور یا برنامه‌ها تغییر کرده‌اند؛ دوباره بررسی کنید.',409)
            for key,rev in p['targets']:
                enroll(store,dict(target=key,command='enroll',revision=rev,due=q['due'],confirm_today=q.get('confirm_today') is True),enroll_connection=c)
        elif op=='action':
            ident=text_field(q,'id',100,True);note=text_field(q,'note',100,True)
            if not c.execute("SELECT 1 FROM notes WHERE id=? AND status='active'",(note,)).fetchone():raise Problem('یادداشت فعال انتخاب کنید.')
            old=c.execute('SELECT * FROM actions WHERE id=?',(ident,)).fetchone()
            store.expected(q,old['rev'] if old else 0)
            if old and old['note']!=note:raise Problem('یادداشت مبدأ قابل تغییر نیست.')
            status=q.get('status','open')
            if status not in ('open','done','cancelled'):raise Problem('وضعیت اقدام معتبر نیست.')
            completed=(old['completed'] if old and old['completed'] else now()) if status=='done' else ''
            c.execute('INSERT OR REPLACE INTO actions VALUES(?,?,?,?,?,?,?,?)',(ident,note,text_field(q,'description',1000,True),validate_date(q.get('due','')),status,text_field(q,'result',2000),completed,q['revision']+1))
        elif op=='activity':
            from catalog import target
            key=q.get('target','');kind,_=target(c,key)
            if kind not in ('note','source'):raise Problem('یک یادداشت یا منبع انتخاب کنید.')
            minutes=q.get('minutes');rating=q.get('rating')
            if minutes is not None and (type(minutes)!=int or not 1<=minutes<=1440):raise Problem('دقایق مطالعه معتبر نیست.')
            if rating is not None and (type(rating)!=int or not 1<=rating<=5):raise Problem('احساس مفید بودن از ۱ تا ۵ است.')
            c.execute('INSERT INTO activities VALUES(?,?,?,?,?,?)',(str(uuid.uuid4()),key,now(),minutes,rating,'logged' if q.get('logged') or minutes or rating else 'opened'))
        else:raise Problem('فرمان نامعتبر است.')
        return dict(ok=True)
    return store.transaction(q,'daily',write)

def search(store,filters):
    """Match normalized terms but build snippets exclusively from unmodified text."""
    from collections import defaultdict
    from functools import lru_cache
    norm=lru_cache(maxsize=8192)(normalized)
    needle=norm(filters.get('q','').strip())[:500];terms=needle.split()
    if not terms and not any(filters.get(k) for k in ('kind','type','topic','tag','review','from','to')):return []
    with store.connect() as c:
        c.execute('BEGIN')
        topics={r['id']:r['label'] for r in c.execute("SELECT id,label FROM topics WHERE status='active'")}
        sources={r['id']:dict(r) for r in c.execute("SELECT s.id,s.title,s.body,d.type FROM sources s JOIN source_details d ON d.source_id=s.id WHERE d.status='active'")}
        notes={r['id']:dict(id=r['id'],title=r['title'],sections={},body='') for r in c.execute("SELECT id,title FROM notes WHERE status='active'")}
        for r in c.execute('SELECT note_id,kind,content_text FROM note_sections'):
            if r['note_id'] in notes:
                n=notes[r['note_id']];n['sections'][r['kind']]=r['content_text']
                if r['kind']=='body':n['body']=r['content_text']
        highlights=[dict(r) for r in c.execute('SELECT * FROM highlights')]
        schedules={r['target']:dict(r) for r in c.execute('SELECT target,status,due FROM schedules')}
        membership=defaultdict(set);taglist=defaultdict(list);links=defaultdict(set)
        for t,v in c.execute('SELECT target,topic FROM membership'):membership[t].add(v)
        for t,v in c.execute('SELECT target,label FROM tags'):taglist[t].append(v)
        for t,v in c.execute('SELECT target,source FROM citations'):links[t].add(v)
        for t,v in c.execute('SELECT note_id,source_id FROM note_sources'):links['note:'+t].add(v)
        for hid,origin in c.execute('SELECT highlight,origin FROM anchors'):links['highlight:'+hid].update(links[origin])
    results=[]
    for k,rows in [('topics',[dict(id=t,label=v) for t,v in topics.items()]),('notes',notes.values()),('sources',sources.values()),('highlights',highlights)]:
        if filters.get('kind') and filters['kind']!=k:continue
        for obj in rows:
            ident=obj['id'];key={'notes':'note','topics':'topic','sources':'source','highlights':'highlight'}[k]+':'+ident
            title=obj.get('title') or obj.get('label','')
            ts=membership[key]
            if k=='topics':ts.add(ident)
            tags=taglist[key]
            refs=links[key];refs.add(obj.get('source_id') or obj.get('source') or (ident if k=='sources' else ''))
            if filters.get('topic') and filters['topic'] not in ts:continue
            if filters.get('type') and not any(sources.get(r,{}).get('type')==filters['type'] for r in refs):continue
            if filters.get('tag') and norm(filters['tag']) not in [norm(t) for t in tags]:continue
            rv=schedules.get(key,{})
            if filters.get('review') and filters['review']!=rv.get('status','none'):continue
            due=rv.get('due','')
            if filters.get('from') and due<filters['from'] or filters.get('to') and (not due or due>filters['to']):continue
            texts=[title,*dict.fromkeys([obj.get('body',''),*obj.get('sections',{}).values()]),*tags,*[topics[t] for t in ts if t in topics],*[sources[r]['title'] for r in refs if r in sources]]
            texts=[t for t in texts if t];ns=[norm(t) for t in texts]
            if not all(any(term in n for n in ns) for term in terms):continue
            score=sum(10 if term in norm(title) else 6 if k=='highlights' and term in norm(obj['body']) else 2 for term in terms)
            best=next((t for t in texts if t!=title and any(x in norm(t) for x in terms)),obj.get('body') or title)
            pos=best.casefold().find(needle.casefold()) if needle else -1
            # Mapping normalization across ligatures or combining marks is ambiguous: use a safe plain-text fallback.
            start=max(0,pos-45) if pos>=0 else 0
            if pos<0 and terms and len(best)>180:
                start=next((i for i in range(0,len(best),100) if any(t in norm(best[i:i+180]) for t in terms)),0)
            results.append(dict(id=ident,kind=k,title=title or 'گزیده',body=best[start:start+180],score=score,due=due))
    return sorted(results,key=lambda r:(-r['score'],norm(r['title']),r['id']))[:200]
