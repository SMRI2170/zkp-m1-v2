"""Synthetic clock/alignment fixtures, not real-data evidence."""
import unittest
import numpy as np
from aerpaw21_local import nearest_indices,minimum_covering_span,constant_offset,optimal_grid_offset


class Dataset21Tests(unittest.TestCase):
    def test_nearest_join_matches_matlab_first_tie_and_reuses_values(self):
        reference=np.array([0.,.5,1.,1.5,2.])
        other=np.array([0.,2.])
        np.testing.assert_array_equal(nearest_indices(reference,other),[0,0,0,1,1])
        self.assertEqual(len(set(nearest_indices(reference,other))),2)

    def test_unsorted_or_nonfinite_timestamps_fail_instead_of_silent_sort(self):
        for values in [[1.,0.],[0.,0.],[np.nan,1.],[]]:
            with self.assertRaises(ValueError):nearest_indices([0.,1.],values)

    def test_global_span_is_not_independent_nearest_span(self):
        times=[np.array([0]),np.array([-4,5]),np.array([5])]
        self.assertEqual(minimum_covering_span(times),5)
        # Independent nearest chooses -4 and5; global minimum is 0,5,5.
        picked=[v[nearest_indices([0],v)[0]] for v in times]
        self.assertEqual(max(picked)-min(picked),9)

    def test_disjoint_windows_do_not_become_same_transmission(self):
        self.assertEqual(minimum_covering_span([[0,100],[21,121],[1,101],[2,102],[3,103]]),21)
        with self.assertRaises(ValueError):minimum_covering_span([[0],[]])

    def test_constant_offset_and_rt_fit_are_separate_from_hardware_calibration(self):
        a=np.array([-50.,-60.,-70.]);b=a-3.3
        offset,error=constant_offset(a,b)
        self.assertAlmostEqual(offset,-3.3);self.assertLess(error,1.e-10)
        optimum,rmse,count=optimal_grid_offset(a,b)
        self.assertAlmostEqual(optimum,-3.3);self.assertLess(rmse,1.e-10);self.assertEqual(count,3)
        with self.assertRaises(ValueError):constant_offset(a,b+[0,0,1])

    def test_rt_padding_not_used_as_calibration_target(self):
        optimum,rmse,count=optimal_grid_offset([-10.,-20.,200.],[-11.,-21.,-90.])
        self.assertAlmostEqual(optimum,-1.);self.assertEqual(count,2);self.assertAlmostEqual(rmse,0.)


if __name__=='__main__':unittest.main()
