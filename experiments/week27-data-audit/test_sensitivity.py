import unittest
import numpy as np
from compensation_sensitivity import residual_shift, episodes, full_windows, window_scores
from paired_attacks import scores

class SensitivityTests(unittest.TestCase):
    def test_shift_equation_matches_direct_residual(self):
        d=np.array([10.,50.,100.]);q=d+50.;r=np.array([-70.,-90.,-96.]);model=[-40.,-27.]
        for na in (1.,2.,2.7,4.):
            for cap in (0.,3.,None):
                shift,p=residual_shift(2.7,na,d,q,cap)
                _,actual,_=scores(model,r,d,q,attacker_slope=-10*na,power_limit=cap)
                original_signed=r-(model[0]+model[1]*np.log10(d))
                np.testing.assert_allclose(actual,np.abs(original_signed+shift),atol=1e-12)
    def test_oracle_and_zero_cap_endpoints(self):
        d=np.array([10.,20.]);q=d*2
        shift,power=residual_shift(2.,2.,d,q,None)
        np.testing.assert_allclose(shift,0,atol=1e-12)
        shift,power=residual_shift(2.,3.,d,q,0.)
        np.testing.assert_array_equal(power,[0.,0.])
        np.testing.assert_allclose(shift,20*np.log10(2))
    def test_model_error_sign(self):
        d=np.array([10.]);q=np.array([100.])
        self.assertAlmostEqual(residual_shift(3.,2.,d,q)[0][0],10.)
        self.assertAlmostEqual(residual_shift(2.,3.,d,q)[0][0],-10.)
    def test_episode_count_is_not_packet_count(self):
        result=episodes(np.arange(10)*.2,[False,True,True,True,False,True,True,False,False,False])
        self.assertEqual(result['alarm_packets'],5);self.assertEqual(result['episodes'],2)
        self.assertEqual(result['mean_packets_per_episode'],2.5)
    def test_gap_breaks_an_episode(self):
        result=episodes([0.,.2,5.,5.2],[True]*4)
        self.assertEqual(result['episodes'],2)
        self.assertAlmostEqual(result['longest_episode_span_s'],.2)
    def test_complete_windows_never_bridge_gaps_or_include_partial_end(self):
        t=np.r_[np.arange(0,25.1,.5),np.arange(40,55.1,.5)]
        windows=full_windows(t,10)
        self.assertEqual(len(windows),3)
        self.assertEqual(windows,[(0,20),(20,40),(51,71)])
        self.assertTrue(all(np.max(np.diff(t[a:b]))<=2 for a,b in windows))
    def test_window_statistic_uses_all_scores_not_alarm_flags(self):
        np.testing.assert_allclose(window_scores([1,2,100,3],[(0,3),(3,4)]),[2,3])
    def test_invalid_time_and_physical_parameters_fail(self):
        with self.assertRaises(ValueError):episodes([0.,0.],[True,True])
        with self.assertRaises(ValueError):full_windows([0.,1.],0)
        with self.assertRaises(ValueError):residual_shift(2.,-1.,[10.],[20.])
        with self.assertRaises(ValueError):residual_shift(2.,2.,[10.],[20.],-1)

if __name__=='__main__':unittest.main()
