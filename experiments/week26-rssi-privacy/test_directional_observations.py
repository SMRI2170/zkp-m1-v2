import json
from pathlib import Path
import unittest
import numpy as np
from directional_observations import (pattern, centered_score, generate, claim,
    observe, calibrate, decide, metrics, counterexamples, indoor_pools)


class DirectionalTests(unittest.TestCase):
    def setUp(self):
        self.cfg=json.loads(Path(__file__).with_name('directional_config.json').read_text())
        self.cfg.update(calibration_flights=10,test_flights=10,events_per_flight=60)
        self.data=generate(self.cfg,71,1)

    def test_common_scalar_power_cancels_but_different_channel_powers_do_not(self):
        raw=np.array([[1.,2.,3.,4.]]);mask=np.ones_like(raw,dtype=bool)
        s=centered_score(raw,np.zeros_like(raw),mask)
        np.testing.assert_allclose(s,centered_score(raw+87,np.zeros_like(raw),mask))
        self.assertGreater(centered_score(raw+[[0,8,-8,0]],np.zeros_like(raw),mask)[0],s[0])

    def test_exact_counterexamples_and_two_antenna_mirror(self):
        c=counterexamples(self.cfg)
        for key in ('radial_equal_rssi_max_db','mirror_two_antenna_max_db','arbitrary_common_power_score_difference_db'):
            self.assertLess(c[key],1e-10)
        self.assertGreater(c['radial_power_difference_db'],17)

    def test_radial_shift_has_zero_m1_information_without_gnss_error(self):
        cfg=dict(self.cfg,claim_gnss_sd_m=0)
        q=claim(self.data,cfg,100,'outward')
        obs=observe(self.data,cfg,q,0,4,'joint_unbounded')
        self.assertLess(np.max(obs['M1'][0]),1e-10)
        self.assertGreater(np.mean(obs['M2'][0]),.5)

    def test_tangential_shift_creates_directional_residual(self):
        cfg=dict(self.cfg,claim_gnss_sd_m=0)
        q=claim(self.data,cfg,100,'tangential')
        self.assertGreater(np.mean(observe(self.data,cfg,q,0,4,'random')['M1'][0]),1)

    def test_unbounded_power_cannot_change_m1_m2_scores_in_full_reception(self):
        q=claim(self.data,self.cfg,100,'tangential')
        a=observe(self.data,self.cfg,q,2,4,'random')
        b=observe(self.data,self.cfg,q,2,4,'joint_unbounded')
        for model in ('M1','M2'): np.testing.assert_allclose(a[model][0],b[model][0],atol=1e-10)

    def test_joint_compensation_returns_m0_residual_to_normal_reference(self):
        q=claim(self.data,self.cfg,100,'outward')
        obs=observe(self.data,self.cfg,q,0,4,'joint_unbounded')
        expected=self.cfg['reference_received_dbm']+self.cfg['power_sd_db']*self.data['power_z']
        np.testing.assert_allclose(obs['M0_stat'][0],expected,atol=1e-10)

    def test_free_power_single_rssi_is_abstention_not_zero_attack_rate(self):
        q=claim(self.data,self.cfg,0,'outward');obs=observe(self.data,self.cfg,q,2,4,'random')
        table=calibrate(obs,self.cfg)
        usable,alarm=decide('M0_free',obs['M0_free'],table['M0_free'])
        m=metrics(usable,alarm)
        self.assertEqual(m['abstain_rate'],1);self.assertIsNone(m['alarm_conditional'])

    def test_no_calibration_support_means_abstention(self):
        values=(np.array([0.,1.]),np.array([3,3]))
        table=calibrate({'M1':values},self.cfg)
        u,_=decide('M1',values,table['M1']);self.assertFalse(u.any())

    def test_timestamp_gap_alone_does_not_change_local_measurement(self):
        q=claim(self.data,self.cfg,100,'tangential')
        a=observe(self.data,self.cfg,q,2,4,'joint_unbounded',gap_s=0)
        b=observe(self.data,self.cfg,q,2,4,'joint_unbounded',gap_s=86400)
        for model in a: np.testing.assert_allclose(a[model][0],b[model][0],equal_nan=True)

    def test_stale_calibration_drift_is_distinct_from_time_gap(self):
        q=claim(self.data,self.cfg,0,'outward')
        a=observe(self.data,self.cfg,q,2,4,'random','async_drift',0)
        b=observe(self.data,self.cfg,q,2,4,'random','async_drift',86400)
        self.assertGreater(np.max(np.abs(a['M1'][0]-b['M1'][0])),.1)

    def test_switched_separate_packets_breaks_cancellation(self):
        q=claim(self.data,self.cfg,0,'outward')
        a=observe(self.data,self.cfg,q,0,4,'random')
        b=observe(self.data,self.cfg,q,0,4,'random','switched_packets')
        self.assertGreater(np.mean(b['M1'][0]),np.mean(a['M1'][0])+2)

    def test_power_dependent_missingness_and_unsupported_masks(self):
        q=claim(self.data,self.cfg,100,'outward')
        a=observe(self.data,self.cfg,q,2,4,'random','rf_missing')
        b=observe(self.data,self.cfg,q,2,4,'joint_unbounded','rf_missing')
        self.assertGreater(np.count_nonzero(np.isnan(b['M0_stat'][0])),np.count_nonzero(np.isnan(a['M0_stat'][0])))
        self.assertTrue(np.any(~np.isfinite(b['M1'][0])))

    def test_generate_repeatable_and_splits_are_disjoint(self):
        a=generate(self.cfg,71,1);b=generate(self.cfg,71,0)
        np.testing.assert_array_equal(a['xyz'],self.data['xyz'])
        self.assertFalse(np.array_equal(a['xyz'],b['xyz']))

    def test_at_least_three_antennas_resolve_analytic_azimuth_mirror(self):
        self.assertGreater(np.max(np.abs(pattern(.5,4)-pattern(-.5,4))),2)

    def test_indoor_pool_baseline_and_sector_split(self):
        data={0:{(1,'B1'):[-60]*50+[-62]*50,(2,'B1'):[-70]*50+[-67]*50}}
        pools,stats=indoor_pools(data,0)
        np.testing.assert_array_equal(pools[0],np.full(50,3))
        np.testing.assert_array_equal(pools[1],np.full(50,-2))
        self.assertTrue(stats['disjoint_sector_sets'])

    def test_calibration_table_never_changes_when_test_claim_changes(self):
        cal=generate(self.cfg,71,0)
        obs=observe(cal,self.cfg,claim(cal,self.cfg,0,'outward'),2,4,'random')
        table=calibrate(obs,self.cfg);snapshot=repr(table)
        attack=observe(self.data,self.cfg,claim(self.data,self.cfg,100,'tangential'),2,4,'joint_unbounded')
        for model in attack: decide(model,attack[model],table[model])
        self.assertEqual(snapshot,repr(table))


if __name__=='__main__': unittest.main()
