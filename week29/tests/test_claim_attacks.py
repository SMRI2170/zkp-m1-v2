import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from evaluate_claim_attacks import prediction,compensation,changed_distance,split_time,fit


class ClaimAttacksTests(unittest.TestCase):
    def test_matched_power_keeps_the_signed_residual(self):
        for before,after in [(10,30),(30,10),(10,100)]:
            n=2.2;intercept=-30;measured=prediction(before,intercept,n)+3.5
            adjusted=measured+compensation(before,after,n)
            self.assertAlmostEqual(adjusted-prediction(after,intercept,n),3.5)

    def test_distance_changes_and_no_silent_clipping(self):
        self.assertEqual(changed_distance(30,20,'toward'),10)
        self.assertIsNone(changed_distance(20,20,'toward'))
        self.assertEqual(changed_distance(30,20,'away'),50)
        self.assertEqual(changed_distance(3,4,'transverse'),5)
        self.assertEqual(compensation(10,100,2,3),-3)

    def test_temporal_split_embargo_and_no_boot_merging(self):
        rows=[dict(time=i,boot='fixture',distance=i+1,rssi=-i) for i in range(100)]
        train,cal,test=split_time(rows)
        self.assertGreater(cal[0]['time']-train[-1]['time'],10)
        self.assertGreater(test[0]['time']-74,10)
        self.assertFalse(set(x['time'] for x in train)&set(x['time'] for x in test))
        with self.assertRaises(ValueError):split_time(rows+[dict(rows[-1],boot='other')])

    def test_known_model_and_flat_geometry_hold(self):
        rows=[dict(distance=d,rssi=prediction(d,-30,2)) for d in [1,2,5,10]]
        intercept,n=fit(rows)
        self.assertAlmostEqual(intercept,-30);self.assertAlmostEqual(n,2)
        with self.assertRaises(ValueError):fit([dict(distance=1,rssi=-30)]*4)


if __name__=='__main__':unittest.main()
