import json
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from store import Store,Problem
import catalog
import review

class CatalogTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.base=Path(tmp.name);self.root=self.base/'فایل های شخصی';self.root.mkdir()
        self.s=Store(self.base/'data','.');self.s.seed()
    def cmd(self,action,**kw):
        with self.s.connect() as c:revision=catalog.config(c)['rev']
        return catalog.command(self.s,dict(action=action,revision=revision,operation_id=uuid.uuid4().hex)|kw)
    def preview(self,action,**kw):
        plan=self.cmd(action,**kw);self.cmd(action,confirm=plan['token'],**kw);return plan['plan']
    def config_root(self):self.preview('root',path=str(self.root))
    def table(self,t):
        with self.s.connect() as c:return catalog.rows(c,t)
    def folder(self,name,parent=''):
        self.cmd('folder',name=name,parent=parent);return next(f for f in self.table('folders') if f['parent']==parent and f['name']==name)
    def test_topic_normalization_cycle_and_no_duplication(self):
        self.cmd('topic',id='a',name='خشم');self.cmd('topic',id='b',name='يادگيري',parent='a')
        with self.assertRaises(Problem):self.cmd('topic',name='یادگیری',parent='a')
        with self.assertRaises(Problem):self.cmd('topic',id='a',name='خشم',parent='b')
        for t in ('a','b','a'):self.cmd('topic-link',target='note:note-1',id=t)
        self.assertEqual(len(self.table('membership')),2)
        self.cmd('topic-delete',id='a');self.assertEqual(len(self.s.state()['notes']),2)
    def test_summary_multiple_refs_atomic_and_retry(self):
        self.cmd('topic',id='t',name='مطالعه')
        q=dict(id='t',title='جمع‌بندی',body='متن مشترک',sources=['book-1','book-2'],revision=1,operation_id='one')
        self.cmd('summary',**q);self.cmd('summary',**q)
        self.assertEqual(len(self.table('citations')),2)
        with self.assertRaises(Problem):self.cmd('summary',id='t',title='خطا',body='اصلی',sources=['not-present'])
        self.assertEqual(len(self.s.state()['notes']),3)
    def test_same_source_two_locators_and_reflection(self):
        self.cmd('topic',id='t',name='موضوع');self.cmd('topic-link',id='t',target='note:note-1')
        for loc in ('ص ۱','ص ۲'):self.cmd('citation',target='note:note-1',id='book-1',locator=loc)
        self.cmd('tag',target='note:note-1',name='يادگيري');self.cmd('tag',target='note:note-1',name='یادگیری')
        self.assertEqual(len(self.table('tags')),1)
        review.command(self.s,dict(command='enroll',target='note:note-1',revision=0,operation_id='start'))
        r=review.command(self.s,dict(command='reflect',target='note:note-1',revision=1,operation_id='reflect',answer='برداشت جدا'))
        key='note:'+r['id'];self.assertEqual(len([x for x in self.table('citations') if x['target']==key]),2)
        self.assertTrue(any(x['target']==key for x in self.table('membership')))
    def test_excerpts_content_revision_and_manual(self):
        self.cmd('excerpt',target='note:note-1',body='مکث',content_revision=1,locator='ص ۱')
        with self.assertRaises(Problem):self.cmd('excerpt',target='note:note-1',body='مکث',content_revision=0)
        self.cmd('excerpt',target='source:book-1',manual=True,body='نقل دستی',locator='ص ۱۲')
        self.assertEqual(len(self.table('anchors')),2)
    def test_queue_without_note_and_date(self):
        self.cmd('queue',id='book-1',status='بعداً',priority=2,planned='2027-03-21',reason='مطالعهٔ بعدی')
        self.assertEqual(len(self.s.state()['notes']),2)
        self.assertEqual(Store(self.s.data,'.').state()['catalog']['reading_queue'][0]['planned'],'2027-03-21')
    def test_root_preview_only_and_stale_preview(self):
        plan=self.cmd('root',path=str(self.root));self.assertEqual(self.s.state()['catalog']['root'],'')
        self.cmd('topic',name='موضوع')
        with self.assertRaises(Problem):self.cmd('root',path=str(self.root),confirm=plan['token'])
    def test_folder_paths_and_duplicate_names(self):
        self.config_root();a=self.folder('یک');b=self.folder('دو')
        self.folder('مشترک',a['id']);self.folder('مشترک',b['id'])
        for name in ('CON','x.','../escape','A:B','الف'*249):
            with self.assertRaises(Problem):self.folder(name)
        with self.assertRaises(Problem):self.cmd('move',id=a['id'],name='جدید',parent=a['id'])
    def test_outside_audio_and_junction(self):
        self.config_root();outside=self.base/'outside';outside.mkdir()
        (outside/'example.pdf').write_bytes(b'%PDF-1.4');(self.root/'sound.mp3').write_bytes(b'x')
        for path in ('../outside/example.pdf','sound.mp3',str(outside/'example.pdf')):
            with self.assertRaises(Problem):self.cmd('file',target='source:book-1',path=path)
        junction=self.root/'junction'
        subprocess.run(['cmd','/c','mklink','/J',str(junction),str(outside)],check=True,capture_output=True)
        try:
            with self.assertRaises(Problem):self.cmd('file',target='source:book-1',path='junction/example.pdf')
        finally:junction.rmdir()
    def test_move_collision_and_recovery_after_disk_rename(self):
        self.config_root();f=self.folder('خشم');pdf=self.root/'خشم'/'درس.pdf';pdf.write_bytes(b'%PDF-1.4')
        self.cmd('file',target='source:book-1',path='خشم/درس.pdf');self.cmd('file',target='note:note-1',path='خشم/درس.pdf')
        self.assertEqual(len(self.table('file_refs')),1)
        (self.root/'اشغال').mkdir()
        with self.assertRaises(Problem):self.cmd('move',id=f['id'],parent='',name='اشغال')
        plan=self.cmd('move',id=f['id'],parent='',name='جدید')
        with patch.object(catalog,'recover',side_effect=RuntimeError('power loss after rename')):
            with self.assertRaises(RuntimeError):self.cmd('move',id=f['id'],parent='',name='جدید',confirm=plan['token'])
        self.s=Store(self.s.data,'.');self.assertEqual(self.table('file_refs')[0]['rel'],'جدید/درس.pdf')
        self.assertTrue((self.root/'جدید'/'درس.pdf').exists());self.assertEqual(self.table('folder_intent'),[])
    def test_relink_200_paths_component_boundary(self):
        self.config_root();f=self.folder('خشم');self.folder('خشمگین')
        with self.s.connect() as c:
            for i in range(200):
                name=f'خشم/{i}.txt';(self.root/name).write_text('x')
                c.execute('INSERT INTO file_refs VALUES(?,?)',(str(i),name))
                c.execute('INSERT INTO attached VALUES(?,?)',('source:book-1',str(i)))
            c.execute("INSERT INTO file_refs VALUES('other','خشمگین/1.txt')")
        (self.root/'خشم').rename(self.root/'تازه')
        plan=self.preview('relink',id=f['id'],name='تازه',parent='')
        self.assertEqual(plan['count'],200);refs=self.table('file_refs');self.assertEqual(sum(r['rel'].startswith('تازه/') for r in refs),200)
        self.assertEqual(refs[-1]['rel'],'خشمگین/1.txt')
    def test_missing_file_keeps_note_and_rebind_root(self):
        self.config_root();(self.root/'f.txt').write_text('نمونه')
        self.cmd('file',target='note:note-1',path='f.txt')
        self.root.rename(self.base/'new')
        self.assertFalse(self.s.state()['catalog']['file_refs'][0]['available'])
        self.preview('root',path=str(self.base/'new'))
        self.assertTrue(self.s.state()['catalog']['file_refs'][0]['available'])
    def test_soft_archive_stops_review_and_preserves_note(self):
        review.command(self.s,dict(command='enroll',target='note:note-1',revision=0,operation_id='start'))
        self.cmd('note-status',target='note:note-1',status='archived')
        self.assertEqual(self.table('schedules')[0]['status'],'paused')
        self.assertTrue(any(r['note_id']=='note-1' for r in self.table('note_sections')))
