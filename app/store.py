"""G0 synthetic persistence. No F1 scheduling policy is implemented here."""
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

SCHEMA = 2


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


class Store:
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
                if version != SCHEMA:
                    raise Problem(f'نسخهٔ داده {version} پشتیبانی نمی‌شود؛ برنامهٔ سازگار لازم است. داده جایگزین نشد.')
                if c.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise Problem('پایگاه داده آسیب دیده است؛ فایل موجود حفظ شد.')
                for table, columns in {'settings':'key,value','notes':'id,title,body,revision,due,at_utc','sources':'id,title,body,page','highlights':'id,body,source,location','operations':'id,payload,result'}.items():
                    c.execute(f'SELECT {columns} FROM {table} LIMIT 1')
        except sqlite3.Error as e:
            raise Problem('بازکردن داده ممکن نیست؛ فایل موجود حفظ شد. فایل موجود را برای بررسی نگه دارید.') from e

    def settings(self):
        with self.connect() as c:
            return {r['key']: json.loads(r['value']) for r in c.execute('SELECT * FROM settings')}

    def setting(self, key, value):
        with self.connect() as c:
            c.execute('INSERT OR REPLACE INTO settings VALUES(?,?)', (key, json.dumps(value, ensure_ascii=False)))

    def state(self):
        with self.connect() as c:
            return dict(notes=[dict(r) for r in c.execute('SELECT * FROM notes ORDER BY rowid DESC')],
                        sources=[dict(r) for r in c.execute('SELECT * FROM sources ORDER BY id')],
                        highlights=[dict(r) for r in c.execute('SELECT * FROM highlights')],
                        settings=self.settings(),
                        data_path=str(self.data), schema=SCHEMA, version='G0-r1')

    def save(self, request):
        for key in ('id', 'title', 'body', 'due', 'at_utc', 'operation_id'):
            if not isinstance(request.get(key), str):
                raise Problem('ورودی ذخیره معتبر نیست.')
        if type(request.get('revision')) is not int or not request['id'] or not request['operation_id'] or max(len(request['id']), len(request['operation_id'])) > 100:
            raise Problem('شناسه یا نسخهٔ ذخیره معتبر نیست.')
        if not request['title'].strip() or not request['body'].strip():
            raise Problem('عنوان و متن را بنویسید؛ نوشتهٔ شما حفظ شده است.')
        if len(request['body']) > 200000 or len(request['title']) > 250:
            raise Problem('عنوان حداکثر ۲۵۰ نویسه و متن حداکثر ۲۰۰ هزار نویسه باشد.')
        if request['due']:
            from datetime import date
            try:
                date.fromisoformat(request['due'])
            except ValueError:
                raise Problem('تاریخ معتبر نیست.')
        if request['at_utc']:
            try:
                moment = datetime.fromisoformat(request['at_utc'].replace('Z', '+00:00'))
                if moment.tzinfo is None:
                    raise ValueError()
            except ValueError:
                raise Problem('زمان باید با منطقهٔ زمانی ذخیره شود.')
        payload = hashlib.sha256(json.dumps(request, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            previous = c.execute('SELECT * FROM operations WHERE id=?', (request['operation_id'],)).fetchone()
            if previous:
                if previous['payload'] != payload:
                    raise Problem('کلید ذخیره برای متن متفاوت استفاده شده است.', 409)
                return json.loads(previous['result'])
            old = c.execute('SELECT revision FROM notes WHERE id=?', (request['id'],)).fetchone()
            rev = old['revision'] if old else 0
            if request.get('revision') != rev:
                raise Problem('این یادداشت در تب دیگری تغییر کرده است. پیش‌نویس حفظ شد؛ آخرین نسخه را بارگیری کنید یا نسخهٔ جدا ذخیره کنید.', 409)
            result = dict(id=request['id'], revision=rev + 1)
            c.execute('INSERT OR REPLACE INTO notes VALUES(?,?,?,?,?,?)', (request['id'], request['title'], request['body'], rev + 1, request['due'], request['at_utc']))
            c.execute('INSERT INTO operations VALUES(?,?,?)', (request['operation_id'], payload, json.dumps(result)))
            return result

    def seed(self):
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            if c.execute('SELECT count(*) FROM notes').fetchone()[0] or c.execute('SELECT count(*) FROM sources').fetchone()[0]:
                raise Problem('داده وجود دارد؛ نمونه دوباره ساخته نشد.')
            c.execute('INSERT INTO sources VALUES(?,?,?,?)', ('book-1', 'مکث پیش از واکنش', 'گاهی میان شنیدن یک جمله و پاسخ ما فقط چند ثانیه فاصله است. همین فاصله می‌تواند فرصتی برای انتخاب باشد.\n\nدر این کتاب ساختگی، تمرین می‌کنیم پیش از پاسخ‌دادن، احساس خود را نام ببریم و یک نفس آرام بکشیم. هدف حذف خشم نیست؛ می‌خواهیم پیام آن را بفهمیم و رفتارمان را انتخاب کنیم.\n\nتمرین کوتاه: موقعیتی از امروز را به یاد بیاورید. چه چیزی را می‌توانستید متفاوت بیان کنید؟\n\nاین متن فقط دادهٔ مصنوعی برای آزمایش برنامه است. Active recall یعنی تلاش برای یادآوری پیش از بازخوانی.', 47))
            c.execute('INSERT INTO sources VALUES(?,?,?,?)', ('book-2', 'یادگیری با توضیح ساده', 'توضیح یک مفهوم با زبان خودمان کمک می‌کند جاهای مبهم را پیدا کنیم.\nمنبع دوم مصنوعی است؛ بدون نیاز به ساخت یادداشت می‌توانید آن را بخوانید.', 12))
            c.execute('INSERT INTO notes VALUES(?,?,?,?,?,?)', ('note-1', 'وقتی خشمگین می‌شوم، اولین قدم چیست؟', 'پیش از واکنش، مکث می‌کنم؛ احساس را نام می‌برم و یک نفس آرام می‌کشم.\nبرداشت شخصی آزمایشی: Pause → Name → Choose\nنشانی نمونه: https://example.org/learn', 1, '2026-11-07', '2026-11-06T23:29:00Z'))
            c.execute('INSERT INTO notes VALUES(?,?,?,?,?,?)', ('note-2', 'توضیح با یک مثال', 'یک مفهوم را با زبان خودم و یک مثال ساده توضیح می‌دهم؛ سپس برای یافتن جاهای مبهم به متن برمی‌گردم.', 1, '2026-11-08', '2026-11-06T23:30:00Z'))
            c.execute('INSERT INTO highlights VALUES(?,?,?,?)', ('hl-1', 'هدف حذف خشم نیست؛ می‌خواهیم رفتارمان را انتخاب کنیم.', 'book-1', 'صفحهٔ ۱۲'))
        return self.state()

