import json
from pathlib import Path
import unittest
import numpy as np
from event_scenarios import (generate, rssi, claimed_distances, mask_for, profile_score,
                             thresholds, metrics, counterexamples)


class EventScenarioTests(unittest.TestCase):
    def setUp(self):
        self.cfg = json.loads(Path(__file__).with_name('event_scenarios_config.json').read_text())
        self.cfg.update(calibration_flights=2, test_flights=3, events_per_flight=40)

    def test_common_trajectory_drives_all_receiver_distances(self):
        d = generate(self.cfg, 71, 0)
        expected = np.linalg.norm(d['xyz'][:, :, None, :] - np.asarray(self.cfg['observer_xyz_m']), axis=3)
        np.testing.assert_allclose(d['dist'], expected)
        self.assertEqual(d['xyz'].shape, (2, 40, 3))
        self.assertLess(np.max(np.linalg.norm(np.diff(d['xyz'], axis=1), axis=2)), 12)

    def test_calibration_and_test_share_hardware_not_trajectories(self):
        cal, test = generate(self.cfg, 72, 0), generate(self.cfg, 72, 1)
        np.testing.assert_array_equal(cal['bias'], test['bias'])
        self.assertFalse(np.array_equal(cal['xyz'][0], test['xyz'][0]))

    def test_arbitrary_common_power_changes_cancel(self):
        d = generate(self.cfg, 73, 1)
        raw = rssi(d, self.cfg, 2)
        mask = mask_for(d, 'partial')
        s, _, _ = profile_score(raw, d['dist'], mask, 22)
        change = np.random.default_rng(17).normal(0, 40, raw.shape[:2])
        changed, _, _ = profile_score(raw + change[:, :, None], d['dist'], mask, 22)
        np.testing.assert_allclose(s, changed, equal_nan=True, atol=1e-10)

    def test_independent_event_powers_do_not_cancel(self):
        raw = np.array([[[-80., -80., -80.]]])
        dist = np.ones_like(raw) * 50
        mask = np.ones_like(raw, dtype=bool)
        s, _, _ = profile_score(raw, dist, mask, 22)
        changed, _, _ = profile_score(raw + np.array([[[0., 8., -8.]]]), dist, mask, 22)
        self.assertLess(s.item(), 1e-10)
        self.assertGreater(changed.item(), 6)

    def test_single_receiver_requires_abstention(self):
        d = generate(self.cfg, 74, 1)
        mask = mask_for(d, 'single')
        self.assertTrue(np.all(mask.sum(axis=2) <= 1))
        score, pat, _ = profile_score(rssi(d, self.cfg, 2), d['dist'], mask, 22)
        result = metrics(score, pat, {})
        self.assertEqual(result['abstain_fraction'], 1)
        self.assertIsNone(result['conditional_alarm_fraction'])

    def test_unsupported_calibration_subset_is_not_silently_used(self):
        cfg = dict(self.cfg, minimum_calibration_events_per_subset=3)
        table = thresholds(np.array([[1., 2.]]), np.array([[3, 3]]), cfg)
        self.assertEqual(table, {})

    def test_joint_common_power_cannot_change_profiled_score(self):
        d = generate(self.cfg, 75, 1)
        raw = rssi(d, self.cfg, 2); cd = claimed_distances(d, self.cfg, 100)
        mask = mask_for(d, 'full')
        s, _, _ = profile_score(raw, cd, mask, 22)
        offset = 22 * np.log10(d['dist'] / cd).mean(axis=2)
        changed, _, _ = profile_score(raw + offset[:, :, None], cd, mask, 22)
        np.testing.assert_allclose(s, changed, atol=1e-10)

    def test_two_nonidentifiability_constructions(self):
        c = counterexamples(self.cfg)
        self.assertLess(c['circle']['max_rssi_difference_db'], 1e-10)
        self.assertLess(c['disjoint']['max_rssi_difference_db'], 1e-10)
        self.assertGreater(abs(c['circle']['attack_power_change_db']), 2)


if __name__ == '__main__':
    unittest.main()
