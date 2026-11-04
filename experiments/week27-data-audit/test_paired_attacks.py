import unittest
import numpy as np
from paired_attacks import claimed_distance, scores, variant_scores, horizontal_distance

class PairedAttackTests(unittest.TestCase):
    def test_exact_compensation_preserves_arbitrary_correlated_residuals(self):
        d=np.linspace(5.,250.,100);q=d+50;noise=np.sin(np.linspace(0,2,100))*5
        model=np.array([-40.,-27.]);r=model[0]+model[1]*np.log10(d)+noise
        original=r.copy();normal,attack,power=scores(model,r,d,q)
        np.testing.assert_allclose(attack,normal,atol=1e-12)
        np.testing.assert_array_equal(r,original)
        self.assertTrue(np.all(power<0))
    def test_bounded_power_leaves_large_distance_change(self):
        model=[-40.,-20.];d=np.array([10.]);q=np.array([100.]);r=np.array([-60.])
        normal,attack,power=scores(model,r,d,q,power_limit=3)
        self.assertAlmostEqual(normal[0],0);self.assertAlmostEqual(attack[0],17);self.assertEqual(power[0],-3)
    def test_mismatched_exponent_does_not_cancel(self):
        model=[-40.,-30.];d=np.array([10.]);q=np.array([100.]);r=np.array([-70.])
        normal,attack,power=scores(model,r,d,q,attacker_slope=-20)
        self.assertAlmostEqual(attack[0],10)
    def test_horizontal_geometry_distinguishes_radial_and_tangential(self):
        d=np.array([5.]);z=np.array([3.])
        outward,ok=claimed_distance(d,z,3,'outward')
        tangent,_=claimed_distance(d,z,3,'tangential')
        self.assertAlmostEqual(outward[0],np.sqrt(58))
        self.assertAlmostEqual(tangent[0],np.sqrt(34))
        self.assertTrue(ok[0])
    def test_inward_crossing_is_deferred_not_wrapped(self):
        d=np.array([5.,10.]);z=np.array([3.,0.])
        claim,mask=claimed_distance(d,z,5,'inward')
        np.testing.assert_array_equal(mask,[False,True]);self.assertEqual(claim[1],5)
    def test_position_only_does_not_modify_measured_rssi(self):
        r=np.array([-70.,-80.]);copy=r.copy()
        normal,attack,power=variant_scores([-40.,-20.],r,np.array([10.,20.]),np.array([20.,40.]),'position_only')
        np.testing.assert_array_equal(r,copy);np.testing.assert_array_equal(power,[0.,0.])
        self.assertTrue(np.all(attack!=normal))
    def test_zero_shift_returns_same_geometry_for_all_directions(self):
        for direction in ('outward','inward','tangential'):
            claim,mask=claimed_distance(np.array([5.]),np.array([3.]),0,direction)
            np.testing.assert_allclose(claim,[5.]);self.assertTrue(mask[0])
    def test_invalid_geometry_and_parameters_fail(self):
        with self.assertRaises(ValueError):horizontal_distance([1.],[2.])
        with self.assertRaises(ValueError):scores([-40.,1.],[-60.],[10.],[20.])
        with self.assertRaises(ValueError):scores([-40.,-20.],[float('nan')],[10.],[20.])
        with self.assertRaises(ValueError):scores([-40.,-20.],[-60.],[10.],[20.],power_limit=-1)

if __name__=='__main__':unittest.main()
