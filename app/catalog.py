"""Non-audio library, logical topics and physical folder bindings."""
import hashlib
import json
import os
import re
import stat
import subprocess
import uuid
from datetime import date
from pathlib import Path, PureWindowsPath
from store import Problem, normalized, now, text_field

KINDS = ('book','website','article','pdf','video','course','conversation','personal_experience','other')
QUEUE = ('پیشنهادی','بعداً','در حال مطالعه','تکمیل','کنارگذاشته')
EXT = {'.pdf':'application/pdf','.txt':'text/plain; charset=utf-8','.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.mp4':'video/mp4','.webm':'video/webm'}
def uid(): return str(uuid.uuid4())
def install(c):
    statements=[
      "CREATE TABLE library_config(id INTEGER PRIMARY KEY CHECK(id=1),root TEXT NOT NULL,rev INTEGER NOT NULL)",
      "INSERT INTO library_config VALUES(1,'',0)",
      "CREATE TABLE folders(id TEXT PRIMARY KEY,parent TEXT NOT NULL,name TEXT NOT NULL,rel TEXT COLLATE NOCASE UNIQUE NOT NULL,identity TEXT NOT NULL,archived INTEGER NOT NULL DEFAULT 0)",
      "CREATE TABLE file_refs(id TEXT PRIMARY KEY,rel TEXT NOT NULL COLLATE NOCASE UNIQUE)",
      "CREATE TABLE folder_intent(id INTEGER PRIMARY KEY CHECK(id=1),payload TEXT NOT NULL)",
      "CREATE TABLE topics(id TEXT PRIMARY KEY,parent TEXT NOT NULL,label TEXT NOT NULL,norm TEXT NOT NULL,status TEXT NOT NULL,UNIQUE(parent,norm))",
      "CREATE TABLE membership(target TEXT NOT NULL,topic TEXT NOT NULL REFERENCES topics(id),PRIMARY KEY(target,topic))",
      "CREATE TABLE tags(target TEXT NOT NULL,label TEXT NOT NULL,norm TEXT NOT NULL,PRIMARY KEY(target,norm))",
      "CREATE TABLE placements(target TEXT PRIMARY KEY,folder TEXT NOT NULL REFERENCES folders(id))",
      "CREATE TABLE citations(id TEXT PRIMARY KEY,target TEXT NOT NULL,source TEXT NOT NULL REFERENCES sources(id),locator TEXT NOT NULL)",
      "CREATE TABLE attached(target TEXT NOT NULL,file TEXT NOT NULL REFERENCES file_refs(id),PRIMARY KEY(target,file))",
      "CREATE TABLE source_meta(source TEXT PRIMARY KEY,url TEXT NOT NULL,site TEXT NOT NULL,accessed TEXT NOT NULL)",
      "CREATE TABLE reading_queue(source TEXT PRIMARY KEY REFERENCES sources(id),status TEXT NOT NULL,reason TEXT NOT NULL,priority INTEGER NOT NULL,planned TEXT NOT NULL)",
      "CREATE TABLE anchors(highlight TEXT PRIMARY KEY,origin TEXT NOT NULL,revision INTEGER NOT NULL,stamp TEXT NOT NULL,section_id TEXT NOT NULL,context_before TEXT NOT NULL,context_after TEXT NOT NULL,offset INTEGER)",
      "PRAGMA user_version=5"]
    for sql in statements:c.execute(sql)

def config(c):return c.execute('SELECT * FROM library_config').fetchone()
def bump(c):c.execute('UPDATE library_config SET rev=rev+1')
def one(c,table,ident):
    if table not in ('topics','folders','sources','file_refs','notes','highlights'):raise ValueError(table)
    r=c.execute(f'SELECT * FROM {table} WHERE id=?',(ident,)).fetchone()
    if not r:raise Problem('مورد انتخابی پیدا نشد.',404)
    return r
def target(c,key):
    k,_,i=key.partition(':')
    if k not in ('note','highlight','source'):raise Problem('نوع مطلب نامعتبر است.')
    one(c,{'note':'notes','source':'sources','highlight':'highlights'}[k],i)
    return k,i
def label(value):
    if not isinstance(value,str) or not value.strip() or len(value)>180:raise Problem('نام را بنویسید (حداکثر ۱۸۰ نویسه).')
    return value.strip()
def fragment(value):
    s=label(value)
    if s!=value or s.endswith('.') or s in ('.','..') or re.search(r'[<>:"/\\|?*\x00-\x1f]',s) or os.path.isreserved(s):
        raise Problem('این نام در مسیر ویندوز مجاز نیست.')
    return s
def clean_rel(value):
    if not isinstance(value,str):raise Problem('مسیر نسبی لازم است.')
    parts=value.replace('\\','/').split('/')
    return '/'.join(fragment(p) for p in parts)
def safe_root(raw,store):
    p=Path(raw)
    if not p.is_absolute() or not p.is_dir() or str(p).startswith('\\\\') or p==Path(p.anchor):raise Problem('یک پوشهٔ محلی موجود را به عنوان ریشه انتخاب کنید.')
    for x in [p,*p.parents]:
        if x.is_symlink() or x.is_junction():raise Problem('مسیر پیوندی یا junction مجاز نیست.')
    p=p.resolve()
    for protected in (store.data.resolve(),Path(__file__).resolve().parent):
        if p.is_relative_to(protected) or protected.is_relative_to(p):raise Problem('پوشهٔ فایل‌ها باید جدا از app و data باشد.')
    return p
def resolve(store,root,rel):
    if not root:raise Problem('ابتدا پوشهٔ مادر فایل‌ها را مشخص کنید.')
    base=safe_root(root,store)
    rel=clean_rel(rel)
    p=base
    for part in rel.split('/'):
        p=p/part
        if p.is_symlink() or p.is_junction() or (p.exists() and p.stat(follow_symlinks=False).st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT):raise Problem('مسیر پیوندی یا junction مجاز نیست.')
    if not p.resolve().is_relative_to(base) or len(str(p))>248:raise Problem('مسیر خارج از ریشه یا بیش از حد بلند است.')
    return p
def identity(p):
    st=p.stat();return str(st.st_dev)+':'+str(st.st_ino)
def under(rel,prefix):
    return rel.casefold()==prefix.casefold() or rel.casefold().startswith(prefix.casefold()+'/')
def rows(c,table):return [dict(x) for x in c.execute('SELECT * FROM '+table)]
def snapshot(store,c):
    out={t:rows(c,t) for t in ('folders','topics','membership','tags','placements','citations','attached','source_meta','reading_queue','anchors','file_refs','reflections')}
    cfg=config(c);out.update(root=cfg['root'],rev=cfg['rev'],pending=bool(c.execute('SELECT 1 FROM folder_intent').fetchone()))
    for f in out['file_refs']:
        try:f['available']=resolve(store,cfg['root'],f['rel']).is_file()
        except (OSError,Problem):f['available']=False
    return out
def require_rev(c,q):
    if q.get('revision')!=config(c)['rev']:raise Problem('فهرست در تب دیگر تغییر کرده است. تازه‌سازی کنید.',409)
def ensure_idle(c):
    if c.execute('SELECT 1 FROM folder_intent').fetchone():raise Problem('ابتدا وضعیت جابه‌جایی ناتمام را بررسی کنید.',409)
def named_parent(c,table,parent,ident):
    visited={ident}
    while parent:
        if parent in visited:raise Problem('انتقال به خود یا زیرشاخهٔ خود ممکن نیست.')
        visited.add(parent);parent=one(c,table,parent)['parent']

def plan(store,c,q):
    cfg=config(c);op=q['action'];parent=q.get('parent','')
    if op=='root':
        dest=str(safe_root(q.get('path',''),store))
        return dict(action=op,old=cfg['root'],new=dest,count=c.execute('SELECT count(*) FROM file_refs').fetchone()[0],rev=cfg['rev'])
    f=one(c,'folders',q.get('id'));named_parent(c,'folders',parent,f['id'])
    prefix=one(c,'folders',parent)['rel']+'/' if parent else ''
    name=fragment(q.get('name',''));new=prefix+name
    if under(new,f['rel']):raise Problem('مقصد باید بیرون از پوشهٔ قبلی باشد.')
    a=resolve(store,cfg['root'],f['rel']);b=resolve(store,cfg['root'],new)
    if c.execute('SELECT 1 FROM folders WHERE rel=?',(new,)).fetchone():raise Problem('مقصد قبلاً ثبت شده است.')
    if op=='move':
        if not a.is_dir() or identity(a)!=f['identity'] or b.exists() or not b.parent.is_dir():raise Problem('مبدأ یا مقصد تغییر کرده یا مقصد اشغال است.')
    elif op=='relink':
        if a.exists() or not b.is_dir() or identity(b)!=f['identity']:raise Problem('پوشهٔ قبلی باید جابه‌جا شده و هویت مقصد یکسان باشد.')
    else:raise Problem('فرمان ناشناخته.')
    refs=[r for r in rows(c,'file_refs') if under(r['rel'],f['rel'])]
    for r in refs:
        targetrel=new+r['rel'][len(f['rel']):]
        resolve(store,cfg['root'],targetrel)
        if c.execute('SELECT 1 FROM file_refs WHERE rel=? AND id<>?',(targetrel,r['id'])).fetchone():raise Problem('ارجاع مقصد از قبل وجود دارد.')
    return dict(action=op,id=f['id'],parent=parent,name=name,root=cfg['root'],old=f['rel'],new=new,identity=f['identity'],count=len(refs),rev=cfg['rev'])
def apply_paths(c,p):
    for table in ('folders','file_refs'):
        for r in rows(c,table):
            if under(r['rel'],p['old']):
                c.execute(f'UPDATE {table} SET rel=? WHERE id=?',(p['new']+r['rel'][len(p['old']):],r['id']))
    c.execute('UPDATE folders SET name=?,parent=? WHERE id=?',(p['name'],p['parent'],p['id']))
    bump(c)
def recover(store):
    with store.connect() as c:
        item=c.execute('SELECT payload FROM folder_intent').fetchone()
        if not item:return 'idle'
        p=json.loads(item[0])
        try:
            a=resolve(store,p['root'],p['old']);b=resolve(store,p['root'],p['new'])
            if not a.exists() and b.is_dir() and identity(b)==p['identity']:
                apply_paths(c,p);result='completed'
            elif not b.exists() and a.is_dir() and identity(a)==p['identity']:result='cancelled'
            else:return 'ambiguous'
        except (OSError,Problem):return 'ambiguous'
        c.execute('DELETE FROM folder_intent');return result

def command(store,q):
    op=q.get('action')
    if op=='recover':return dict(result=recover(store))
    if op=='browse':
        with store.connect() as c:
            root=config(c)['root'];rel=q.get('path','')
            base=resolve(store,root,rel) if rel else safe_root(root,store)
            result=[]
            for p in sorted(base.iterdir(),key=lambda x:(not x.is_dir(),x.name.casefold())):
                if p.is_symlink() or p.is_junction() or p.stat(follow_symlinks=False).st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:continue
                if p.is_dir() or p.suffix.lower() in EXT:result.append(dict(name=p.name,folder=p.is_dir()))
                if len(result)>=500:break
            return dict(entries=result)
    if op=='explorer':
        with store.connect() as c:
            ref=one(c,'file_refs',q.get('id'));p=resolve(store,config(c)['root'],ref['rel'])
            if not p.is_file():raise Problem('فایل در مسیر ثبت‌شده یافت نشد.')
            subprocess.Popen([str(Path(os.environ['WINDIR'])/'explorer.exe'),'/select,'+str(p)])
        return dict(ok=True)
    if op in ('root','move','relink'):
        with store.connect() as c:
            ensure_idle(c);require_rev(c,q);p=plan(store,c,q)
            token=hashlib.sha256(json.dumps(p,sort_keys=True).encode()).hexdigest()
            if not q.get('confirm'):return dict(plan=p,token=token)
            if q['confirm']!=token:raise Problem('پیش‌نمایش تغییر کرده است.',409)
            if op=='root':
                c.execute('UPDATE library_config SET root=?,rev=rev+1',(p['new'],))
                for f in rows(c,'folders'):
                    loc=resolve(store,p['new'],f['rel'])
                    if loc.is_dir():c.execute('UPDATE folders SET identity=? WHERE id=?',(identity(loc),f['id']))
                return dict(ok=True)
            if op=='relink':apply_paths(c,p);return dict(ok=True)
            c.execute('INSERT INTO folder_intent VALUES(1,?)',(json.dumps(p),))
        try:resolve(store,p['root'],p['old']).rename(resolve(store,p['root'],p['new']))
        except OSError:recover(store);raise Problem('انتقال در ویندوز انجام نشد. دسترسی و آزادبودن مقصد را بررسی کنید.')
        if recover(store)!='completed':raise Problem('وضعیت انتقال نیازمند بررسی است.',409)
        return dict(ok=True)
    def apply(c):
        require_rev(c,q);ensure_idle(c);key=q.get('target','')
        if op=='folder':
            parent=q.get('parent','');name=fragment(q.get('name',''))
            rel=(one(c,'folders',parent)['rel']+'/' if parent else '')+name
            p=resolve(store,config(c)['root'],rel)
            if c.execute('SELECT 1 FROM folders WHERE rel=?',(rel,)).fetchone():raise Problem('پوشه قبلاً ثبت شده است.')
            p.mkdir(exist_ok=True);c.execute('INSERT INTO folders VALUES(?,?,?,?,?,0)',(uid(),parent,name,rel,identity(p)))
        elif op=='folder-archive':c.execute('UPDATE folders SET archived=1 WHERE id=?',(one(c,'folders',q['id'])['id'],))
        elif op=='topic':
            ident=q.get('id') or uid();parent=q.get('parent','');name=label(q.get('name'))
            named_parent(c,'topics',parent,ident)
            if c.execute('SELECT 1 FROM topics WHERE parent=? AND norm=? AND id<>?',(parent,normalized(name),ident)).fetchone():raise Problem('موضوع هم‌نام وجود دارد.')
            c.execute("INSERT INTO topics VALUES(?,?,?,?,'active') ON CONFLICT(id) DO UPDATE SET label=excluded.label,parent=excluded.parent,norm=excluded.norm",(ident,parent,name,normalized(name)))
        elif op=='topic-delete':c.execute("UPDATE topics SET status='deleted' WHERE id=?",(one(c,'topics',q['id'])['id'],))
        elif op in ('topic-link','tag','citation','place','file'):
            k,i=target(c,key)
            if op=='topic-link':
                one(c,'topics',q['id']);c.execute('INSERT OR IGNORE INTO membership VALUES(?,?)',(key,q['id']))
            elif op=='tag':
                name=label(q['name']);c.execute('INSERT OR IGNORE INTO tags VALUES(?,?,?)',(key,name,normalized(name)))
            elif op=='citation':
                one(c,'sources',q['id']);c.execute('INSERT INTO citations VALUES(?,?,?,?)',(uid(),key,q['id'],text_field(q,'locator',500)))
            elif op=='place':
                c.execute('DELETE FROM placements WHERE target=?',(key,))
                if q.get('id'):one(c,'folders',q['id']);c.execute('INSERT INTO placements VALUES(?,?)',(key,q['id']))
            else:
                rel=clean_rel(q['path']);f=resolve(store,config(c)['root'],rel)
                if f.suffix.lower() not in EXT or not f.is_file():raise Problem('فایل غیرصوتی موجود و پشتیبانی‌شده انتخاب کنید.')
                c.execute('INSERT OR IGNORE INTO file_refs VALUES(?,?)',(uid(),rel));fid=c.execute('SELECT id FROM file_refs WHERE rel=?',(rel,)).fetchone()[0]
                c.execute('INSERT OR IGNORE INTO attached VALUES(?,?)',(key,fid))
        elif op=='unlink':
            table,col={'topic':('membership','topic'),'tag':('tags','norm'),'file':('attached','file'),'citation':('citations','id')}[q['kind']]
            c.execute(f'DELETE FROM {table} WHERE target=? AND {col}=?',(key,q['id']))
        elif op=='queue':
            one(c,'sources',q['id']);status=q['status'];priority=q['priority'];planned=q.get('planned','')
            if status not in QUEUE or type(priority)!=int or not 1<=priority<=5:raise Problem('اولویت یا وضعیت نامعتبر است.')
            if planned:date.fromisoformat(planned)
            c.execute('INSERT OR REPLACE INTO reading_queue VALUES(?,?,?,?,?)',(q['id'],status,text_field(q,'reason',2000),priority,planned))
        elif op=='summary':
            topic=one(c,'topics',q.get('id'))
            if topic['status']!='active':raise Problem('موضوع فعال انتخاب کنید.')
            title=text_field(q,'title',250,True);body=text_field(q,'body',200000,True)
            nid=uid();stamp=now()
            c.execute("INSERT INTO notes VALUES(?,?,1,'','','active',?,?)",(nid,title,stamp,stamp))
            c.execute("INSERT INTO note_sections(id,note_id,kind,position,content_text,revision) VALUES(?,?,'body',0,?,1)",(uid(),nid,body))
            c.execute('INSERT INTO membership VALUES(?,?)',('note:'+nid,topic['id']))
            for src in dict.fromkeys(q.get('sources',[])):
                one(c,'sources',src);c.execute('INSERT INTO citations VALUES(?,?,?,?)',(uid(),'note:'+nid,src,''))
        elif op=='excerpt':
            k,i=target(c,key);excerpt=text_field(q,'body',20000,True);location=text_field(q,'locator',500)
            if k=='source':r=c.execute('SELECT s.body,d.content_revision FROM sources s JOIN source_details d ON d.source_id=s.id WHERE s.id=?',(i,)).fetchone()
            elif k=='note':r=c.execute("SELECT content_text,revision FROM note_sections WHERE note_id=? AND kind='body'",(i,)).fetchone()
            else:raise Problem('مبدأ گزیده باید منبع یا یادداشت باشد.')
            if not q.get('manual') and (excerpt not in r[0] or q.get('content_revision')!=r[1]):raise Problem('متن مبدأ تغییر کرده است؛ دوباره انتخاب کنید.',409)
            hid=uid();c.execute('INSERT INTO highlights VALUES(?,?,?,?)',(hid,excerpt,i if k=='source' else '',location))
            offset=q.get('offset')
            if type(offset) is not int or offset<0 or r[0][offset:offset+len(excerpt)]!=excerpt:
                offset=r[0].find(excerpt) if r[0].count(excerpt)==1 else None
            if q.get('manual'):offset=None
            before=r[0][max(0,offset-48):offset] if offset is not None else ''
            after=r[0][offset+len(excerpt):offset+len(excerpt)+48] if offset is not None else ''
            section=c.execute("SELECT id FROM note_sections WHERE kind='body' AND note_id=?",(i,)).fetchone() if k=='note' else None
            c.execute('INSERT INTO anchors VALUES(?,?,?,?,?,?,?,?)',(hid,key,0 if q.get('manual') else r[1],now(),section[0] if section else '',before,after,offset))
        elif op=='note-status':
            k,i=target(c,key);status=q['status']
            if k!='note' or status not in ('archived','deleted'):raise Problem('وضعیت نامعتبر است.')
            c.execute('UPDATE notes SET status=?,revision=revision+1 WHERE id=?',(status,i));c.execute("UPDATE schedules SET status='paused',rev=rev+1 WHERE target=? AND status='active'",(key,))
        else:raise Problem('فرمان نامعتبر است.')
        bump(c);return dict(ok=True)
    return store.transaction(q,'catalog',apply)

def copy_context(c,origin,nid):
    dest='note:'+nid
    for table,cols in [('membership','topic'),('tags','label,norm')]:
        c.execute(f'INSERT OR IGNORE INTO {table}(target,{cols}) SELECT ?,{cols} FROM {table} WHERE target=?',(dest,origin))
    if origin.startswith('highlight:'):
        a=c.execute('SELECT origin FROM anchors WHERE highlight=?',(origin.split(':',1)[1],)).fetchone()
        if a and a[0].startswith('note:'):
            c.execute('INSERT OR IGNORE INTO membership SELECT ?,topic FROM membership WHERE target=?',(dest,a[0]))
    if origin.startswith('highlight:') and a and a[0].startswith('note:'):
        nid_origin=a[0].split(':',1)[1]
        primary=c.execute('SELECT source_id,locator FROM note_sources WHERE note_id=?',(nid_origin,)).fetchone()
        if primary and not c.execute('SELECT 1 FROM note_sources WHERE note_id=?',(nid,)).fetchone():
            c.execute('INSERT INTO note_sources VALUES(?,?,?,?)',(uid(),nid,*primary))
    for r in c.execute('SELECT source,locator FROM citations WHERE target=?',(origin,)).fetchall():
        c.execute('INSERT INTO citations VALUES(?,?,?,?)',(uid(),dest,*r))
