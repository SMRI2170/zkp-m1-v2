"""Exercise the runner's real exception handler with a live process group.
Hardware/cgroup preflight is not bypassed in the runner; only its cleanup block
is isolated here to simulate a telemetry timeout on the development host.
"""
import ast
import json
import os
from pathlib import Path
import signal
import subprocess
import unittest

class CleanupTest(unittest.TestCase):
    def test_telemetry_timeout_stops_running_group(self):
        tree=ast.parse(Path(__file__).with_name('run_guarded.py').read_text())
        block=next(n for n in ast.walk(tree) if isinstance(n,ast.Try) and n.finalbody)
        block.body=ast.parse("raise subprocess.TimeoutExpired('vcgencmd', 2)").body
        isolated=ast.fix_missing_locations(ast.Module(body=[block],type_ignores=[]))
        process=subprocess.Popen(['sleep','60'],start_new_session=True)
        env=dict(p=process,subprocess=subprocess,os=os,signal=signal,json=json,reason=None)
        try:
            exec(compile(isolated,'runner-cleanup','exec'),env)
            self.assertEqual(env['reason'],'telemetry_error:TimeoutExpired')
            self.assertEqual(process.poll(),-signal.SIGTERM)
            with self.assertRaises(ProcessLookupError): os.killpg(process.pid,0)
        finally:
            if process.poll() is None:
                os.killpg(process.pid,signal.SIGKILL);process.wait()

if __name__=='__main__': unittest.main()
