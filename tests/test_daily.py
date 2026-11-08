import sys,tempfile,unittest
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from store import Store,Problem
import daily,review
class DailyTests(unittest.TestCase):
 def setUp(self):
  t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);self.s=Store(t.name,'.');self.s.seed()
 def cmd(self,cmd,**kw):
  return daily.command(self.s,dict(command=cmd,operation_id=uuid4().hex)|kw)
 def rv(self,cmd,target='note:note-1',**kw):
  with self.s.connect() as c:r=c.execute('SELECT rev FROM schedules WHERE target=?',(target,)).fetchone()
  return review.command(self.s,dict(command=cmd,target=target,revision=r[0] if r else 0,operation_id=uuid4().hex)|kw)
 def grade(self,**kw):
  a=self.rv('start');return self.rv('grade',attempt=a['id'],draft_revision=a['rev'],grade='good',**kw)
 def change(self,scope,intervals):
  p=dict(scope=scope,intervals=intervals,repeat_last=False,revision=self.s.state()['daily']['config']['rev'])
  plan=self.cmd('preview',**p);self.cmd('policy',**p,token=plan['token']);return plan
 def test_active_policy_clamp_preserves_due_and_old_events(self):
  self.rv('enroll')
  for i in range(3):self.grade()
  old=self.s.state()['review']['rows'][0];plan=self.change('active',[2,4,8]);self.assertEqual(plan['clamped'],1)
  r=self.s.state()['review']['rows'][0];self.assertEqual((r['step'],r['due'],r['turn']),(3,old['due'],4));self.assertFalse(r['undo'])
  with self.assertRaises(Problem):self.rv('undo')
  with self.s.connect() as c:self.assertEqual([r[0] for r in c.execute("SELECT policy_id FROM review_events WHERE command='grade'")],[1,1,1])
 def test_new_only_retains_old_policy_and_undo(self):
  self.rv('enroll');self.grade();self.change('new',[4,9])
  self.rv('undo');self.rv('enroll',target='highlight:hl-1');state=self.s.state()['review']
  self.assertEqual(sorted(x['stages'] for x in state['rows']),[2,6]);self.assertEqual(state['first'],review.plus(state['today'],4))
 def test_stale_preview_and_bad_intervals(self):
  self.rv('enroll');p=dict(scope='active',intervals=[2,5],repeat_last=True,revision=0);preview=self.cmd('preview',**p)
  self.rv('pause')
  with self.assertRaises(Problem):self.cmd('policy',**p,token=preview['token'])
  for bad in ([3,1],[1,1],[],[-1]):
   with self.assertRaises(Problem):self.cmd('preview',**(p|{'intervals':bad}))
 def test_boundary_and_quota_previous_day_stays_fixed(self):
  self.cmd('settings',values={'zone':'UTC','boundary':240,'cap':1},revision=0)
  class Clock(datetime):
   current=datetime(2026,11,8,3,59,tzinfo=timezone.utc)
   @classmethod
   def now(cls,tz=None):return cls.current
  with patch('daily.datetime',Clock):
   self.rv('enroll');self.grade();self.assertEqual(self.s.state()['review']['used'],1)
   with self.assertRaises(Problem):self.grade()
   Clock.current=datetime(2026,11,8,4,0,tzinfo=timezone.utc)
   self.assertEqual(self.s.state()['review']['used'],0);self.assertEqual(self.s.state()['review']['today'],'2026-11-08')
   self.rv('undo');self.assertEqual(self.s.state()['review']['used'],0)
 def test_saved_action_retry_conflict_and_reopen(self):
  a=dict(id='a',note='note-1',description='قدم عملی',due='2026-11-08',status='open',result='',revision=0,operation_id='a-save')
  self.cmd('action',**a);self.cmd('action',**a)
  with self.assertRaises(Problem):self.cmd('action',**(a|{'operation_id':'stale'}))
  self.cmd('action',**(a|dict(revision=1,status='done',result='نتیجه',operation_id='complete')))
  row=Store(self.s.data,'.').state()['daily']['actions'][0];self.assertEqual(row['result'],'نتیجه');self.assertTrue(row['completed'])
 def test_settings_validation_and_real_activity(self):
  for values in [{'cap':0},{'cap':True},{'boundary':1440},{'initial_folder':'invalid'}]:
   with self.assertRaises(Problem):self.cmd('settings',values=values,revision=0)
  self.assertFalse(self.s.state()['daily']['activities'])
  self.cmd('activity',target='note:note-1',minutes=4,rating=3,logged=True);a=self.s.state()['daily']['activities'][0];self.assertEqual((a['kind'],a['minutes'],a['rating']),('logged',4,3))
 def test_section_search_safe_original_and_filter(self):
  self.s.save(dict(id='test',revision=0,title='نمونه',body='متن',sections={'personal':'كـاربرد ١٢٣ <script> خشم'},source_id='book-1',operation_id='save'))
  found=daily.search(self.s,dict(q='کاربرد ۱۲۳',type='book',kind='notes'));self.assertEqual([r['id'] for r in found],['test']);self.assertIn('كـاربرد',found[0]['body'])
  self.assertFalse(daily.search(self.s,dict(q='کاربرد ۱۲۳',review='active')))
 def test_source_tag_and_due_filters(self):
  import catalog
  catalog.command(self.s,dict(action='tag',revision=0,operation_id='tag',name='يادگيري',target='source:book-1'))
  self.assertEqual([r['id'] for r in daily.search(self.s,{'q':'یادگیری','tag':'یادگیری'})],['book-1'])
  self.rv('enroll',due='2030-01-05');self.assertEqual([r['id'] for r in daily.search(self.s,{'q':'','from':'2030-01-01','to':'2030-01-05'})],['note-1'])
 def test_batch_preview_atomicity_and_retry(self):
  q=dict(targets=['note:note-1','highlight:hl-1'],due='2030-01-05')
  plan=self.cmd('batch-preview',**q);self.assertEqual(plan['total'],2);self.assertEqual(self.s.state()['review']['rows'],[])
  commit=dict(**q,token=plan['token'],operation_id='batch-once');self.cmd('batch',**commit);self.cmd('batch',**commit)
  self.assertEqual(len(self.s.state()['review']['rows']),2)
  with self.assertRaises(Problem):self.cmd('batch-preview',targets=['note:note-2','note:missing'],due='2030-01-05')
  self.assertEqual(len(self.s.state()['review']['rows']),2)
 def test_same_day_after_completion_is_explicit_only(self):
  today=self.s.state()['review']['today'];self.rv('enroll',due=today,confirm_today=True)
  self.grade(due=today,confirm_today=True);self.assertEqual(self.s.state()['review']['queue'],[])
  self.rv('undo');self.assertEqual(self.s.state()['review']['queue'],['note:note-1'])
 def test_section_direction_and_search_far_from_start(self):
  self.s.save(dict(id='long',revision=0,title='A',body='متن '*85+'كـاربرد',directions={'body':'rtl'},operation_id='long'))
  st=self.s.state();n=next(x for x in st['notes'] if x['id']=='long')
  self.assertEqual(st['daily']['directions'][n['section_records'][0]['id']],'rtl')
  self.assertIn('كـاربرد',daily.search(self.s,{'q':'کاربرد'})[0]['body'])
