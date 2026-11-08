import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
from store import Store, Problem, normalized, sync_risks
from main import Application

class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='G0 آزمون ')
        self.data=Path(self.temp.name)
        self.store=Store(self.data,ROOT/'app/static')
    def tearDown(self):self.temp.cleanup()
    def note(self,**kwargs):
        return dict(id='test-note',title='برداشت من',body='یادگیری می‌تواند بهتر شود.\n# متن **خام**\nEnglish https://example.org/a?b=1',due='2026-11-07',at_utc='2026-11-06T23:30:00Z',revision=0,operation_id='op-1',**kwargs)
    def test_initial_empty_explicit_seed_and_no_duplicate(self):
        self.assertEqual(self.store.state()['notes'],[])
        self.store.seed();self.assertEqual(len(self.store.state()['sources']),2)
        self.assertEqual(len(self.store.state()['notes']),2)
        with self.assertRaises(Problem):self.store.seed()
        self.assertFalse((self.data/'backups').exists())
    def test_roundtrip_unicode_date_and_instant(self):
        n=self.note();self.store.save(n)
        reopened=Store(self.data,ROOT/'app/static').state()['notes'][0]
        for k in ['body','title','due','at_utc']:self.assertEqual(reopened[k],n[k])
    def test_retry_after_lost_response_is_one_revision(self):
        n=self.note();a=self.store.save(n);b=self.store.save(n)
        self.assertEqual(a,b);self.assertEqual(b['revision'],1)
        with self.store.connect() as c:self.assertEqual(c.execute('SELECT count(*) FROM operations').fetchone()[0],1)
    def test_same_operation_different_text_rejected(self):
        n=self.note();self.store.save(n);n['body']='متن متفاوت'
        with self.assertRaises(Problem) as cm:self.store.save(n)
        self.assertEqual(cm.exception.status,409)
        self.assertNotEqual(self.store.state()['notes'][0]['body'],n['body'])
    def test_two_tabs_no_silent_overwrite(self):
        n=self.note();self.store.save(n)
        a={**n,'revision':1,'operation_id':'op-2','body':'نسخه اول'}
        b={**a,'operation_id':'op-3','body':'نسخه دوم'}
        self.store.save(a)
        with self.assertRaises(Problem):self.store.save(b)
        self.assertEqual(self.store.state()['notes'][0]['body'],'نسخه اول')
        b.update(id='separate',revision=0,operation_id='op-4');self.store.save(b)
        self.assertEqual(len(self.store.state()['notes']),2)
    def test_failed_validation_leaves_old_data(self):
        n=self.note();self.store.save(n)
        for update in [{'body':''},{'due':'2026-02-31'},{'at_utc':'2026-11-07T12:00:00'},{'title':'x'*251}]:
            with self.assertRaises(Problem):self.store.save({**n,**update,'revision':1,'operation_id':'invalid'})
        self.assertEqual(self.store.state()['notes'][0]['revision'],1)
    def test_search_normalization_does_not_change_source(self):
        text='يادگيري كافي ۱۲۳ ١٢٣ می\u200cتواند \u200fآرام باشد'
        n={**self.note(),'body':text};self.store.save(n)
        self.assertIn('یادگیری کافی 123 123 می تواند',normalized(text))
        self.assertEqual(self.store.state()['notes'][0]['body'],text)
    def test_future_schema_rejected_without_byte_changes(self):
        with self.store.connect() as c:c.execute('PRAGMA user_version=99')
        before=self.store.db.read_bytes()
        with self.assertRaises(Problem):Store(self.data,ROOT/'app/static')
        self.assertEqual(before,self.store.db.read_bytes())
    def test_corrupt_database_not_overwritten(self):
        self.store.db.write_bytes(b'corrupt synthetic database')
        before=self.store.db.read_bytes()
        with self.assertRaises(Problem):Store(self.data,ROOT/'app/static')
        self.assertEqual(before,self.store.db.read_bytes())
    def test_removed_database_not_recreated_during_save(self):
        self.store.db.unlink()
        with self.assertRaises(sqlite3.Error):self.store.save(self.note())
        self.assertFalse(self.store.db.exists())
    def test_transaction_interruption_keeps_committed_text(self):
        self.store.save(self.note())
        code="import sqlite3,sys,os;c=sqlite3.connect(sys.argv[1]);c.execute('BEGIN IMMEDIATE');c.execute(\"UPDATE note_sections SET content_text='uncommitted'\");os._exit(23)"
        result=subprocess.run([sys.executable,'-c',code,str(self.store.db)],capture_output=True)
        self.assertEqual(result.returncode,23)
        self.assertEqual(self.store.state()['notes'][0]['body'],self.note()['body'])
    def test_database_locked_error_preserves_text(self):
        self.store.save(self.note())
        c=sqlite3.connect(self.store.db);c.execute('BEGIN EXCLUSIVE')
        try:
            with self.assertRaises(sqlite3.OperationalError):self.store.save({**self.note(),'operation_id':'op-2','revision':1})
        finally:c.rollback();c.close()
        self.assertEqual(self.store.state()['notes'][0]['revision'],1)
    def test_sync_recognition_env_and_names_not_documents(self):
        with patch.dict(os.environ,{'OneDrive':str(self.data/'mapped-sync')}):
            self.assertTrue(sync_risks(self.data/'mapped-sync'/'data'))
            self.assertTrue(sync_risks(self.data/'Dropbox'/'data'))
            self.assertFalse(sync_risks(self.data/'Documents'/'data'))
    def test_shutdown_refuses_dirty_other_tab(self):
        a=Application(self.data);a.action('heartbeat',{'tab':'one','dirty':True})
        with self.assertRaises(Problem):a.action('shutdown',{})
        a.action('heartbeat',{'tab':'one','dirty':False});self.assertEqual(a.action('shutdown',{}),{'ok':True})
    def test_deferred_routes_absent(self):
        a=Application(self.data)
        for route in ['backup','restore','audio','seed-media','library']:
            with self.assertRaises(Problem) as cm:a.action(route,{})
            self.assertEqual(cm.exception.status,404)

if __name__=='__main__':unittest.main(verbosity=2)
