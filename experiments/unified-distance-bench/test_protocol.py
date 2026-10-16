import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import build
from protocol import schedule, validate_samples, stats
from collect import collect_run, weighted_memory

class EvidenceTests(unittest.TestCase):
    def samples(self):
        return [{**x,'verified':True,'prove_ms':10.,'verify_ms':1.,'proof_bytes':164} for x in schedule()]
    def test_balanced_and_missing_not_zero(self):
        self.assertTrue(validate_samples(self.samples(),True))
        self.assertFalse(validate_samples(self.samples()[:-1]))
        self.assertIsNone(stats([])['mean'])
        self.assertIsNone(stats([1])['sd'])
    def test_duplicate_case_and_boolean_confusion_rejected(self):
        for key,value in [('case_id',0),('warmup',0),('repetition',False)]:
            rows=self.samples();rows[8][key]=value
            with self.assertRaises(ValueError):validate_samples(rows)
    def test_invalid_duration_and_false_proof_rejected(self):
        for key,value in [('prove_ms',float('nan')),('verify_ms',-1),('verified',False)]:
            rows=self.samples();rows[0][key]=value
            with self.assertRaises(ValueError):validate_samples(rows)
    def test_old_runs_cannot_be_imported_as_balanced(self):
        with self.assertRaises(ValueError):validate_samples([{'case_id':i,'verified':True,'prove_ms':1,'verify_ms':1} for i in range(7)])
    def test_resource_and_summary_required_for_completion(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)
            meta=dict(run_id='test',framework='arkworks',host_class='Pi4',cpu_quota_percent=25,threads=1,flow_scope='prove+verify',proof_encoding='native',protocol='distance-u16-balanced-v1',binary_sha256='test-only',build_metadata={})
            (p/'metadata.json').write_text(json.dumps(meta))
            (p/'memory.jsonl').write_text('\n'.join(json.dumps(dict(elapsed_s=t,cgroup_current_bytes=123)) for t in [0,1]))
            rows=self.samples()+[dict(phase='summary',samples=21,warmups=7,protocol=meta['protocol'],all_verified=True)]
            for x in rows[:-1]:x['phase']='sample'
            (p/'benchmark.jsonl').write_text('\n'.join(map(json.dumps,rows)))
            self.assertEqual(collect_run(p)[0]['status'],'partial')
            res=dict(exit_code=0,stop_reason=None,memory_events_before={'oom_kill':0},memory_events_after={'oom_kill':0},sampled_swap_peak_bytes=0,cpu_quota_percent=25,threads=1,benchmark_cpu_affinity=[0],throttle_samples=['0x50000'])
            (p/'resource.json').write_text(json.dumps(res))
            self.assertEqual(collect_run(p)[0]['status'],'completed')
            res['stop_reason']='timeout';(p/'resource.json').write_text(json.dumps(res))
            self.assertEqual(collect_run(p)[0]['status'],'partial')
    def test_time_weighted_memory(self):
        self.assertEqual(weighted_memory([dict(elapsed_s=0,cgroup_current_bytes=10),dict(elapsed_s=1,cgroup_current_bytes=20),dict(elapsed_s=4,cgroup_current_bytes=0)]),17.5)
    def test_failed_preflight_cannot_start_systemd(self):
        import launch
        import subprocess
        import hashlib
        import sys
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);binary=root/'binary';binary.write_bytes(b'test binary')
            sha=hashlib.sha256(binary.read_bytes()).hexdigest()
            metadata=root/'build.json';metadata.write_text(json.dumps(dict(protocol='distance-u16-balanced-v1',target='aarch64-unknown-linux-musl',framework='arkworks',binary_sha256=sha)))
            for name in ['run_guarded_evaluation.py','preflight.py']:(root/name).write_bytes(b'test binary')
            argv=['launch','--run-id','test','--binary',str(binary),'--build-metadata',str(metadata),'--cache',str(root)]
            with patch.object(sys,'argv',argv),patch.object(launch.os,'uname',return_value=SimpleNamespace(machine='aarch64')),patch.object(launch.os,'geteuid',return_value=1000),patch.object(launch,'RUNNER_SHA',sha),patch.object(launch,'PREFLIGHT_SHA',sha),patch.object(launch.subprocess,'check_output',return_value=''),patch.object(launch.subprocess,'run',side_effect=subprocess.CalledProcessError(1,['preflight'])) as run:
                with self.assertRaises(subprocess.CalledProcessError):launch.main()
                self.assertEqual(run.call_count,1)
                self.assertIn('preflight.py',run.call_args.args[0][1])
                self.assertNotIn('sudo',run.call_args.args[0])

    def test_all_renderers_preserve_circuit_prefix_and_negative_checks(self):
        for name in build.FRAMEWORKS:
            with self.subTest(name=name),tempfile.TemporaryDirectory() as td:
                p=Path(td)/name
                with patch.object(build.subprocess,'run'):
                    build.render(name,p)
                original=next(v for k,v in build.source_info(name).items() if k in ('main.go','src/main.rs')).read_text()
                rendered=(p/('main.go' if name=='gnark' else 'src/main.rs')).read_text()
                # All circuit and negative-test code must survive; only loop/metadata change.
                marker='for i := -1; i < 20; i++ {' if name=='gnark' else 'for (i, a) in CASES.iter().enumerate() {'
                self.assertEqual(original.split(marker)[0],rendered.split('for i := -7;' if name=='gnark' else 'for sample_id in 0..28')[0])
                self.assertIn('tampered_proof_rejected',rendered)
                self.assertIn('distance-u16-balanced-v1',rendered)

if __name__=='__main__':unittest.main()
