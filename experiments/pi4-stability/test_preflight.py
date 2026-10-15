"""Missing guards / telemetry must never turn into a successful preflight."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
spec=importlib.util.spec_from_file_location('preflight',Path(__file__).with_name('preflight.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class PreflightTests(unittest.TestCase):
    def test_missing_runtime_guard_is_reported(self):
        with tempfile.TemporaryDirectory() as d:
            row=m.snapshot(Path(d),lambda args:(1,''))
        self.assertFalse(row['ready'])
        self.assertIsNone(row['watchdog_sha256'])
        self.assertIsNone(row['current_kernel_oom_matches'])
        self.assertFalse(row['checks']['parent_limits'])
        self.assertIsNone(row['ssh_oom_score_adj'])

    def test_reboot_is_not_a_stable_span(self):
        result=m.summarize([{'uptime_s':500,'ready':True},{'uptime_s':5,'ready':True}])
        self.assertFalse(result['no_observed_uptime_reset'])
        self.assertIsNone(result['observed_uptime_span_s'])

    def test_short_observation_keeps_readiness_failures(self):
        result=m.summarize([{'uptime_s':500,'ready':True},{'uptime_s':530,'ready':False}])
        self.assertFalse(result['all_ready'])
        self.assertEqual(result['observed_uptime_span_s'],30)

if __name__=='__main__':unittest.main()
