import unittest
import numpy as np
from explain_three_results import histogram, metrics, joint_scores

class ExplanationTests(unittest.TestCase):
    def test_threshold_boundary_matches_strict_alarm(self):
        values=np.array([0.,.5,1.,1.000001,1.5,2.,100.])
        counts=histogram(values)
        self.assertEqual(int(counts.sum()),len(values))
        self.assertEqual(int(counts[2:].sum()),int((values>1).sum()))

    def test_missing_events_are_retained_in_emitted_denominator(self):
        m=metrics(1,'synthetic','x',np.array([True,False,True]),np.array([True,True,False]),3)
        self.assertEqual(m['conditional_alarm_rate'],.5)
        self.assertEqual(m['all_event_alarm_rate'],1/3)

    def test_empty_cohort_does_not_become_zero_conditional_error(self):
        m=metrics(1,'synthetic','x',np.array([False]),np.array([True]),1)
        self.assertIsNone(m['conditional_alarm_rate'])

    def test_paired_analysis_requires_both_receptions(self):
        paired,delta=joint_scores({},np.array([True,True,False]),np.array([True,False,True]),np.array([2.,100.,3.]),np.array([2.,0.,500.]))
        np.testing.assert_array_equal(paired,[True,False,False])
        self.assertEqual(delta,0)

if __name__=='__main__': unittest.main()
