import unittest
from analyze_rf_matrix import summarize_samples,number


def sample(stamp=11,rssi=-60,digest='synthetic-match',counter=7,source='fixture-bssid',frequency=2412):
    return dict(monotonic_time_us=None if stamp is None else int(stamp*1e6),rssi_dbm=rssi,
                vendor_content_digest=digest,odid_counter=counter,cache_stale=False,
                rid_parse_status='decoded',bssid=source,frequency_mhz=frequency)


class AnalysisTests(unittest.TestCase):
    def test_old_other_content_missing_rssi_and_duplicate_times_do_not_inflate_rate(self):
        rows=[sample(9),sample(11),sample(11),sample(13),sample(12,digest='other'),sample(14,rssi=None),
              sample(None),sample(14,counter=8),sample(15)]
        s,b=summarize_samples(rows,dict(vendor_content_sha256='synthetic-match',counter=7),
                              dict(started_boottime_s=10,elapsed_s=10))
        self.assertEqual(s['matching_records'],7)
        self.assertEqual(s['other_content_records'],2)
        self.assertEqual(s['current_rssi_updates'],3)
        self.assertEqual(s['interval_count'],2)
        self.assertEqual(s['interval_median_s'],2)
        self.assertEqual(s['matching_missing_rssi'],1)
        self.assertEqual(s['max_observed_silence_s'],5)
        self.assertEqual(b[0]['count'],2)
        self.assertEqual(b[1]['count'],1)

    def test_no_observations_remains_missing_not_perfect_zero_interval(self):
        s,b=summarize_samples([],dict(vendor_content_sha256='synthetic-match',counter=7),
                              dict(started_boottime_s=10,elapsed_s=10))
        self.assertIsNone(s['interval_median_s']);self.assertEqual(s['max_observed_silence_s'],10)
        self.assertTrue(all(row['rssi_median_dbm'] is None and row['count']==0 for row in b))

    def test_different_sources_and_frequencies_are_not_combined(self):
        rows=[sample(11),sample(12,source='other'),sample(13,frequency=2452)]
        s,b=summarize_samples(rows,dict(vendor_content_sha256='synthetic-match',counter=7),
                              dict(started_boottime_s=10,elapsed_s=10))
        self.assertEqual(s['interval_count'],0)
        self.assertEqual(s['current_rssi_updates'],3)

    def test_unavailable_systemd_memory_is_unknown(self):
        for value in ['[not set]',None,str(2**64-1),'unknown']:
            self.assertIsNone(number(value))
        self.assertEqual(number('1024'),1024)

    def test_end_to_end_aggregates_do_not_publish_source_identifiers_or_digests(self):
        import csv
        import json
        from pathlib import Path
        import tempfile
        from analyze_rf_matrix import analyze
        with tempfile.TemporaryDirectory() as d:
            base=Path(d);matrix=base/'matrix';matrix.mkdir();snapshots=base/'snapshots'
            run='20260101T000000.000000Z';folder=snapshots/'b/captures/observer-b'/run
            folder.mkdir(parents=True)
            rows=[sample(11),sample(13),sample(15)]
            (folder/'observations.jsonl').write_text('\n'.join(json.dumps(r) for r in rows)+'\n')
            receipt=dict(vendor_content_sha256='synthetic-match',counter=7,temporary_ap_removed=True)
            condition=dict(kind='matrix',repetition=1,transmitter='a',scope='target',spacing_s=.25,duration_s=10)
            trial=dict(index=0,condition=condition,status='COMPLETED',cleanup_errors=[],tx_receipt_final=receipt,
                       started_at_utc='2026-01-01T00:00:00+00:00',resources=[],
                       receivers={'b':dict(run_id=run,exit_code=0,child_peak_rss_kib=22528,
                           capture=dict(started_boottime_s=10,elapsed_s=10,stopped_reason='duration_complete',
                                        counts=dict(scan_requests=10,scan_accepted=10,scan_failed=0)))})
            (matrix/'plan.json').write_text(json.dumps([condition]))
            (matrix/'trial-00.json').write_text(json.dumps(trial))
            result=analyze(matrix,snapshots,base/'output')
            self.assertEqual(result['completed_trials'],1)
            self.assertEqual(result['total_matching_records'],3)
            self.assertEqual(result['groups'][0]['median_of_run_medians_s'],2)
            public=''.join(p.read_text() for p in (base/'output').iterdir())
            self.assertNotIn('fixture-bssid',public)
            self.assertNotIn('synthetic-match',public)
            self.assertNotIn(run,public)
