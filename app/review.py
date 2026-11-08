"""Transactional review commands and a single learning-day clock for M1-b."""
from datetime import datetime, timedelta, date, timezone
import json
import uuid
from store import Problem

INTERVALS = (1, 3, 7, 14, 30, 60)
CAP = 20

def day(local=None):
    local = local or datetime.now().astimezone()
    return (local.date() - timedelta(days=int(local.hour < 3))).isoformat()

def plus(today, days):
    return (date.fromisoformat(today) + timedelta(days=days)).isoformat()

def install(c):
    c.execute("CREATE TABLE schedules(target TEXT PRIMARY KEY,step INTEGER NOT NULL,due TEXT NOT NULL,status TEXT NOT NULL,rev INTEGER NOT NULL,cue TEXT NOT NULL,repeat_last INTEGER NOT NULL DEFAULT 0)")
    c.execute("CREATE TABLE attempts(id TEXT PRIMARY KEY,target TEXT NOT NULL,status TEXT NOT NULL,answer TEXT NOT NULL,rev INTEGER NOT NULL,day TEXT NOT NULL,grade TEXT NOT NULL)")
    c.execute("CREATE UNIQUE INDEX one_draft ON attempts(target) WHERE status='draft'")
    c.execute("CREATE TABLE review_events(id INTEGER PRIMARY KEY,target TEXT NOT NULL,command TEXT NOT NULL,old_state TEXT,new_state TEXT NOT NULL,attempt TEXT,day TEXT NOT NULL)")
    c.execute("CREATE TABLE reflections(note_id TEXT PRIMARY KEY,target TEXT NOT NULL)")
    c.execute("PRAGMA user_version=4")

def proposals(step,today,repeat_last=False,intervals=INTERVALS):
    return {k:{'step':s,'due':plus(today,n) if n else ''} for k,s,n in (
        ('again',1,intervals[0]),('partial',step,intervals[0]),
        ('good',min(step+1,len(intervals)),intervals[step] if step<len(intervals) else (intervals[-1] if repeat_last else 0)))}

def summary(c,today):
    from daily import config,policy
    cap=config(c)["cap"]
    used=c.execute("SELECT count(*) FROM attempts WHERE day=? AND status='completed'",(today,)).fetchone()[0]
    rows=[]
    for s in c.execute("SELECT * FROM schedules ORDER BY due,target"):
        row=dict(s)
        row['turn']=1+c.execute("SELECT count(*) FROM attempts WHERE target=? AND status='completed'",(s['target'],)).fetchone()[0]
        event=c.execute('SELECT command FROM review_events WHERE target=? ORDER BY id DESC LIMIT 1',(s['target'],)).fetchone()
        row['undo']=bool(event and event[0]=='grade')
        intervals=policy(c,s['target'])['intervals'];row['stages']=len(intervals)
        row['choices']=proposals(s['step'],today,s['repeat_last'],intervals)
        rows.append(row)
    completed_today={r[0] for r in c.execute("SELECT DISTINCT target FROM attempts WHERE day=? AND status='completed'",(today,))}
    queue=[s['target'] for s in rows if s['status']=='active' and s['due']<=today and s['target'] not in completed_today]
    return dict(today=today,first=plus(today,policy(c)["intervals"][0]),used=used,cap=cap,rows=rows,queue=queue[:max(0,cap-used)],backlog=max(0,len(queue)-max(0,cap-used)))

def command(store,q,*,enroll_connection=None):
    key=q.get('target','')
    kind,sep,ident=key.partition(':')
    if kind not in ('note','highlight') or not sep or not ident:raise Problem('مطلب معتبر انتخاب کنید.')
    action=q.get('command')
    def apply(c):
        from daily import config,policy,clock_day
        today=clock_day(c);cfg=config(c);rule=policy(c,None if action=='enroll' else key)
        if q.get('expected_day',today)!=today:raise Problem('روز مطالعه عوض شده است. وضعیت و تاریخ را دوباره بررسی کنید.',409)
        content=c.execute("SELECT content_text FROM note_sections WHERE note_id=? AND kind='body'" if kind=='note' else 'SELECT body FROM highlights WHERE id=?',(ident,)).fetchone()
        if kind=='note' and action not in ('reveal',):
            header=c.execute('SELECT status FROM notes WHERE id=?',(ident,)).fetchone()
            if not header or header['status']!='active':raise Problem('یادداشت برای مرور فعال نیست.',409)
        if not content:raise Problem('مطلب پیدا نشد.',404)
        old=c.execute('SELECT * FROM schedules WHERE target=?',(key,)).fetchone()
        old=dict(old) if old else None
        rev=old['rev'] if old else 0
        if action=='reveal':
            history=[dict(r) for r in c.execute("SELECT answer,grade,status,day FROM attempts WHERE target=? AND status IN ('completed','undone') ORDER BY rowid DESC",(key,))]
            return dict(body=content[0],history=history)
        if q.get('revision')!=rev:raise Problem('برنامهٔ مرور در تب دیگری تغییر کرد. متن شما حفظ شده است؛ وضعیت تازه را ببینید.',409)
        def chosen(default):
            value=q.get('due',default)
            try: valid=date.fromisoformat(value).isoformat()==value
            except (TypeError,ValueError):valid=False
            if not valid or value<today or (value==today and not q.get('confirm_today')):raise Problem('تاریخ آینده را انتخاب کنید یا مرور دوبارهٔ امروز را تأیید کنید.')
            return value
        s=dict(old) if old else dict(target=key,step=1,due='',status='active',cue='',rev=0,repeat_last=0)
        aid=q.get('attempt','')
        if action=='enroll':
            if old and old['status'] not in ('ended','cancelled'):raise Problem('این مطلب برنامهٔ مرور دارد.',409)
            s.update(step=1,status='active',due=chosen(plus(today,rule['intervals'][0])),cue=str(q.get('cue',''))[:250],repeat_last=int(q.get('repeat_last',rule['repeat_last']) is True))
            c.execute('INSERT OR REPLACE INTO target_policy VALUES(?,?)',(key,rule['id']))
        elif not old:raise Problem('ابتدا مطلب را به مرور اضافه کنید.')
        elif action in ('start','draft','grade'):
            if s['status']!='active':raise Problem('برنامهٔ مرور فعال نیست.',409)
            draft=c.execute("SELECT * FROM attempts WHERE target=? AND status='draft'",(key,)).fetchone()
            if action=='start':
                if not draft:
                    aid=str(uuid.uuid4());c.execute("INSERT INTO attempts VALUES(?,?,'draft','',0,'','')",(aid,key))
                    return dict(id=aid,answer='',rev=0)
                return dict(id=draft['id'],answer=draft['answer'],rev=draft['rev'])
            if not draft or draft['id']!=aid or draft['rev']!=q.get('draft_revision'):raise Problem('پیش‌نویس در تب دیگر تغییر کرد؛ متن خود را نگه دارید.',409)
            answer=q.get('answer','')
            if not isinstance(answer,str) or len(answer)>100000:raise Problem('پاسخ بیش از حد بلند است.')
            if action=='draft':
                c.execute('UPDATE attempts SET answer=?,rev=rev+1 WHERE id=?',(answer,aid))
                return dict(rev=draft['rev']+1)
            if c.execute("SELECT count(*) FROM attempts WHERE day=? AND status='completed'",(today,)).fetchone()[0]>=cfg['cap']:raise Problem('سهمیهٔ مرور امروز کامل شده است.')
            grade=q.get('grade')
            if grade not in ('again','partial','good'):raise Problem('یکی از سه نتیجه را انتخاب کنید.')
            proposal=proposals(s['step'],today,s['repeat_last'],rule['intervals'])[grade]
            due=chosen(proposal['due']) if q.get('due',proposal['due']) else ''
            if not due and proposal['due']:raise Problem('موعد مرور لازم است.')
            s.update(step=proposal['step'],due=due,status='active' if due else 'ended')
            c.execute("UPDATE attempts SET status='completed',answer=?,grade=?,day=?,rev=rev+1 WHERE id=?",(answer,grade,today,aid))
        elif action=='undo':
            last=c.execute('SELECT * FROM review_events WHERE target=? ORDER BY id DESC LIMIT 1',(key,)).fetchone()
            if not last or last['command']!='grade':raise Problem('فقط آخرین نتیجهٔ بدون تغییر بعدی قابل برگشت است.',409)
            s=json.loads(last['old_state']);aid=last['attempt']
            c.execute("UPDATE attempts SET status='undone' WHERE id=?",(aid,))
        elif action=='pause' and s['status']=='active':s['status']='paused'
        elif action=='resume' and s['status']=='paused':s.update(status='active',due=chosen(max(today,s['due'])))
        elif action in ('snooze','reschedule') and s['status']=='active':s['due']=chosen(plus(today,1))
        elif action=='cancel' and s['status'] in ('active','paused'):s['status']='cancelled'
        elif action=='reflect':
            body=q.get('answer','')
            if not isinstance(body,str) or not body.strip() or len(body)>100000:raise Problem('متن برداشت را بنویسید.')
            nid=str(uuid.uuid4());stamp=datetime.now(timezone.utc).isoformat()
            c.execute("INSERT INTO notes VALUES(?,?,1,'','','active',?,?)",(nid,'برداشت از مرور',stamp,stamp))
            c.execute("INSERT INTO note_sections(id,note_id,kind,position,content_text,revision) VALUES(?,?,'body',0,?,1)",(str(uuid.uuid4()),nid,body))
            c.execute('INSERT INTO reflections VALUES(?,?)',(nid,key))
            ref=c.execute('SELECT source_id,locator FROM note_sources WHERE note_id=?' if kind=='note' else 'SELECT source,location FROM highlights WHERE id=?',(ident,)).fetchone()
            if ref and ref[0]:c.execute('INSERT INTO note_sources VALUES(?,?,?,?)',(str(uuid.uuid4()),nid,*ref))
            from catalog import copy_context
            copy_context(c,key,nid)
            return dict(id=nid)
        else:raise Problem('این عمل در وضعیت فعلی امکان ندارد.')
        s['rev']=rev+1
        c.execute('INSERT OR REPLACE INTO schedules VALUES(:target,:step,:due,:status,:rev,:cue,:repeat_last)',s)
        c.execute('INSERT INTO review_events(target,command,old_state,new_state,attempt,day,policy_id) VALUES(?,?,?,?,?,?,?)',(key,action,json.dumps(old),json.dumps(s),aid,today,rule["id"]))
        return dict(revision=s['rev'],due=s['due'])
    if enroll_connection is not None:
        if action!='enroll':raise ValueError('enrollment transaction only')
        return apply(enroll_connection)
    if action=='reveal':
        with store.connect() as c:return apply(c)
    return store.transaction(q,'review',apply)
