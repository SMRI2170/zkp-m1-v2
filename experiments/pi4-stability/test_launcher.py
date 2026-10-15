"""Verify a failed preflight cannot launch systemd or the prover."""
import hashlib
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('launcher',Path(__file__).with_name('launch_workload.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class LauncherTests(unittest.TestCase):
    def test_preflight_failure_prevents_sudo(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for name in ['run_guarded_evaluation.py','week24-observation-workload-queue-v1']:
                (root/name).write_bytes(b'fixture')
            digest=hashlib.sha256(b'fixture').hexdigest()
            with patch.object(m,'RUNNER_SHA256',digest),patch.object(m,'BINARY_SHA256',digest), \
                 patch.object(m.os,'uname') as uname,patch.object(m.os,'geteuid',return_value=1000), \
                 patch.object(m.sys,'argv',['launcher','--run-id','test','--count','4','--cache',d]), \
                 patch.object(m.subprocess,'run',side_effect=subprocess.CalledProcessError(1,['preflight'])) as run:
                uname.return_value.machine='aarch64'
                with self.assertRaises(subprocess.CalledProcessError):m.main()
                self.assertEqual(run.call_count,1)
                self.assertIn('preflight.py',run.call_args.args[0][1])
                self.assertTrue(run.call_args.kwargs['check'])

if __name__=='__main__':unittest.main()
