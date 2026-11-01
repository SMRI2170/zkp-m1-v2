import copy
import json
from pathlib import Path
import unittest
import numpy as np
from robustness_suite import (residual_pools,huber_location,corruption_masks,nuisance_estimates,
                              gate_cases,anchor_gate_study,aggregate)


class RobustnessTests(unittest.TestCase):
    def test_empirical_pool_uses_held_out_rows_and_disjoint_sectors(self):
        data={-8:{(1,'B1'):[-70]*50+[-65]*50,(2,'B1'):[-90]*50+[-80]*50}}
        pools,sectors=residual_pools(data,1)
        np.testing.assert_array_equal(pools[0],[5]*50)
        np.testing.assert_array_equal(pools[1],[10]*50)
        self.assertFalse(sectors[0]&sectors[1])
        reverse,_=residual_pools(data,0)
        np.testing.assert_array_equal(reverse[0],pools[1])

    def test_huber_has_bounded_outlier_influence_and_translation_equivariance(self):
        a=np.array([-1.,0.,1.,100.]);b=np.array([-1.,0.,1.,1e6])
        self.assertAlmostEqual(huber_location(a,1.5),huber_location(b,1.5))
        self.assertAlmostEqual(huber_location(a+7,1.5),huber_location(a,1.5)+7)
        with self.assertRaises(ValueError):huber_location(a,0)

    def test_poisoning_masks_are_nested_and_flight_blocks_stay_intact(self):
        for pattern in ['random_rows','whole_flights']:
            small=corruption_masks(np.random.default_rng(4),3,10,10,pattern,.1)
            big=corruption_masks(np.random.default_rng(4),3,10,10,pattern,.3)
            self.assertTrue(np.all(~small|big))
            self.assertAlmostEqual(small.mean(),.1);self.assertAlmostEqual(big.mean(),.3)
            if pattern=='whole_flights':
                for v in big.reshape(3,10,10).sum(axis=2).reshape(-1):self.assertIn(v,[0,10])

    def test_nuisance_estimates_are_finite_and_nonnegative(self):
        rng=np.random.default_rng(8)
        residual=rng.normal(0,6,(30,1,1))+rng.normal(0,2,(30,10,1))+rng.normal(0,4,(30,10,10))
        values=nuisance_estimates(residual)
        self.assertTrue(all(np.isfinite(v) for v in values))
        self.assertTrue(all(v>=0 for v in values[1:]))

    def test_attack_after_anchor_cannot_change_the_anchor(self):
        base=np.arange(6,dtype=float).reshape(2,3);alpha=np.array([1.,4.])
        anchor,query=gate_cases(base,alpha,'step_after8')
        np.testing.assert_array_equal(anchor,base);np.testing.assert_array_equal(query,base+8)
        clone_a,clone_q=gate_cases(base,alpha,'cloned_rid')
        np.testing.assert_array_equal(clone_a-base,np.broadcast_to(np.array([[3.],[-3.]]),(2,3)))

    def test_after_anchor_gate_acceptance_matches_normal(self):
        cfg=json.loads(Path(__file__).with_name('robustness_config.json').read_text())
        cfg=copy.deepcopy(cfg);cfg['fresh_anchor_gate']['calibration_units']=40
        cfg['fresh_anchor_gate']['target_ids']=3;cfg['fresh_anchor_gate']['test_flights']=2
        cfg['fresh_anchor_gate']['query_events_per_flight']=4
        rows=anchor_gate_study(cfg,17)
        for row in rows:
            if row['scenario']=='step_after8' and row['model']=='rid_gated':
                normal=next(r for r in rows if r['flight_sd_db']==row['flight_sd_db'] and r['anchor_count']==row['anchor_count'] and r['model']==row['model'] and r['scenario']=='normal')
                self.assertEqual(row['accepted_units'],normal['accepted_units'])
                self.assertEqual(row['tested'],normal['tested'])

    def test_abstaining_everywhere_does_not_report_zero_error(self):
        row={'seed':1,'flight_sd_db':1,'anchor_count':1,'scenario':'normal','model':'rid_gated',
             'tested':0,'anchor_units':20,'accepted_units':0,'query_total':400,
             'abs_error_sum':0.,'squared_error_sum':0.,'point_wrong30':0}
        result=aggregate('anchor_gate',[row])[0]
        self.assertIsNone(result['mae_m']);self.assertIsNone(result['point_wrong30_rate'])
        self.assertEqual(result['abstain_rate'],1)


if __name__=='__main__':unittest.main()
