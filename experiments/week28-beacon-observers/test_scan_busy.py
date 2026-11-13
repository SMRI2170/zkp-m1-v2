import io
import unittest
from unittest.mock import patch
from diagnose_scan_busy import event_kind,result_reason,summarize,Probe
from analyze_scan_busy import analyze


class ScanBusyTests(unittest.TestCase):
    def test_events_are_interface_specific_and_aborts_are_not_completion(self):
        self.assertEqual(event_kind('1.100: wlan0 (phy #0): scan started','wlan0'),'started')
        self.assertEqual(event_kind('1.500: wlan0 (phy #0): scan finished:','wlan0'),'finished')
        self.assertEqual(event_kind('1.500: wlan0 (phy #0): scan aborted:','wlan0'),'aborted')
        self.assertIsNone(event_kind('1.500: wlan1 (phy #0): scan finished:','wlan0'))
        self.assertIsNone(event_kind('1.500: wlan0 (phy #0): connected','wlan0'))

    def test_permission_busy_timeout_and_other_failures_remain_distinct(self):
        self.assertEqual(result_reason(240,'command failed: Device or resource busy (-16)'),'busy')
        self.assertEqual(result_reason(255,'command failed: Operation not permitted (-1)'),'permission')
        self.assertEqual(result_reason(0,''),'accepted')
        self.assertEqual(result_reason(1,'other error'),'driver_rejected')
        s=summarize([dict(kind='request',reason='busy',scan_open_before=True),
                     dict(kind='request',reason='busy',scan_open_before=False),
                     dict(kind='request',reason='permission'),dict(kind='wait',timed_out=True),
                     dict(kind='aborted')])
        self.assertEqual(s['busy'],2);self.assertEqual(s['permission'],1)
        self.assertEqual(s['busy_while_scan_event_open'],1)
        self.assertEqual(s['timeouts'],1);self.assertEqual(s['event_aborts'],1)

    def test_missing_events_do_not_become_success_and_previous_scan_is_ignored(self):
        p=Probe('wlan0',None);p.file=io.StringIO()
        p.events=[dict(kind='finished',elapsed_s=1)]
        self.assertFalse(p.wait_done(dict(tag='test',request_started_s=2),timeout=0))
        self.assertTrue(p.events[-1]['timed_out'])
        p.events.append(dict(kind='aborted',elapsed_s=3))
        self.assertFalse(p.wait_done(dict(tag='test',request_started_s=2)))
        self.assertEqual(p.events[-1]['terminal'],'aborted')

    def test_analysis_rejects_unfinished_experiments_and_separates_denominators(self):
        with self.assertRaises(ValueError):analyze([])
        es=[dict(kind='completed',scenario='two_requesters'),
            dict(kind='request',scenario='broad_probe',tag='broad-0',reason='accepted'),
            dict(kind='request',scenario='broad_probe',tag='during-broad-0',reason='busy')]
        r=analyze(es)['broad_probe']
        self.assertEqual(r['requests'],2)
        self.assertEqual(r['premature_target_requests'],1)
        self.assertEqual(r['premature_target_busy'],1)
        self.assertIsNone(r['broad_completion_median_s'])


if __name__=='__main__':unittest.main()
