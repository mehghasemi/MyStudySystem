import argparse
import ctypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import msvcrt
import os
from pathlib import Path
import re
import secrets
import sys
import threading
import time
from urllib.parse import parse_qs, urlsplit
import webbrowser

sys.path.insert(0, str(Path(__file__).resolve().parent))
from store import Store, Problem, normalized, sync_risks

ASSETS = Path(__file__).resolve().parent / 'static'


class Application:
    def __init__(self, data):
        self.store = Store(data, ASSETS)
        self.token = secrets.token_urlsafe(32)
        self.csrf = secrets.token_urlsafe(32)
        self.closing = False
        self.tabs = {}
        self.lock = threading.RLock()

    def action(self, route, obj):
        with self.lock:
            if self.closing:
                raise Problem('برنامه بسته شده است؛ دوباره از فایل اجرایی باز کنید.', 503)
            return self._action(route, obj)

    def _action(self, route, obj):
        s = self.store
        if route == 'catalog':
            from catalog import command
            return command(s,obj)
        if route == 'review':
            from review import command
            return command(s,obj)
        if route == 'save':
            return s.save(obj)
        if route == 'seed':
            return s.seed()
        if route == 'preferences':
            for key in ('theme', 'collapsed'):
                if key in obj:
                    s.setting(key, obj[key])
            return {'ok': True}
        if route == 'source-save':
            return s.save_source(obj)
        if route == 'bookmark':
            return s.bookmark(obj)
        if route == 'read-source':
            return s.touch_source(obj)
        if route == 'draft':
            return s.draft(obj)
        if route == 'discard-draft':
            return s.discard_draft(obj)
        if route == 'highlight':
            body = obj.get('body', '').strip()
            if not body or len(body) > 20000:
                raise Problem('متن گزیده خالی یا بیش از حد بلند است.')
            with s.connect() as c:
                c.execute('INSERT INTO highlights VALUES(?,?,?,?)', (secrets.token_hex(12), body, obj.get('source', ''), obj.get('location', '')))
            return {'ok': True}
        if route == 'heartbeat':
            self.tabs[obj['tab']] = (time.monotonic(), bool(obj.get('dirty')))
            return {'ok': True}
        if route == 'close-tab':
            self.tabs.pop(obj.get('tab'), None)
            return {'ok': True}
        if route == 'shutdown':
            self.require_clean_tabs()
            self.closing = True
            return {'ok': True}
        raise Problem('عمل پیدا نشد.', 404)

    def require_clean_tabs(self):
        if any(dirty for stamp, dirty in self.tabs.values()):
            raise Problem('در یکی از تب‌ها نوشتهٔ ذخیره‌نشده وجود دارد؛ ابتدا آن را ذخیره کنید یا همان تب را با تأیید کنارگذاشتن تغییرات ببندید.', 409)


class Handler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    server_version = 'MyStudySystem/M1a'

    def log_message(self, *args):
        pass  # No note text, file paths, session tokens or request URLs in logs.

    @property
    def app(self):
        return self.server.app

    def send_headers(self, status, content_type, length, extra=None):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(length))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; font-src 'self'; img-src 'self' data:; media-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()

    def respond(self, obj, status=200):
        raw = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_headers(status, 'application/json; charset=utf-8', len(raw))
        self.wfile.write(raw)

    def do_GET(self):
        self.handle_request(False)

    def do_POST(self):
        self.handle_request(True)

    def handle_request(self, post):
        # Response method has a distinct name because request headers is an instance attribute.
        try:
            host = f'127.0.0.1:{self.server.server_port}'
            cookie = f'pkl{self.server.server_port}={self.app.token}'
            if self.headers.get('Host') != host:
                raise Problem('میزبان درخواست معتبر نیست.', 403)
            url = urlsplit(self.path)
            query = parse_qs(url.query)
            if not post and url.path == '/' and query.get('launch', [''])[0] == self.app.token:
                self.send_headers(303, 'text/plain', 0, {'Set-Cookie': f'{cookie}; HttpOnly; SameSite=Strict; Path=/', 'Location': '/'})
                return
            if cookie not in self.headers.get('Cookie', '').split('; '):
                raise Problem('برنامه را از فایل اجرایی باز کنید.', 403)
            if post:
                if self.headers.get('Origin') != f'http://{host}' or self.headers.get('X-CSRF') != self.app.csrf:
                    raise Problem('درخواست از برنامهٔ محلی صادر نشده است.', 403)
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 2_000_000:
                    raise Problem('اندازهٔ درخواست مجاز نیست.', 413)
                obj = json.loads(self.rfile.read(size))
                if not isinstance(obj, dict) or not url.path.startswith('/api/'):
                    raise Problem('درخواست معتبر نیست.')
                self.respond(self.app.action(url.path.removeprefix('/api/'), obj))
                return
            if url.path == '/api/state':
                self.respond({**self.app.store.state(), 'csrf': self.app.csrf})
            elif url.path == '/api/document':
                from catalog import one,config,resolve,EXT
                with self.app.store.connect() as c:
                    ref=one(c,'file_refs',query.get('id',[''])[0])
                    file=resolve(self.app.store,config(c)['root'],ref['rel'])
                mime=EXT.get(file.suffix.lower())
                if not mime or not file.is_file():raise Problem('فایل در دسترس نیست.',404)
                with file.open('rb') as stream:
                    self.send_headers(200,mime,os.fstat(stream.fileno()).st_size)
                    import shutil
                    shutil.copyfileobj(stream,self.wfile,128*1024)
            elif url.path == '/api/search':
                phrase = normalized(query.get('q', [''])[0])
                state = self.app.store.state()
                found=[dict(id=t['id'],title=t['label'],body='موضوع',kind='topics') for t in state['catalog']['topics'] if t['status']=='active' and phrase in normalized(t['label'])]
                found.extend({**n,'kind':kind} for kind in ('notes','sources','highlights') for n in state[kind] if n.get('status','active')=='active' and phrase in normalized(n.get('title','')+' '+n['body']))
                self.respond({'results':found[:100]})
            else:
                files = {'/': 'index.html', '/style.css': 'style.css', '/ui.js': 'ui.js', '/catalog.js':'catalog.js', '/calendar.js': 'calendar.js', '/Vazirmatn.ttf': 'Vazirmatn.ttf'}
                if url.path not in files:
                    raise Problem('صفحه پیدا نشد.', 404)
                self.serve_file(ASSETS / files[url.path])
        except Problem as e:
            self.respond({'error': str(e)}, e.status)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass
        except (ValueError, KeyError, TypeError):
            self.respond({'error': 'ورودی معتبر نیست؛ نوشتهٔ شما حفظ شده است.'}, 400)
        except Exception:
            self.respond({'error': 'عمل انجام نشد؛ دسترسی پوشه و فضای دیسک را بررسی و دوباره تلاش کنید. نوشتهٔ شما حفظ شده است.'}, 500)

    def serve_file(self, path):
        if not path.is_file():
            raise Problem('فایل پیدا نشد.', 404)
        raw = path.read_bytes()
        mime = {'.html':'text/html', '.css':'text/css', '.js':'text/javascript', '.ttf':'font/ttf'}.get(path.suffix, 'application/octet-stream')
        if mime.startswith('text/'):
            mime += '; charset=utf-8'
        self.send_headers(200, mime, len(raw))
        self.wfile.write(raw)


def start():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', type=Path)
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--allow-sync', action='store_true')
    parser.add_argument('--port', type=int, default=0)
    args = parser.parse_args()
    home = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
    data = (args.data or home.parent / 'data').resolve()
    if sync_risks(data) and not args.allow_sync:
        message = ('پوشهٔ مطالعه در مسیر همگام‌سازی است. در زمان ذخیره، ممکن است نسخهٔ ناقص به فضای ابری منتقل شود.\n\n'
                   'برای استفادهٔ نوبتی، هنگام مطالعه سینک را موقتاً متوقف کنید. پس از «خروج کامل»، سینک را فعال کنید و پیش از بازکردن روی دستگاه دیگر، منتظر تکمیل آن بمانید.\n\n'
                   'برنامه در همین پوشه باز شود؟')
        if args.no_browser:
            raise Problem('برای اجرای آگاهانه در مسیر سینک از --allow-sync استفاده کنید.')
        if ctypes.windll.user32.MessageBoxW(None, message, 'سیستم مطالعه من', 0x00000004 | 0x00000100 | 0x00180000) != 6:
            return
    data.mkdir(parents=True, exist_ok=True)
    lock = (data / 'instance.lock').open('a+b')
    if lock.seek(0, 2) == 0:
        lock.write(b'0')
        lock.flush()
    lock.seek(0)
    try:
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        if not args.no_browser:
            try:
                webbrowser.open(json.loads((data / 'session.json').read_text())['url'])
            except (OSError, ValueError):
                raise Problem('برنامه در حال اجرا یا راه‌اندازی است؛ چند ثانیه بعد دوباره باز کنید.')
        lock.close()
        return
    server = None
    try:
        app = Application(data)
        server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
        server.daemon_threads = False
        server.app = app
        server.timeout = 0.3
        url = f'http://127.0.0.1:{server.server_port}/?launch={app.token}'
        session = data / 'session.json'
        session.write_text(json.dumps({'url': url, 'pid': os.getpid(), 'port': server.server_port}), encoding='utf-8')
        if not args.no_browser:
            webbrowser.open(url)
        while not app.closing:
            server.handle_request()
    finally:
        if server:
            server.server_close()
        (data / 'session.json').unlink(missing_ok=True)
        lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
        lock.close()


if __name__ == '__main__':
    try:
        start()
    except Exception as error:
        message = str(error) if isinstance(error, Problem) else 'راه‌اندازی ممکن نشد. دسترسی نوشتن پوشه، فضای دیسک و سالم‌بودن داده را بررسی کنید. دادهٔ موجود حذف نشده است.'
        if '--no-browser' in sys.argv:
            print(message, file=sys.stderr)
        else:
            ctypes.windll.user32.MessageBoxW(None, message, 'سیستم مطالعه من', 0x10)
        sys.exit(1)
