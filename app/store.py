"""M1-a persistence. Review scheduling is deferred to M1-b."""
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import unicodedata
import uuid
from contextlib import contextmanager, closing
from datetime import datetime, timezone

SCHEMA = 5


class Problem(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def normalized(text):
    text = unicodedata.normalize('NFKC', text).translate(str.maketrans('يك٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹', 'یک01234567890123456789'))
    return ''.join(c for c in text if c not in 'ـ\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069' and not unicodedata.combining(c)).replace('\u200c', ' ').casefold()


def sync_risks(path):
    p = str(Path(path).resolve()).casefold()
    roots = [v for k, v in os.environ.items() if k.casefold().startswith('onedrive')]
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\OneDrive\Accounts') as key:
            for i in range(winreg.QueryInfoKey(key)[0]):
                with winreg.OpenKey(key, winreg.EnumKey(key, i)) as account:
                    try:
                        roots.append(winreg.QueryValueEx(account, 'UserFolder')[0])
                    except OSError:
                        pass
    except (ImportError, OSError):
        pass
    if any(p == str(Path(r).resolve()).casefold() or p.startswith(str(Path(r).resolve()).casefold() + os.sep) for r in roots):
        return True
    return any(any(s in part for s in ('onedrive', 'dropbox', 'google drive', 'googledrive', 'icloud', 'syncthing')) for part in Path(p).parts)


class BaseStore:
    def __init__(self, data, assets):
        self.data, self.assets = Path(data), Path(assets)
        self.data.mkdir(parents=True, exist_ok=True)
        self.db = self.data / 'study.sqlite'
        if self.db.exists():
            self.inspect(self.db)
        else:
            with self.connect(create=True) as c:
                c.executescript('''
                CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
                CREATE TABLE notes(id TEXT PRIMARY KEY,title TEXT NOT NULL,body TEXT NOT NULL,revision INTEGER NOT NULL DEFAULT 1,due TEXT NOT NULL DEFAULT '',at_utc TEXT NOT NULL DEFAULT '');
                CREATE TABLE sources(id TEXT PRIMARY KEY,title TEXT NOT NULL,body TEXT NOT NULL,page INTEGER NOT NULL);
                CREATE TABLE highlights(id TEXT PRIMARY KEY,body TEXT NOT NULL,source TEXT NOT NULL,location TEXT NOT NULL);
                CREATE TABLE operations(id TEXT PRIMARY KEY,payload TEXT NOT NULL,result TEXT NOT NULL);
                PRAGMA user_version=2;
                ''')

    @contextmanager
    def connect(self, path=None, create=False):
        uri = Path(path or self.db).resolve().as_uri() + ('?mode=rwc' if create else '?mode=rw')
        c = sqlite3.connect(uri, uri=True, timeout=3)
        c.row_factory = sqlite3.Row
        c.execute('PRAGMA foreign_keys=ON')
        try:
            with c:
                yield c
        finally:
            c.close()

    @staticmethod
    def version(path):
        with closing(sqlite3.connect(path)) as c:
            return c.execute('PRAGMA user_version').fetchone()[0]

    @staticmethod
    def inspect(path):
        try:
            with closing(sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)) as c:
                version = c.execute('PRAGMA user_version').fetchone()[0]
                if version not in (2, 3, 4, SCHEMA):
                    raise Problem(f'نسخهٔ داده {version} پشتیبانی نمی‌شود؛ برنامهٔ سازگار لازم است. داده جایگزین نشد.')
                if c.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise Problem('پایگاه داده آسیب دیده است؛ فایل موجود حفظ شد.')
                for table, columns in {'settings':'key,value','notes':('id,title,body,revision,due,at_utc' if version == 2 else 'id,title,revision,due,at_utc,status'),'sources':'id,title,body,page','highlights':'id,body,source,location','operations':'id,payload,result'}.items():
                    c.execute(f'SELECT {columns} FROM {table} LIMIT 1')
        except sqlite3.Error as e:
            raise Problem('بازکردن داده ممکن نیست؛ فایل موجود حفظ شد. فایل موجود را برای بررسی نگه دارید.') from e

    def settings(self):
        with self.connect() as c:
            return {r['key']: json.loads(r['value']) for r in c.execute('SELECT * FROM settings')}

    def setting(self, key, value):
        with self.connect() as c:
            c.execute('INSERT OR REPLACE INTO settings VALUES(?,?)', (key, json.dumps(value, ensure_ascii=False)))


def now():
    return datetime.now(timezone.utc).isoformat()


def text_field(obj, key, limit, required=False):
    value = obj.get(key, '')
    if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
        raise Problem('متن خالی یا بیش از حد بلند است؛ نوشتهٔ شما حفظ شده است.')
    return value


class Store(BaseStore):
    """M1-a: headers, sections and progress have distinct data ownership."""
    def __init__(self, data, assets):
        super().__init__(data, assets)
        with self.connect() as c:
            if c.execute('PRAGMA user_version').fetchone()[0] == 2:
                self.upgrade(c)
            if c.execute("PRAGMA user_version").fetchone()[0] == 3:
                from review import install
                if not c.in_transaction: c.execute("BEGIN IMMEDIATE")
                install(c)
            if c.execute("PRAGMA user_version").fetchone()[0] == 4:
                from catalog import install
                if not c.in_transaction: c.execute("BEGIN IMMEDIATE")
                install(c)
            for table in ('note_sections', 'note_sources', 'source_details', 'reading_progress', 'drafts'):
                c.execute(f'SELECT * FROM {table} LIMIT 1')

        from catalog import recover
        recover(self)

    def upgrade(self, c):
        # Transactional compatibility upgrade, not backup or restore.
        c.execute('BEGIN IMMEDIATE')
        c.execute('ALTER TABLE notes RENAME TO legacy_notes')
        c.execute("CREATE TABLE notes(id TEXT PRIMARY KEY,title TEXT NOT NULL,revision INTEGER NOT NULL,due TEXT NOT NULL,at_utc TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'active',created_at TEXT NOT NULL,updated_at TEXT NOT NULL)")
        c.execute('CREATE TABLE note_sections(id TEXT PRIMARY KEY,note_id TEXT NOT NULL REFERENCES notes(id),kind TEXT NOT NULL,position INTEGER NOT NULL,content_text TEXT NOT NULL,content_format TEXT NOT NULL DEFAULT \'plain\',revision INTEGER NOT NULL,UNIQUE(note_id,kind))')
        c.execute('CREATE TABLE note_sources(id TEXT PRIMARY KEY,note_id TEXT UNIQUE NOT NULL REFERENCES notes(id),source_id TEXT NOT NULL REFERENCES sources(id),locator TEXT NOT NULL)')
        c.execute("CREATE TABLE source_details(source_id TEXT PRIMARY KEY REFERENCES sources(id),type TEXT NOT NULL DEFAULT 'book',creator TEXT NOT NULL DEFAULT '',publisher TEXT NOT NULL DEFAULT '',revision INTEGER NOT NULL DEFAULT 1,content_revision INTEGER NOT NULL DEFAULT 1,status TEXT NOT NULL DEFAULT 'active',created_at TEXT NOT NULL,updated_at TEXT NOT NULL)")
        c.execute("CREATE TABLE reading_progress(source_id TEXT PRIMARY KEY REFERENCES sources(id),page INTEGER NOT NULL,chapter TEXT NOT NULL DEFAULT '',revision INTEGER NOT NULL DEFAULT 1,last_read_at TEXT NOT NULL DEFAULT '')")
        c.execute('CREATE TABLE drafts(id TEXT PRIMARY KEY,kind TEXT NOT NULL,payload TEXT NOT NULL,updated_at TEXT NOT NULL,revision INTEGER NOT NULL)')
        stamp = now()
        c.execute("INSERT INTO notes SELECT id,title,revision,due,at_utc,'active',?,? FROM legacy_notes", (stamp, stamp))
        for n in c.execute('SELECT * FROM legacy_notes').fetchall():
            c.execute('INSERT INTO note_sections(id,note_id,kind,position,content_text,revision) VALUES(?,?,?,?,?,?)', (str(uuid.uuid4()), n['id'], 'body', 0, n['body'], n['revision']))
        c.execute('DROP TABLE legacy_notes')
        for src in c.execute('SELECT * FROM sources').fetchall():
            c.execute('INSERT INTO source_details(source_id,created_at,updated_at) VALUES(?,?,?)', (src['id'], stamp, stamp))
            c.execute('INSERT INTO reading_progress(source_id,page) VALUES(?,?)', (src['id'], src['page']))
        c.execute('PRAGMA user_version=3')

    def transaction(self, request, kind, action):
        operation = text_field(request, 'operation_id', 100, True)
        payload = hashlib.sha256(json.dumps([kind, request], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            previous = c.execute('SELECT * FROM operations WHERE id=?', (operation,)).fetchone()
            if previous:
                if previous['payload'] != payload:
                    raise Problem('این فرمان قبلاً با ورودی دیگری استفاده شده است.', 409)
                return json.loads(previous['result'])
            result = action(c)
            c.execute('INSERT INTO operations VALUES(?,?,?)', (operation, payload, json.dumps(result)))
            return result

    @staticmethod
    def expected(request, actual):
        if type(request.get('revision')) is not int or request['revision'] != actual:
            raise Problem('این مورد در تب دیگری تغییر کرده است؛ نوشتهٔ شما حفظ شد. آخرین نسخه را ببینید یا نوشته را جدا ذخیره کنید.', 409)

    def state(self):
        with self.connect() as c:
            notes = []
            for row in c.execute("SELECT * FROM notes WHERE status='active' ORDER BY updated_at DESC,rowid DESC"):
                n = dict(row)
                sections = [dict(r) for r in c.execute('SELECT * FROM note_sections WHERE note_id=? ORDER BY position', (n['id'],))]
                n['sections'] = {r['kind']: r['content_text'] for r in sections}
                n['section_records'] = sections
                n['body'] = n['sections'].get('body', '')
                ref = c.execute('SELECT * FROM note_sources WHERE note_id=?', (n['id'],)).fetchone()
                n['source_id'], n['locator'] = (ref['source_id'], ref['locator']) if ref else ('', '')
                notes.append(n)
            sources = [dict(r) for r in c.execute('SELECT s.id,s.title,s.body,d.*,p.page,p.chapter,p.revision AS progress_revision,p.last_read_at FROM sources s JOIN source_details d ON d.source_id=s.id JOIN reading_progress p ON p.source_id=s.id ORDER BY p.last_read_at DESC,d.updated_at DESC,s.id')]
            drafts = [dict(r) for r in c.execute('SELECT * FROM drafts ORDER BY updated_at DESC')]
            for d in drafts:
                d['payload'] = json.loads(d['payload'])
            return dict(notes=notes, sources=sources, highlights=[dict(r) for r in c.execute('SELECT * FROM highlights')], drafts=drafts, settings=self.settings(), data_path=str(self.data), schema=SCHEMA, version='M2-r1', catalog=__import__('catalog').snapshot(self,c), review=__import__('review').summary(c,__import__('review').day()))

    def save(self, request):
        ident = text_field(request, 'id', 100, True)
        title = text_field(request, 'title', 250, True)
        body = text_field(request, 'body', 200000, True)
        due, at_utc = text_field(request, 'due', 10), text_field(request, 'at_utc', 50)
        from datetime import date
        try:
            if due: date.fromisoformat(due)
            if at_utc and datetime.fromisoformat(at_utc.replace('Z', '+00:00')).tzinfo is None: raise ValueError()
        except ValueError:
            raise Problem('تاریخ یا ساعت معتبر نیست.')
        sections = request.get('sections', {})
        if not isinstance(sections, dict) or set(sections) - {'summary', 'personal', 'application'}:
            raise Problem('بخش یادداشت معتبر نیست.')
        for key in sections: text_field(sections, key, 100000)
        source_id, locator = text_field(request, 'source_id', 100), text_field(request, 'locator', 500)
        def action(c):
            old = c.execute('SELECT * FROM notes WHERE id=?', (ident,)).fetchone()
            self.expected(request, old['revision'] if old else 0)
            if old and old['status'] != 'active': raise Problem('یادداشت بایگانی شده است.', 409)
            if source_id:
                src = c.execute('SELECT status FROM source_details WHERE source_id=?', (source_id,)).fetchone()
                existing_ref=c.execute('SELECT source_id FROM note_sources WHERE note_id=?',(ident,)).fetchone()
                if not src or (src['status'] != 'active' and (not existing_ref or existing_ref['source_id'] != source_id)):
                    raise Problem('کتاب انتخابی در دسترس نیست؛ کتاب دیگری انتخاب کنید.')
            rev, stamp = request['revision'] + 1, now()
            c.execute('INSERT INTO notes VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET title=excluded.title,revision=excluded.revision,due=excluded.due,at_utc=excluded.at_utc,updated_at=excluded.updated_at', (ident,title,rev,due,at_utc,'active',stamp,stamp))
            for pos, (kind, text) in enumerate({'body':body, **sections}.items()):
                c.execute('INSERT INTO note_sections(id,note_id,kind,position,content_text,revision) VALUES(?,?,?,?,?,1) ON CONFLICT(note_id,kind) DO UPDATE SET content_text=excluded.content_text,revision=note_sections.revision+1 WHERE note_sections.content_text<>excluded.content_text', (str(uuid.uuid4()),ident,kind,pos,text))
            if source_id:
                c.execute('INSERT INTO note_sources VALUES(?,?,?,?) ON CONFLICT(note_id) DO UPDATE SET source_id=excluded.source_id,locator=excluded.locator', (str(uuid.uuid4()),ident,source_id,locator))
            else: c.execute('DELETE FROM note_sources WHERE note_id=?', (ident,))
            if not old and request.get('initial_topics'):
                topics=request['initial_topics']
                if not isinstance(topics,list) or len(topics)>100:raise Problem('فهرست موضوع‌ها معتبر نیست.')
                for topic_id in set(topics):
                    if not c.execute("SELECT 1 FROM topics WHERE id=? AND status='active'",(topic_id,)).fetchone():raise Problem('موضوع انتخابی در دسترس نیست.')
                    c.execute('INSERT INTO membership VALUES(?,?)',('note:'+ident,topic_id))
                c.execute('UPDATE library_config SET rev=rev+1')
            return {'id':ident,'revision':rev}
        return self.transaction(request, 'note', action)

    def save_source(self, request):
        ident = text_field(request, 'id', 100, True)
        title = text_field(request, 'title', 250, True)
        body = text_field(request, 'body', 200000)
        creator, publisher = text_field(request, 'creator', 250), text_field(request, 'publisher', 250)
        status = request.get('status', 'active')
        if status not in ('active','archived','deleted'): raise Problem('وضعیت کتاب معتبر نیست.')
        def action(c):
            old = c.execute('SELECT s.body,d.* FROM sources s JOIN source_details d ON d.source_id=s.id WHERE s.id=?', (ident,)).fetchone()
            self.expected(request, old['revision'] if old else 0)
            if old and old['status'] == 'deleted': raise Problem('بازیابی کتاب حذف‌شده در این نسخه وجود ندارد.', 409)
            rev, stamp = request['revision'] + 1, now()
            c.execute('INSERT INTO sources VALUES(?,?,?,1) ON CONFLICT(id) DO UPDATE SET title=excluded.title,body=excluded.body', (ident,title,body))
            content_revision = old['content_revision'] + int(old['body'] != body) if old else 1
            c.execute("INSERT INTO source_details VALUES(?,'book',?,?,?,?,?,?,?) ON CONFLICT(source_id) DO UPDATE SET creator=excluded.creator,publisher=excluded.publisher,revision=excluded.revision,content_revision=excluded.content_revision,status=excluded.status,updated_at=excluded.updated_at", (ident,creator,publisher,rev,content_revision,status,stamp,stamp))
            from catalog import KINDS
            kind=request.get('type',old['type'] if old else 'book')
            if kind not in KINDS:raise Problem('نوع منبع معتبر نیست.')
            c.execute('UPDATE source_details SET type=? WHERE source_id=?',(kind,ident))
            if 'url' in request:
                url=text_field(request,'url',2000)
                if url and not re.match(r'^https?://[^/\s]+',url,re.I):raise Problem('نشانی وب با http یا https شروع شود.')
                site=text_field(request,'site',250);accessed=text_field(request,'accessed',10)
                if accessed:
                    from datetime import date
                    try:date.fromisoformat(accessed)
                    except ValueError:raise Problem('تاریخ دسترسی معتبر نیست.')
                c.execute('INSERT OR REPLACE INTO source_meta VALUES(?,?,?,?)',(ident,url,site,accessed))
            c.execute('INSERT OR IGNORE INTO reading_progress(source_id,page) VALUES(?,1)', (ident,))
            return {'id':ident,'revision':rev,'content_revision':content_revision}
        return self.transaction(request, 'source', action)

    def bookmark(self, request):
        ident = text_field(request, 'id', 100, True)
        page, chapter = request.get('page'), text_field(request, 'chapter', 250)
        if type(page) is not int or not 1 <= page <= 100000: raise Problem('شمارهٔ صفحه باید بین ۱ و ۱۰۰۰۰۰ باشد.')
        def action(c):
            old = c.execute('SELECT p.*,d.status FROM reading_progress p JOIN source_details d ON d.source_id=p.source_id WHERE p.source_id=?', (ident,)).fetchone()
            if not old or old['status'] != 'active': raise Problem('کتاب برای مطالعه در دسترس نیست.')
            self.expected(request, old['revision'])
            c.execute('UPDATE reading_progress SET page=?,chapter=?,revision=revision+1,last_read_at=? WHERE source_id=?', (page,chapter,now(),ident))
            return {'id':ident,'revision':old['revision']+1}
        return self.transaction(request, 'bookmark', action)

    def touch_source(self, request):
        ident = text_field(request, 'id', 100, True)
        with self.connect() as c:
            c.execute("UPDATE reading_progress SET last_read_at=? WHERE source_id=? AND EXISTS(SELECT 1 FROM source_details WHERE source_id=? AND status='active')", (now(),ident,ident))
        return {'ok':True}

    def draft(self, request):
        ident = text_field(request, 'id', 100, True)
        payload = request.get('payload')
        if not isinstance(payload, dict) or len(json.dumps(payload)) > 1500000: raise Problem('پیش‌نویس معتبر نیست.')
        def action(c):
            old=c.execute('SELECT revision FROM drafts WHERE id=?',(ident,)).fetchone()
            self.expected(request,old['revision'] if old else 0)
            rev=request['revision']+1
            c.execute("INSERT INTO drafts VALUES(?,'note',?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at,revision=excluded.revision",(ident,json.dumps(payload,ensure_ascii=False),now(),rev))
            return {'id':ident,'revision':rev}
        return self.transaction(request,'draft',action)

    def discard_draft(self, request):
        def action(c):
            old=c.execute('SELECT revision FROM drafts WHERE id=?',(request.get('id'),)).fetchone()
            self.expected(request,old['revision'] if old else 0)
            c.execute('DELETE FROM drafts WHERE id=?',(request['id'],))
            return {'ok':True}
        return self.transaction(request,'discard-draft',action)

    def seed(self):
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            if c.execute('SELECT count(*) FROM notes').fetchone()[0] or c.execute('SELECT count(*) FROM sources').fetchone()[0]: raise Problem('داده وجود دارد؛ نمونه دوباره ساخته نشد.')
            stamp=now()
            for ident,title,body,page in [('book-1','مکث پیش از واکنش','گاهی میان شنیدن یک جمله و پاسخ ما فقط چند ثانیه فاصله است. همین فاصله فرصتی برای انتخاب است.\n\nهدف حذف خشم نیست؛ می‌خواهیم رفتارمان را انتخاب کنیم.\n\nاین متن ساختگی است. Active recall یعنی تلاش پیش از بازخوانی.',47),('book-2','یادگیری با توضیح ساده','توضیح یک مفهوم با زبان خودمان کمک می‌کند جاهای مبهم را پیدا کنیم.\nمنبع دوم مصنوعی است.',12)]:
                c.execute('INSERT INTO sources VALUES(?,?,?,?)',(ident,title,body,page))
                c.execute('INSERT INTO source_details(source_id,created_at,updated_at) VALUES(?,?,?)',(ident,stamp,stamp))
                c.execute('INSERT INTO reading_progress(source_id,page) VALUES(?,?)',(ident,page))
            for ident,title,body,due,at in [('note-1','وقتی خشمگین می‌شوم، اولین قدم چیست؟','پیش از واکنش، مکث می‌کنم؛ احساس را نام می‌برم و یک نفس آرام می‌کشم.\nPause → Name → Choose','2026-11-07','2026-11-06T23:29:00Z'),('note-2','توضیح با یک مثال','یک مفهوم را با زبان خودم و یک مثال ساده توضیح می‌دهم.','2026-11-08','2026-11-06T23:30:00Z')]:
                c.execute("INSERT INTO notes VALUES(?,?,1,?,?,'active',?,?)",(ident,title,due,at,stamp,stamp))
                c.execute("INSERT INTO note_sections(id,note_id,kind,position,content_text,revision) VALUES(?,?,'body',0,?,1)",(str(uuid.uuid4()),ident,body))
            c.execute('INSERT INTO highlights VALUES(?,?,?,?)',('hl-1','هدف حذف خشم نیست؛ می‌خواهیم رفتارمان را انتخاب کنیم.','book-1','صفحهٔ ۱۲'))
        return self.state()

