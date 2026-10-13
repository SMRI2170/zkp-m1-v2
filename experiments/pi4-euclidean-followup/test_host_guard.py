"""Check that the soft host monitor terminates a live process and preserves failure evidence."""
import json
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

RUNNER=Path(__file__).with_name('run_host_guarded.py')
class HostGuardTest(unittest.TestCase):
    def test_rss_limit_terminates_command(self):
        real_popen=subprocess.Popen
        children=[]
        def launch(*args,**kwargs):
            child=real_popen(*args,**kwargs);children.append(child);return child
        def telemetry(command,**kwargs):
            if command[0]=='sysctl':return 'vm.swapusage: total = 0M used = 0M free = 0M'
            return f'{children[0].pid} 1 2048\n'
        with tempfile.TemporaryDirectory() as temporary:
            out=Path(temporary)/'run'
            with patch.object(sys,'argv',[str(RUNNER),'--out',str(out),'--rss-max-mib','1','--','sleep','60']), patch('subprocess.Popen',side_effect=launch), patch('subprocess.check_output',side_effect=telemetry):
                with self.assertRaises(SystemExit) as stop:runpy.run_path(str(RUNNER),run_name='__main__')
            self.assertEqual(stop.exception.code,1)
            self.assertIsNotNone(children[0].poll())
            resource=json.loads((out/'resource.json').read_text())
            self.assertEqual(resource['stop_reason'],'process_tree_rss_limit')
            self.assertNotEqual(resource['exit_code'],0)
            self.assertGreater(resource['sampled_process_tree_peak_bytes'],resource['rss_limit_bytes'])

if __name__=='__main__':unittest.main()
