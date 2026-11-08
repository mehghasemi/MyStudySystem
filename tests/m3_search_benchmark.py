"""Search P95 in a new synthetic 35,000-item library (no operational files)."""
from pathlib import Path
import tempfile,time,json,sys,math
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/'app'))
from store import Store,now
from daily import search
with tempfile.TemporaryDirectory() as tmp:
 s=Store(tmp,root/'app/static');stamp=now()
 with s.connect() as c:
  c.executemany("INSERT INTO notes VALUES(?,?,1,'','','active',?,?)",((f'n{i}',f'یادداشت {i}',stamp,stamp) for i in range(5000)))
  c.executemany("INSERT INTO note_sections(id,note_id,kind,position,content_text,revision) VALUES(?,?,'body',0,?,1)",((f'b{i}',f'n{i}',f'آزمون یادگیری و رفتار شمارهٔ {i} در خانه') for i in range(5000)))
  c.executemany('INSERT INTO sources VALUES(?,?,?,1)',((f's{i}',f'کتاب {i}',f'مکث قبل از واکنش {i}') for i in range(10000)))
  c.executemany('INSERT INTO source_details(source_id,created_at,updated_at) VALUES(?,?,?)',((f's{i}',stamp,stamp) for i in range(10000)))
  c.executemany('INSERT INTO highlights VALUES(?,?,?,?)',((f'h{i}',f'گزیدهٔ روش مطالعه {i}',f's{i%10000}','صفحهٔ ۴۷') for i in range(20000)))
 elapsed=[]
 for q in ['گزیده','يادگيري','کتاب ۹۹۹','مكث','ناموجود']*4:
  start=time.perf_counter();found=search(s,{'q':q});elapsed.append(round(time.perf_counter()-start,4))
  assert bool(found)==(q!='ناموجود')
 result={'notes':5000,'sources':10000,'highlights':20000,'seconds':elapsed,'p95':sorted(elapsed)[math.ceil(.95*len(elapsed))-1],'method':'daily.search, including database reads and ranking; excludes browser rendering'}
 (root/'docs/evidence/m3').mkdir(exist_ok=True);(root/'docs/evidence/m3/search-benchmark.json').write_text(json.dumps(result,indent=2))
 print(result)
