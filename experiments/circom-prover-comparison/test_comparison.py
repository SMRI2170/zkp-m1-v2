import json,os,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import prepare
import task
class ComparisonTests(unittest.TestCase):
 def test_relation_schedule_and_negative_checks_preserved(self):
  s=prepare.render();old=(prepare.ROOT/'experiments/balanced-cli/rendered/circom/bench.cjs').read_text()
  self.assertEqual(s[s.index('  // Bypass witness'):],old[old.index('  // Bypass witness'):])
  for marker in ['sample_id<28','sample_id<7','Math.floor((sample_id-7)/7)','phase1_contributed','phase2_contributed','zkey_verified','fieldBytes!==32','negative_verifier_exit_code:1']:
   self.assertIn(marker,s)
  self.assertIn("verifier_backend:'RapidSnark native'",s)
 def test_node_syntax(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'bench.cjs';p.write_text(prepare.render())
   for file in [p,Path(__file__).with_name('snarkjs-prover.cjs')]:subprocess.run(['node','--check',str(file)],check=True,capture_output=True)
 def test_missing_pinned_module_fails(self):
  env={k:v for k,v in os.environ.items() if k!='WEEK24_SNARKJS_ROOT'}
  r=subprocess.run(['node',str(Path(__file__).with_name('snarkjs-prover.cjs'))],env=env,capture_output=True,text=True)
  self.assertEqual(r.returncode,1);self.assertNotIn('witness',r.stderr)
 def test_combined_export_keeps_measurements_and_provenance(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);job=root/'job';job.mkdir();baseline=root/'baseline';baseline.mkdir();data=job/'data';data.mkdir()
   for folder,name in [(baseline,'old'),(data,'circom-snarkjs')]:
    (folder/'summary.json').write_text(json.dumps([dict(framework=name,status='completed',measured_samples=21)]))
    (folder/'samples.jsonl').write_text(json.dumps(dict(framework=name,flow_ms=1))+'\n')
   with patch.object(task.subprocess,'run') as run:task.combine(job,baseline)
   self.assertEqual(len(json.loads((job/'combined-data/summary.json').read_text())),2)
   self.assertEqual(len(json.loads((job/'combined-data/sources.json').read_text())),2)
   self.assertEqual(run.call_count,1)
if __name__=='__main__':unittest.main()
