import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('capture_analysis', Path(__file__).parents[1]/'scripts/analyze_capture.py')
a = importlib.util.module_from_spec(spec);spec.loader.exec_module(a)

class AnalysisTest(unittest.TestCase):
    def row(self, t, source='a', **extra):
        return dict(monotonic_time_us=t, bssid=source, frequency_mhz=2452,
                    cache_stale=False, rid_parse_status='decoded', **extra)
    def test_intervals_never_cross_transmitters(self):
        result = a.analyze([self.row(1_000_000),self.row(2_000_000,'b'),self.row(11_000_000)], [],
                           [dict(name='foreground',start_us=0,end_us=20_000_000)])[0]
        self.assertEqual(result['interval_pairs'],1)
        self.assertEqual(result['update_interval_p95_s'],10)
    def test_empty_phase_is_not_perfect_reception(self):
        r = a.analyze([],[],[dict(name='screen_off',start_us=0,end_us=30_000_000)])[0]
        self.assertEqual(r['max_edge_inclusive_gap_s'],30)
        self.assertIsNone(r['update_interval_median_s'])
        self.assertIsNone(r['pss_max_kib'])
    def test_cache_from_previous_phase_and_invalid_rows(self):
        old=self.row(1);old['cache_stale']=True
        invalid=self.row(12);invalid['rid_parse_status']='invalid'
        r=a.analyze([old, invalid],[],[dict(name='background',start_us=10,end_us=20)])[0]
        self.assertEqual(r['scan_observations'],1)
        self.assertEqual(r['fresh_decoded_observations'],0)
        self.assertEqual(r['invalid_observations'],1)
    def test_boundaries_and_telemetry_coverage(self):
        events=[dict(elapsed_us=10,pss_kib=100,process_cpu_ms=25,duplicate_results=10),
                dict(elapsed_us=19,pss_kib=120,process_cpu_ms=35,duplicate_results=12)]
        r=a.analyze([self.row(10),self.row(20)],events,[dict(name='foreground',start_us=10,end_us=20)])[0]
        self.assertEqual(r['scan_observations'],1)
        self.assertEqual(r['process_cpu_ms_delta'],10)
        self.assertEqual(r['duplicates_counter_delta'],2)
        self.assertEqual(r['pss_max_kib'],120)
    def test_summary_excludes_transmitter(self):
        r=a.analyze([self.row(10,'secret-id')],[],[dict(name='foreground',start_us=0,end_us=20)])
        self.assertNotIn('secret-id',str(r))
    def test_quantile_interpolation(self):
        self.assertAlmostEqual(a.percentile([1,3],.95),2.9)
        self.assertIsNone(a.percentile([],.95))

if __name__=='__main__':unittest.main()
