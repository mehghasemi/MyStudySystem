import json
import sqlite3
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
from store import Store,BaseStore,Problem

class M1Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)
        self.store=Store(self.path,ROOT/'app/static')
    def tearDown(self):self.temp.cleanup()
    def source(self,**values):
        return dict(id='source',title='کتاب فارسی English',body='متن اصلی\n# **خام**',creator='نویسنده',publisher='ناشر',revision=0,operation_id=str(uuid.uuid4()),**values)
    def note(self):
        return dict(id='note',title='برداشت',body='متن بدنه',sections={'summary':'خلاصه','personal':'برداشت من','application':'کاربرد'},source_id='source',locator='صفحهٔ ۱۲',revision=0,due='',at_utc='',operation_id=str(uuid.uuid4()))
    def test_book_without_note_and_optional_text(self):
        req=self.source();req['body']='';self.store.save_source(req)
        state=Store(self.path,ROOT/'app/static').state()
        self.assertEqual(state['notes'],[]);self.assertEqual(state['sources'][0]['creator'],'نویسنده')
    def test_source_retry_and_stale_tab_preserve_body(self):
        req=self.source();one=self.store.save_source(req);self.assertEqual(one,self.store.save_source(req))
        bad={**req,'body':'دیگر'}
        with self.assertRaises(Problem):self.store.save_source(bad)
        req.update(revision=1,operation_id=str(uuid.uuid4()),body='نسخه دوم');self.store.save_source(req)
        with self.assertRaises(Problem):self.store.save_source({**req,'operation_id':str(uuid.uuid4())})
        self.assertEqual(self.store.state()['sources'][0]['body'],'نسخه دوم')
    def test_sections_have_stable_ids_and_original_text(self):
        self.store.save_source(self.source());req=self.note();self.store.save(req)
        before=self.store.state()['notes'][0];req.update(revision=1,operation_id=str(uuid.uuid4()),body='بدنه تازه');self.store.save(req)
        n=Store(self.path,ROOT/'app/static').state()['notes'][0]
        self.assertEqual(n['sections']['personal'],'برداشت من');self.assertEqual(n['locator'],'صفحهٔ ۱۲')
        self.assertEqual([s['id'] for s in before['section_records']],[s['id'] for s in n['section_records']])
        with self.store.connect() as c:self.assertNotIn('body',[r['name'] for r in c.execute('PRAGMA table_info(notes)')])
    def test_bookmark_revision_independent_of_text_and_excerpt(self):
        req=self.source();self.store.save_source(req)
        mark={'id':'source','page':47,'chapter':'فصل دوم','revision':1,'operation_id':'mark'}
        a=self.store.bookmark(mark);self.assertEqual(a,self.store.bookmark(mark))
        req.update(revision=1,body='ویرایش منبع',operation_id='edit');self.store.save_source(req)
        with self.assertRaises(Problem):self.store.bookmark({**mark,'page':48,'operation_id':'stale'})
        src=self.store.state()['sources'][0];self.assertEqual(src['page'],47);self.assertEqual(src['chapter'],'فصل دوم');self.assertEqual(src['progress_revision'],2)
    def test_last_opened_source_controls_continue(self):
        self.store.seed();self.store.touch_source({'id':'book-2'})
        self.assertEqual(Store(self.path,ROOT/'app/static').state()['sources'][0]['id'],'book-2')
    def test_soft_delete_keeps_text_and_note_reference(self):
        req=self.source();self.store.save_source(req);self.store.save(self.note())
        self.store.save_source({**req,'status':'deleted','revision':1,'operation_id':'delete'})
        state=self.store.state();self.assertEqual(state['notes'][0]['source_id'],'source');self.assertEqual(state['sources'][0]['body'],req['body'])
        with self.assertRaises(Problem):self.store.save_source({**req,'revision':2,'operation_id':'restore'})
    def test_draft_reopen_retry_conflict_and_explicit_discard(self):
        req={'id':'draft','revision':0,'payload':self.note(),'operation_id':'draft-save'}
        a=self.store.draft(req);self.assertEqual(a,self.store.draft(req))
        self.assertEqual(Store(self.path,ROOT/'app/static').state()['drafts'][0]['payload']['body'],'متن بدنه')
        with self.assertRaises(Problem):self.store.draft({**req,'operation_id':'stale'})
        self.store.discard_draft({'id':'draft','revision':1,'operation_id':'discard'})
        self.assertEqual(self.store.state()['drafts'],[])
    def test_invalid_reference_is_atomic(self):
        with self.assertRaises(Problem):self.store.save(self.note())
        self.assertEqual(self.store.state()['notes'],[])
        with self.store.connect() as c:self.assertEqual(c.execute('SELECT count(*) FROM note_sections').fetchone()[0],0)
    def legacy(self,path):
        old=BaseStore(path,ROOT/'app/static')
        with old.connect() as c:
            c.execute('INSERT INTO notes VALUES(?,?,?,?,?,?)',('old','قدیمی','متن عینی\n**خام**',7,'2026-11-07',''))
            c.execute('INSERT INTO sources VALUES(?,?,?,?)',('old-book','کتاب','منبع عینی',47))
        return old
    def test_g0_upgrade_preserves_all_and_old_writer_refuses(self):
        path=self.path/'legacy';self.legacy(path);new=Store(path,ROOT/'app/static');n=new.state()['notes'][0]
        self.assertEqual(n['revision'],7);self.assertEqual(n['body'],'متن عینی\n**خام**');self.assertEqual(new.state()['sources'][0]['page'],47)
        self.assertEqual(Store.version(new.db),5)
    def test_failed_upgrade_rolls_back_schema_and_original_text(self):
        path=self.path/'failure';old=self.legacy(path)
        original=Store.upgrade
        def fail(store,c):original(store,c);raise RuntimeError('simulated interruption before commit')
        with patch.object(Store,'upgrade',fail):
            with self.assertRaises(RuntimeError):Store(path,ROOT/'app/static')
        self.assertEqual(Store.version(old.db),2)
        with old.connect() as c:self.assertEqual(c.execute('SELECT body FROM notes').fetchone()[0],'متن عینی\n**خام**')

if __name__=='__main__':unittest.main()
