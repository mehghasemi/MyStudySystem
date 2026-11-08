import sys,tempfile,unittest
from pathlib import Path
from datetime import datetime
from unittest.mock import patch
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from store import Store,Problem
import review

class ReviewTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.s=Store(tmp.name,'.');self.s.seed();self.target='note:note-1'
        fixed=patch('review.day',return_value='2026-11-07');fixed.start();self.addCleanup(fixed.stop)
    def cmd(self,action,**kw):
        rows=self.s.state()['review']['rows']
        rev=next((r['rev'] for r in rows if r['target']==self.target),0)
        return review.command(self.s,dict(command=action,target=self.target,revision=rev,operation_id=str(uuid4()),**{})|kw)
    def grade(self,g='good',**kw):
        a=self.cmd('start')
        return self.cmd('grade',attempt=a['id'],draft_revision=a['rev'],answer='جواب قبلی',grade=g,**kw)
    def test_steps_proposal_and_manual(self):
        self.cmd('enroll');self.assertEqual(self.grade()['due'],'2026-11-10')
        self.assertEqual(self.grade('partial')['due'],'2026-11-08')
        self.assertEqual(self.grade('again',due='2026-11-20')['due'],'2026-11-20')
        row=self.s.state()['review']['rows'][0];self.assertEqual((row['step'],row['turn']),(1,4))
    def test_retry_race_undo_history_and_quota(self):
        self.cmd('enroll');a=self.cmd('start')
        q=dict(command='grade',target=self.target,revision=1,attempt=a['id'],draft_revision=0,grade='good',answer='پیشین',operation_id='one')
        r=review.command(self.s,q);self.assertEqual(r,review.command(self.s,q))
        for bad in [dict(operation_id='two'),dict(answer='متفاوت')]:
            with self.assertRaises(Problem):review.command(self.s,q|bad)
        self.assertEqual(self.s.state()['review']['used'],1)
        self.cmd('undo');self.assertEqual(self.s.state()['review']['used'],0)
        self.assertEqual(self.cmd('reveal')['history'][0]['answer'],'پیشین')
        self.assertNotEqual(a['id'],self.cmd('start')['id'])
    def test_draft_persists_and_stale_refused(self):
        self.cmd('enroll');a=self.cmd('start');self.cmd('draft',attempt=a['id'],draft_revision=0,answer='پیش‌نویس')
        self.s=Store(self.s.data,'.');self.assertEqual(self.cmd('start')['answer'],'پیش‌نویس')
        with self.assertRaises(Problem):self.cmd('draft',attempt=a['id'],draft_revision=0,answer='کهنه')
        self.cmd('snooze',due='2026-11-15')
        with self.assertRaises(Problem):self.cmd('grade',revision=1,attempt=a['id'],draft_revision=1,grade='again')
    def test_pause_resume_cancel_no_quota(self):
        self.cmd('enroll',due='2026-11-07',confirm_today=True);self.cmd('pause')
        self.assertFalse(self.s.state()['review']['queue']);self.cmd('resume',confirm_today=True)
        self.assertTrue(self.s.state()['review']['queue']);self.cmd('cancel')
        self.assertEqual(self.s.state()['review']['used'],0)
    def test_dates_and_end(self):
        for d in ['2026-11-06','2026-11-07']:
            with self.assertRaises(Problem):self.cmd('enroll',due=d)
        self.cmd('enroll')
        for _ in range(6):self.grade()
        self.assertEqual(self.s.state()['review']['rows'][0]['status'],'ended')
        self.cmd('undo');self.grade(due='2026-12-07')
        self.assertEqual(self.s.state()['review']['rows'][0]['status'],'active')
    def test_quota_and_boundary(self):
        self.cmd('enroll')
        for _ in range(20):self.grade('again')
        with self.assertRaises(Problem):self.grade()
        self.cmd('undo');self.grade()
        self.assertEqual(self.s.state()['review']['used'],20)
    def test_highlight_and_reflection(self):
        self.target='highlight:hl-1';self.cmd('enroll');self.grade()
        n=self.cmd('reflect',answer='برداشت من');self.cmd('undo')
        self.assertEqual(next(r for r in self.s.state()['notes'] if r['id']==n['id'])['source_id'],'book-1')
    def test_optional_repeat_last(self):
        self.cmd('enroll',repeat_last=True)
        for _ in range(6):self.grade()
        row=self.s.state()['review']['rows'][0]
        self.assertEqual((row['step'],row['status'],row['due']),(6,'active',review.plus('2026-11-07',60)))
    def test_clock(self):
        from review import day
        # Exercise the real clock function outside the fixture.
        self.assertEqual(real_day(datetime(2026,11,7,2,59)),'2026-11-06')
        self.assertEqual(real_day(datetime(2026,11,7,3,0)),'2026-11-07')
real_day=review.day
