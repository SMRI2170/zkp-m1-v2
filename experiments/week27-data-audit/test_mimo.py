import unittest
import numpy as np
from audit_mimo import channel_gain_db, nearest_time, consolidate_telemetry, SYMBOL_BYTES
class MimoTests(unittest.TestCase):
    def test_exact_channel_power(self):
        payload=np.full(SYMBOL_BYTES//2,256,dtype='>i2').tobytes()
        self.assertAlmostEqual(channel_gain_db(payload),10*np.log10(12800))
    def test_high_values_do_not_overflow(self):
        payload=np.full(SYMBOL_BYTES//2,32767,dtype='>i2').tobytes()
        self.assertTrue(np.isfinite(channel_gain_db(payload)))
    def test_incomplete_and_zero_rejected(self):
        for payload in (b'\x00',b'\x00'*SYMBOL_BYTES):
            with self.assertRaises(ValueError):channel_gain_db(payload)
    def test_join_never_extrapolates_or_crosses_gap(self):
        times=np.array([0.,.05,1.])
        self.assertIsNone(nearest_time(times,-.01))
        self.assertIsNone(nearest_time(times,1.01))
        self.assertIsNone(nearest_time(times,.5))
        self.assertEqual(nearest_time(times,.04),1)
    def test_duplicate_conflicts_are_quarantined(self):
        times=np.array([0.,0.,1.,1.,2.]);xyz=np.array([[1.,2.,3.],[1.,2.,3.],[4.,5.,6.],[4.,5.,6.01],[7.,8.,9.]])
        kept,pos,conflicts,redundant=consolidate_telemetry(times,xyz)
        np.testing.assert_array_equal(kept,[0.,2.])
        np.testing.assert_array_equal(conflicts,[1.])
        self.assertEqual(redundant,1)
    def test_backward_and_nonfinite_telemetry_rejected(self):
        for times,xyz in [(np.array([1.,0.]),np.zeros((2,3))),(np.array([0.,1.]),np.full((2,3),np.nan))]:
            with self.assertRaises(ValueError):consolidate_telemetry(times,xyz)
if __name__=='__main__':unittest.main()
