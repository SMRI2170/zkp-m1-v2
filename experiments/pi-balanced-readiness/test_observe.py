import unittest
from observe import summarize
class ReadinessTests(unittest.TestCase):
    def test_missing_or_partial_not_ready(self):
        for rows in [[],[dict(ready=True,uptime_s=10)], [dict(ready=True,uptime_s=t) for t in [None,30,60]]]:
            self.assertFalse(summarize(rows)['ready_for_next_preflight'])
    def test_reset_even_ready_flags_cannot_pass(self):
        r=summarize([dict(ready=True,uptime_s=t) for t in [100,130,1]])
        self.assertFalse(r['ready_for_next_preflight']);self.assertIsNone(r['observed_uptime_span_s'])
    def test_missing_guard_is_recorded_and_no_proof_claim(self):
        r=summarize([dict(ready=False,uptime_s=t) for t in [0,30,60]])
        self.assertTrue(r['no_observed_uptime_reset']);self.assertFalse(r['all_ready']);self.assertFalse(r['proof_executed'])
    def test_ready_is_only_a_preflight_observation(self):
        r=summarize([dict(ready=True,uptime_s=t) for t in [100,132,164]])
        self.assertTrue(r['ready_for_next_preflight']);self.assertEqual(r['reboot_cause'],'unknown');self.assertFalse(r['proof_executed'])
if __name__=='__main__':unittest.main()
