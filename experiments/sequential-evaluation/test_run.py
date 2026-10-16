import csv,json,os
from pathlib import Path
import subprocess,sys,tempfile,unittest
import run

class SequentialTests(unittest.TestCase):
 def execute(self,steps):
  p=tempfile.TemporaryDirectory();self.addCleanup(p.cleanup);job=Path(p.name)
  (job/'private').mkdir();(job/'plan.json').write_text(json.dumps({'steps':steps}))
  state={'tag':'test','status':'queued','steps':[{'id':s['id'],'status':'pending'} for s in steps]}
  run.write_state(job,state);run.work(job)
  return job,json.loads((job/'status.json').read_text())
 def test_failed_step_blocks_dependent_but_collection_continues(self):
  argv=[sys.executable,'-c','raise SystemExit(1)']
  steps=[dict(id='fail',argv=argv),dict(id='dependent',argv=[sys.executable,'-c','raise Exception("must not run")'],needs=['fail']),dict(id='collect',argv=[sys.executable,'-c','pass'],needs=['dependent'],always=True)]
  job,state=self.execute(steps)
  self.assertEqual([s['status'] for s in state['steps']],['failed','blocked','completed'])
  self.assertEqual(state['status'],'partial')
  with (job/'results.csv').open() as f:rows=list(csv.DictReader(f))
  self.assertEqual(rows[1]['exit_code'],'')
 def test_timeout_stops_child_and_keeps_json_csv(self):
  job,state=self.execute([dict(id='timeout',argv=[sys.executable,'-c','import time;time.sleep(20)'],timeout_s=.1)])
  self.assertEqual(state['steps'][0]['status'],'timed_out');self.assertTrue((job/'results.csv').exists())
 def test_no_repeat_of_interrupted_remote_step(self):
  with tempfile.TemporaryDirectory() as td:
   job=Path(td);(job/'private').mkdir();(job/'plan.json').write_text(json.dumps({'steps':[dict(id='remote',argv=[sys.executable,'-c','raise Exception()'])]}))
   run.write_state(job,{'steps':[dict(id='remote',status='running')]});run.work(job)
   self.assertEqual(json.loads((job/'status.json').read_text())['steps'][0]['status'],'interrupted')
 def test_bad_plan_rejected(self):
  with self.assertRaises(ValueError):run.validate({'steps':[dict(id='x',needs=['later'],argv=['true'])]})
 def test_pending_capability_is_not_a_measurement_failure(self):
  _,state=self.execute([dict(id='unsupported',argv=[sys.executable,'-c','raise SystemExit(4)'],exit_status={'4':'unsupported'})])
  self.assertEqual(state['steps'][0]['status'],'unsupported')
 def test_ci_review_collects_each_commit_and_logs(self):
  import ci
  from types import SimpleNamespace
  from unittest.mock import patch
  with tempfile.TemporaryDirectory() as td:
   job=Path(td);(job/'private').mkdir()
   (job/'status.json').write_text(json.dumps({'source_commit':'head'}))
   (job/'plan.json').write_text(json.dumps({'related_ci_commits':['parent']}))
   def command(argv,**kwargs):
    if argv[2]=='list':
     sha=argv[argv.index('--commit')+1]
     return SimpleNamespace(returncode=0,stdout=json.dumps([dict(databaseId=sha,name='test',status='completed',conclusion='success',url='test-only',headSha=sha)]))
    kwargs['stdout'].write('test log, no live CI');return SimpleNamespace(returncode=0)
   with patch.object(sys,'argv',['ci','--job',str(job)]),patch.object(ci.subprocess,'run',side_effect=command):self.assertEqual(ci.main(),0)
   self.assertEqual(len(json.loads((job/'ci-results.json').read_text())['runs']),2)
   self.assertTrue((job/'private/ci-parent.log').exists())
 def test_guard_restore_preserves_partial_and_mismatched_state(self):
  from restore import decision,INSTALLER,WATCHDOG
  self.assertEqual(decision(dict(installer_sha256=INSTALLER,watchdog_sha256=WATCHDOG,runtime_paths_present=[])),'install_existing_guard')
  self.assertEqual(decision(dict(installer_sha256=INSTALLER,watchdog_sha256=WATCHDOG,runtime_paths_present=['existing'])),'blocked_existing_state_requires_inspection')
  self.assertEqual(decision(dict(installer_sha256='wrong',watchdog_sha256=WATCHDOG,runtime_paths_present=[])),'blocked_source_mismatch')
 def test_real_plan_is_valid(self):
  plan=json.loads(Path(run.__file__).with_name('plan.json').read_text());run.validate(plan)
  self.assertEqual(sum(s['kind']=='measurement' for s in plan['steps']),8)
  self.assertEqual(sum(s['kind']=='capability' for s in plan['steps']),8)
if __name__=='__main__':unittest.main()
