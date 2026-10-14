"""Regression checks for scientific scope: warmups, failures, missing data, phase alignment."""
import csv,json,subprocess,sys,tempfile,unittest
from pathlib import Path
SCRIPT=Path(__file__).with_name('collect.py')
class CollectTest(unittest.TestCase):
 def test_failed_trial_not_success_and_missing_memory_not_zero(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);run=root/'runs'/'test';run.mkdir(parents=True);out=root/'out'
   meta=dict(run_id='test',framework='fixture',variant='test',host_class='synthetic fixture',cpu_quota_percent=25,threads=1,binary_sha256='fixture',source_revision='fixture')
   (run/'metadata.json').write_text(json.dumps(meta));(run/'resource.json').write_text(json.dumps({'exit_code':-9,'stop_reason':'timeout'}))
   stream=[{'phase':'collection_protocol','warmup_count':1,'repeat_count':1}, {'phase':'sample','sample_id':0,'warmup':True,'repetition':None,'prove_ms':2,'verify_ms':1}, {'phase':'sample','sample_id':1,'warmup':False,'repetition':0,'prove_ms':3,'verify_ms':1}]
   (run/'benchmark.jsonl').write_text(''.join(json.dumps(s)+'\n' for s in stream));(run/'memory.jsonl').write_text('')
   subprocess.run([sys.executable,str(SCRIPT),'--runs',str(root/'runs'),'--out',str(out)],check=True,capture_output=True)
   result=[json.loads(s) for s in (out/'samples.jsonl').read_text().splitlines()]
   self.assertFalse(result[1]['trial_completed']);self.assertIsNone(result[1]['prove_memory_sampled_peak_bytes']);self.assertEqual(result[1]['witness_timing_scope'],'included_in_prove')
   queue=[json.loads(s) for s in (out/'queue_model_1hz.jsonl').read_text().splitlines()];self.assertEqual(len(queue),1);self.assertFalse(queue[0]['measured_load_test'])
   with (out/'samples.csv').open() as f:flat=list(csv.DictReader(f))
   self.assertEqual(flat[1]['prove_memory_sampled_peak_bytes'],'')
 def test_prove_memory_excludes_setup_and_verify(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);run=root/'runs'/'test';run.mkdir(parents=True);out=root/'out'
   meta=dict(run_id='test',framework='fixture',variant='test',host_class='synthetic fixture',cpu_quota_percent=25,threads=1,binary_sha256='fixture',source_revision='fixture')
   (run/'metadata.json').write_text(json.dumps(meta));(run/'resource.json').write_text(json.dumps({'exit_code':0,'stop_reason':None}))
   stream=[{'phase':'phase_marker','sample_id':0,'stage':'prove_start','wall_time_ns':100},{'phase':'phase_marker','sample_id':0,'stage':'verify_start','wall_time_ns':200},{'phase':'sample','sample_id':0,'warmup':False,'repetition':0,'prove_ms':3,'verify_ms':1},{'phase':'summary','all_verified':True}]
   mem=[{'wall_time_ns':t,'elapsed_s':t,'cgroup_current_bytes':b,'temperature_C':40} for t,b in [(50,1000),(110,20),(160,40),(210,2000)]]
   (run/'benchmark.jsonl').write_text(''.join(json.dumps(s)+'\n' for s in stream));(run/'memory.jsonl').write_text(''.join(json.dumps(s)+'\n' for s in mem))
   subprocess.run([sys.executable,str(SCRIPT),'--runs',str(root/'runs'),'--out',str(out)],check=True,capture_output=True)
   row=json.loads((out/'samples.jsonl').read_text());self.assertEqual(row['prove_memory_sampled_peak_bytes'],40);self.assertEqual(row['prove_memory_time_weighted_mean_bytes'],20);self.assertEqual(row['prove_memory_samples'],2)
 def test_reboot_truncation_is_reported_not_zero_filled(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);run=root/'runs'/'partial';run.mkdir(parents=True);out=root/'out'
   meta=dict(run_id='partial',framework='fixture',variant='test',host_class='synthetic fixture',cpu_quota_percent=25,threads=1,binary_sha256='fixture',source_revision='fixture')
   (run/'metadata.json').write_text(json.dumps(meta));(run/'benchmark.jsonl').write_text('')
   (run/'memory.jsonl').write_text('{"elapsed_s":0,"cgroup_current_bytes":123}\n{"elapsed_s":1,"cgroup_current_bytes":')
   subprocess.run([sys.executable,str(SCRIPT),'--runs',str(root/'runs'),'--out',str(out)],check=True,capture_output=True)
   trial=json.loads((out/'trials.jsonl').read_text());self.assertEqual(trial['status'],'failed_or_partial');self.assertIsNone(trial['exit_code']);self.assertIsNone(trial['whole_unit_peak_bytes'])
   anomalies=json.loads((out/'schema.json').read_text())['parse_anomalies'];self.assertEqual(anomalies[0]['line'],2)
   self.assertTrue((run/'memory.jsonl').read_text().endswith(':'))
if __name__=='__main__':unittest.main()
