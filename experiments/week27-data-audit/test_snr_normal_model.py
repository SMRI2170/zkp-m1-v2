import unittest
import numpy as np
from snr_normal_model import fit,predict,scores,log_features,horizontal_ranges,evaluate
from snr_four_station import centered

class SNRNormalModelTests(unittest.TestCase):
    def fixture(self,offset=0.):
        t=np.arange(90.)
        d=np.c_[30+t,150+t*2,250+t*.3,100+t*.7]
        x=log_features(d);bias=np.array([2.,-1.,3.,-4.])
        return dict(t=t,x=x,y=-20*x+bias+offset)
    def test_recovers_shared_slope_and_offsets_from_training_only(self):
        a=self.fixture();m=fit([a],'horizontal_geometry')
        self.assertAlmostEqual(m['fitted_n'],2.)
        np.testing.assert_allclose(predict(m,a['x']),a['y'],atol=1e-10)
        self.assertAlmostEqual(sum(m['station_offsets_db']),0.)
    def test_replication_within_session_does_not_change_equal_session_fit(self):
        a=self.fixture();b=self.fixture();b['y']=b['y']+np.array([1.,2.,-2.,-1.])
        replicated=dict(a,x=np.repeat(a['x'],4,axis=0),y=np.repeat(a['y'],4,axis=0))
        for kind in ['constant','horizontal_geometry']:
            p=fit([a,b],kind);q=fit([replicated,b],kind)
            self.assertAlmostEqual(p['slope_db_per_log10'],q['slope_db_per_log10'])
            # Replicated floating reductions differ around zero by ~1e-15;
            # use an explicit absolute roundoff tolerance, not a skip.
            np.testing.assert_allclose(p['station_offsets_db'],q['station_offsets_db'],atol=1e-12)
    def test_target_data_cannot_change_calibration_threshold(self):
        s=self.fixture();m=fit([s],'constant');a=evaluate(m,s,s)
        target=dict(s,y=s['y']+np.array([100.,-100.,100.,-100.]))
        b=evaluate(m,s,target)
        self.assertEqual(a['threshold_db'],b['threshold_db']);self.assertEqual(b['normal_alarm_rate'],1.)
    def test_log_features_remove_common_range_scaling(self):
        d=np.array([[10.,20.,40.,80.]])
        np.testing.assert_allclose(log_features(d),log_features(d*10),atol=1e-12)
    def test_unidentifiable_geometry_slope_is_rejected(self):
        a=self.fixture();a['x']=np.zeros_like(a['x'])
        with self.assertRaises(ValueError):fit([a],'horizontal_geometry')
    def test_invalid_or_zero_distances_not_silently_clamped(self):
        with self.assertRaises(ValueError):log_features([[0.,1.,2.,3.]])
        with self.assertRaises(ValueError):horizontal_ranges([[1.,2.]],[[1.,2.],[2.,3.],[3.,4.],[4.,5.]])

if __name__=='__main__':unittest.main()
