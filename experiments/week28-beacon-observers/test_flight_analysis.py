import json
from pathlib import Path
import tempfile
import unittest
from analyze_flight_capture import receiver


class FlightAnalysisTests(unittest.TestCase):
    def test_old_duplicate_missing_rssi_and_other_source_are_not_new_updates(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            (p/'events.jsonl').write_text(json.dumps(dict(event='start',started_boottime_s=10))+'\n')
            base=dict(bssid='02:00:00:00:00:01',claimed_uas_ids=['PI-RID-TEST'],
                      cache_stale=False,rssi_dbm=-60,source_annotation=dict(role='onboard_pi'))
            entries=[dict(base,monotonic_time_us=t) for t in [9000000,11000000,11000000,11500000]]
            entries += [dict(base,monotonic_time_us=12000000,rssi_dbm=None),
                        dict(base,monotonic_time_us=12500000,cache_stale=True),
                        dict(base,monotonic_time_us=13000000,bssid='02:00:00:00:00:02')]
            (p/'observations.jsonl').write_text('\n'.join(map(json.dumps,entries)))
            result=receiver(p,dict(tx_mac=base['bssid'],uas_id='PI-RID-TEST'))
            self.assertEqual(result['count'],2)
            self.assertEqual(result['median_interval_s'],.5)
            self.assertNotIn('bssid',result)


if __name__=='__main__':unittest.main()
