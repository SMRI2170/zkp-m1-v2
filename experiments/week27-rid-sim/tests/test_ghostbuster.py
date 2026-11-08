"""Numerical algorithm tests; these are synthetic fixtures, not RF evidence."""
import importlib.util
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
HAS_NUMPY=importlib.util.find_spec('numpy') is not None


@unittest.skipUnless(HAS_NUMPY,'Scientific tests run in the separate pinned-dependency CI job')
class GhostBusterTests(unittest.TestCase):
    def test_noise_free_known_power_localizes_without_claim_initialization(self):
        import numpy as np
        from ghostbuster import locate_frames
        r=np.array([[0,0,2],[500,0,2],[500,500,2],[0,500,2],[210,180,8.]])
        p=np.array([[210,220,60.],[320,180,90.]])
        estimate,audit=locate_frames(np.linalg.norm(p[:,None]-r,axis=-1),r)
        self.assertTrue(np.allclose(estimate,p,atol=1.e-6))
        self.assertEqual(audit['subset_count'],5)
        self.assertTrue(audit['frame_stationary'].all())

    def test_single_receiver_equation6_and_equidistant_failure(self):
        import numpy as np
        from ghostbuster import window_scores
        receiver=np.array([[0,0,2.]])
        rss=np.full((1,5,1),-60.) # intercept -20, n2 -> 100m
        a=np.tile([100.,0.,2.],(1,5,1));b=np.tile([0.,100.,2.],(1,5,1))
        sa,_=window_scores(rss,a,receiver,-20.,2.)
        sb,_=window_scores(rss,b,receiver,-20.,2.)
        self.assertAlmostEqual(sa[0],0.)
        self.assertAlmostEqual(sb[0],0.) # 141m position change, equal range.

    def test_power_compensation_cancels_for_one_receiver_before_quantization(self):
        import numpy as np
        from ghostbuster import ranges_from_rss
        d=80.;q=180.;n=1.35;intercept=-38.07
        delta=10*n*np.log10(d/q)
        received=intercept-10*n*np.log10(d)+delta
        self.assertAlmostEqual(ranges_from_rss(received,intercept,n),q,places=9)

    def test_window_median_is_over_position_errors_and_missing_is_und(self):
        import numpy as np
        from ghostbuster import window_scores
        receiver=np.array([[0,0,2.]])
        rss=np.full((2,5,1),-60.)
        claim=np.tile([100.,0.,2.],(2,5,1))
        claim[0,0]=[10000,0,2]
        rss[1,0,0]=np.nan
        scores,_=window_scores(rss,claim,receiver,-20.,2.)
        self.assertEqual(scores[0],0.) # one outlier cannot change median of5
        self.assertTrue(np.isnan(scores[1]))

    def test_threshold_uses_normal_calibration_only_and_distinguishes_max(self):
        import numpy as np
        from ghostbuster import normal_threshold
        a=np.arange(100,dtype=float)
        self.assertEqual(normal_threshold(a,'max_normal','calibrate_normal'),99.)
        self.assertEqual(normal_threshold(a,'q95_normal','calibrate_normal'),95.)
        with self.assertRaises(ValueError):normal_threshold(a,'max_normal','attack')

    def test_nlse_agrees_with_scipy_reference_objective(self):
        if importlib.util.find_spec('scipy') is None:self.skipTest('SciPy needed for reference solver')
        import numpy as np
        from scipy.optimize import least_squares
        from ghostbuster import locate_frames
        r=np.array([[0,0,2],[500,0,2],[500,500,2],[0,500,2.]])
        p=np.array([210,220,60.]);d=np.linalg.norm(p-r,axis=-1)+[2,-3,1,4]
        estimate,audit=locate_frames(d[None],r)
        oracle=least_squares(lambda x:np.linalg.norm(x-r,axis=1)-d,[250,250,60],
                             bounds=([-2000,-2000,2.001],[2500,2500,2000]),xtol=1.e-12,gtol=1.e-12,ftol=1.e-12)
        self.assertAlmostEqual(float(((np.linalg.norm(estimate[0]-r,axis=1)-d)**2).sum()),2*oracle.cost,places=7)
        self.assertTrue(audit['frame_stationary'][0])

    def test_collinear_and_incomplete_inputs_are_not_called_localizations(self):
        import numpy as np
        from ghostbuster import locate_frames
        with self.assertRaises(ValueError):locate_frames(np.ones((1,4)),np.c_[np.arange(4),np.zeros(4),np.zeros(4)])
        with self.assertRaises(ValueError):locate_frames(np.array([[np.nan]*4]),np.zeros((4,3)))

    def test_noisy_boundary_termination_matches_reference_cost(self):
        if importlib.util.find_spec('scipy') is None:self.skipTest('SciPy reference required')
        import numpy as np
        from scipy.optimize import least_squares
        from ghostbuster import _lm
        r=np.array([[0,0,2],[500,0,2],[500,500,2],[210,180,8.]])
        rng=np.random.default_rng(707)
        points=np.broadcast_to(r,(20,4,3)).copy()
        d=np.linalg.norm(np.array([210,220,60])-r,axis=1)[None,:]*10**(rng.normal(0,3.5,(20,4))/13.5)
        starts=points.mean(axis=1);starts[:,2]=60
        estimate,cost,ok=_lm(points,d,starts,200)
        for i in np.flatnonzero(ok):
            reference=least_squares(lambda x:np.linalg.norm(x-r,axis=1)-d[i],estimate[i],
                                    bounds=([-2000,-2000,2.001],[2500,2500,2000]),
                                    max_nfev=500,ftol=1e-12,xtol=1e-12,gtol=1e-10)
            self.assertLessEqual(abs(cost[i]-2*reference.cost),1.e-6*(1+cost[i]))
        self.assertGreaterEqual(ok.sum(),18)


if __name__=='__main__':unittest.main()
