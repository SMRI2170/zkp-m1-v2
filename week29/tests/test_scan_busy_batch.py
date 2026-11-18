import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from run_scan_busy_batch import plan,summarize

class ScanBusyTests(unittest.TestCase):
    def test_two_rounds_are_counterbalanced_and_controls_are_passive(self):
        p=plan();self.assertEqual(len(p),20)
        a=[(x['strategy'],x['interval_s']) for x in p if x['round']==1]
        b=[(x['strategy'],x['interval_s']) for x in p if x['round']==2]
        self.assertEqual(a,list(reversed(b)));self.assertEqual(p[0]['strategy'],'passive');self.assertEqual(p[-1]['strategy'],'passive')
    def test_old_cache_duplicate_and_unrelated_source_are_not_new_target(self):
        target='PI-RID-SCAN-FIXTURE'
        def row(t,**kw):return dict(dict(claimed_uas_ids=[target],rid_parse_status='decoded',cache_stale=False,monotonic_time_us=t,vendor_content_digest=str(t),rssi_dbm=-50),**kw)
        rows=[row(99),row(100),row(100),row(1000100),row(2000100,cache_stale=True),row(3000100,claimed_uas_ids=['OTHER'])]
        x=summarize(rows,[],target,100)
        self.assertEqual(x['target_new_observations'],2);self.assertEqual(x['target_interval_median_s'],1);self.assertIsNone(x['packet_delivery_rate']);self.assertFalse(x['physical_packet_count_known'])
    def test_busy_and_permission_are_separate_and_passive_denominator_is_unknown(self):
        x=summarize([],[], 'TEST',0);self.assertIsNone(x['busy_fraction'])
        events=[dict(event='scan_request',accepted=True),dict(event='scan_request',accepted=False,failure_reason='busy'),dict(event='scan_request',accepted=False,failure_reason='permission')]
        x=summarize([],events,'TEST',0);self.assertEqual(x['busy'],1);self.assertEqual(x['permission'],1);self.assertAlmostEqual(x['busy_fraction'],1/3)

class ScanEventTests(unittest.TestCase):
    def test_scan_event_duration_ignores_other_interfaces(self):
        from analyze_scan_busy_artifacts import scan_spans
        events='1.0: wlan0 (phy #0): scan started\n1.1: other (phy #0): scan finished\n4.0: wlan0 (phy #0): scan finished\n'
        spans,held=scan_spans(events);self.assertEqual(spans,[(1,4)]);self.assertEqual(held['unclosed_started'],0)
    def test_ambiguous_and_reversed_events_are_reported_not_used(self):
        from analyze_scan_busy_artifacts import scan_spans
        events='2.0: wlan0 (phy #0): scan started\n3.0: wlan0 (phy #0): scan started\n4.0: wlan0 (phy #0): scan finished\n9.0: wlan0 (phy #0): scan started\n8.0: wlan0 (phy #0): scan finished\n'
        spans,held=scan_spans(events);self.assertEqual(spans,[]);self.assertEqual(held['ambiguous_pair'],1);self.assertEqual(held['clock_reversal'],1)


class RestoreReceiverTests(unittest.TestCase):
    def exercise(self,states,stop_code=0):
        from types import SimpleNamespace
        from restore_scan_receiver import restore
        calls=[];iterator=iter(states)
        def run(argv,**kwargs):
            calls.append(argv)
            if argv[1]=='show':return SimpleNamespace(stdout=next(iterator),returncode=0)
            if argv[1]=='stop':return SimpleNamespace(stdout='',returncode=stop_code)
            return SimpleNamespace(stdout='active\n',returncode=0)
        result=restore('zkp-scan-rx-20261119t010203z',runner=run,ap_exists=lambda:False)
        return result,calls
    def test_unloaded_completed_unit_does_not_prevent_normal_restart(self):
        result,calls=self.exercise(['LoadState=not-found\nActiveState=inactive\n'])
        self.assertTrue(result['receiver_active']);self.assertFalse(any(x[1]=='stop' for x in calls))
    def test_unload_race_is_verified_before_accepting_stop_error(self):
        result,_=self.exercise(['LoadState=loaded\nActiveState=inactive\n','LoadState=not-found\nActiveState=inactive\n'],5)
        self.assertTrue(result['receiver_active'])
    def test_active_study_stop_error_is_not_ignored(self):
        with self.assertRaisesRegex(RuntimeError,'stop failed'):
            self.exercise(['LoadState=loaded\nActiveState=active\n','LoadState=loaded\nActiveState=active\n'],1)

if __name__=='__main__':unittest.main()
