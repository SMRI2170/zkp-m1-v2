import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from analyze_claim_distance_rssi import retained,summarize


class ClaimDistanceTests(unittest.TestCase):
    def row(self,**changes):
        return dict(dict(quality='ELIGIBLE_TIME_POSITION',claimed_horizontal_distance_m='20',accuracy_m='5',rssi_dbm='-60'),**changes)

    def test_quality_gate_does_not_admit_close_uncertain_fixes(self):
        self.assertTrue(retained(self.row()))
        self.assertFalse(retained(self.row(claimed_horizontal_distance_m='10')))
        self.assertFalse(retained(self.row(quality='STALE_WIFI_OBSERVATION')))
        self.assertFalse(retained(self.row(claimed_horizontal_distance_m='0')))

    def test_missing_nonfinite_values_stay_held(self):
        for field in ['claimed_horizontal_distance_m','accuracy_m','rssi_dbm']:
            for value in ['',None,'nan','inf']:
                self.assertFalse(retained(self.row(**{field:value})))

    def test_empty_bins_and_distribution_not_confidence_intervals(self):
        self.assertEqual(summarize([]),{'n':0})
        s=summarize([self.row(rssi_dbm=str(x)) for x in [-80,-60,-40]])
        self.assertEqual(s['n'],3);self.assertEqual(s['rssi_median_dbm'],-60)
        self.assertEqual(s['rssi_min_dbm'],-80)


if __name__=='__main__':unittest.main()
