"""Offline Windows package from an allowlist and the installed CPython runtime."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'dist' / 'MyStudySystem-G0-r1-win'
APP = OUT / 'app'
RUNTIME = APP / 'runtime'
PYTHON = Path(sys.base_prefix)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build():
    # Refuse to overwrite a running or previously used package. No recursive deletion.
    if (OUT / 'data').exists():
        raise SystemExit('Package folder has data; move the test copy elsewhere before building.')
    APP.mkdir(parents=True, exist_ok=True)
    RUNTIME.mkdir(exist_ok=True)
    allowed=set()
    def copy(source, dest):
        shutil.copyfile(source,dest)
        allowed.add(dest)
    approved = ['main.py','store.py','static/index.html','static/style.css','static/ui.js','static/calendar.js','static/Vazirmatn.ttf','static/OFL.txt']
    for relative in approved:
        dest = APP / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        copy(ROOT/'app'/relative, dest)
    pyver=f'python{sys.version_info.major}{sys.version_info.minor}'
    for name in ['python.exe','pythonw.exe','python3.dll',pyver+'.dll','vcruntime140.dll','vcruntime140_1.dll','LICENSE.txt']:
        copy(PYTHON/name,RUNTIME/name)
    dlls=RUNTIME/'DLLs';dlls.mkdir(exist_ok=True)
    for name in ['_socket.pyd','_sqlite3.pyd','sqlite3.dll','_ctypes.pyd','libffi-8.dll','unicodedata.pyd','select.pyd','_hashlib.pyd','libcrypto-3.dll','_ssl.pyd','libssl-3.dll','_bz2.pyd','_lzma.pyd','_decimal.pyd','_queue.pyd','_uuid.pyd','_wmi.pyd','_overlapped.pyd','_winapi.pyd','_zstd.pyd','zlib1.dll']:
        if (PYTHON/'DLLs'/name).exists():copy(PYTHON/'DLLs'/name,dlls/name)
    excluded={'site-packages','test','tests','idlelib','tkinter','turtledemo','ensurepip','venv','__pycache__'}
    with zipfile.ZipFile(RUNTIME/(pyver+'.zip'),'w',zipfile.ZIP_DEFLATED) as z:
        for source in sorted((PYTHON/'Lib').rglob('*.py')):
            rel=source.relative_to(PYTHON/'Lib')
            if not any(part in excluded for part in rel.parts):z.write(source,rel.as_posix())
    (RUNTIME/(pyver+'._pth')).write_text(pyver+'.zip\nDLLs\n.\n..\n',encoding='ascii')
    allowed.update([RUNTIME/(pyver+'.zip'),RUNTIME/(pyver+'._pth')])
    csc=Path('C:/Windows/Microsoft.NET/Framework64/v4.0.30319/csc.exe')
    subprocess.run([str(csc),'/nologo','/target:winexe','/platform:x64','/reference:System.Windows.Forms.dll','/out:'+str(APP/'MyStudySystem.exe'),str(ROOT/'scripts/Launcher.cs')],check=True)
    (APP/'MyStudySystem.exe.config').write_text('<?xml version="1.0"?><configuration><startup><supportedRuntime version="v4.0" sku=".NETFramework,Version=v4.0"/></startup></configuration>',encoding='utf-8')
    allowed.update([APP/'MyStudySystem.exe',APP/'MyStudySystem.exe.config'])
    for name in ['README.md','docs/USER_GUIDE.md']:
        source=ROOT/name
        if source.exists():copy(source,OUT/source.name)
    source_files=approved+['../scripts/Launcher.cs','../scripts/build.py']
    sources={name:sha(ROOT/'app'/name) for name in source_files}
    manifest={'version':'G0-r1','schema':2,'prd':'3.12','python':sys.version,'sqlite':__import__('sqlite3').sqlite_version,'built_at':datetime.now(timezone.utc).isoformat(),'source_sha256':sources,'source_id':hashlib.sha256(json.dumps(sources,sort_keys=True).encode()).hexdigest(),'files':{p.relative_to(OUT).as_posix():sha(p) for p in sorted(allowed)}}
    (OUT/'BUILD_MANIFEST.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    allowed.add(OUT/'BUILD_MANIFEST.json')
    archive=OUT.with_suffix('.zip')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(allowed):
            if p.is_file():
                relative=p.relative_to(OUT)
                assert relative.parts[0] in {'app','README.md','USER_GUIDE.md','BUILD_MANIFEST.json'}
                assert p.suffix.lower() not in {'.sqlite','.db','.log','.mp3','.m4a'}
                assert '__pycache__' not in relative.parts
                z.write(p,relative.as_posix())
    digest=sha(archive)
    archive.with_suffix('.zip.sha256').write_text(digest+'  '+archive.name+'\n',encoding='ascii')
    print(json.dumps({'zip':str(archive),'sha256':digest,'bytes':archive.stat().st_size,'source_id':manifest['source_id']},indent=2))


if __name__=='__main__':build()
