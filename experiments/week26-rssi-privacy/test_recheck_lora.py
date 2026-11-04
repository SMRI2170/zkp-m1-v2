import unittest
import numpy as np
from recheck_lora import blocks, delayed_pairs, distance_proxy, expected, fit_model, scores


class LoRaRecheckTests(unittest.TestCase):
    def test_geometry_uses_height_and_burial_depth(self):
        d = distance_proxy(np.array([0.]), np.array([0.]), np.array([20.]),
                           np.array([.5]), 0., 0.)
        self.assertAlmostEqual(d[0], 20.5)

    def test_blocks_do_not_cross_outage_or_use_future(self):
        run = dict(t=np.array([0., .2, .4, 10., 10.2, 10.4]),
                   r=np.array([-80., -82., -84., -90., -92., -94.]),
                   d=np.arange(6.) + 20)
        b = blocks(run, 2)
        np.testing.assert_allclose(b['t'], [.2, 10.2])
        np.testing.assert_allclose(b['r'], [-81, -91])
        np.testing.assert_allclose(b['d'], [21, 24])
        self.assertTrue(np.all(b['span'] < 1))

    def test_power_compensation_is_exact_negative_control(self):
        model = np.array([-40., -25.])
        b = dict(d=np.array([20., 50., 100.]), r=np.array([-82., -85., -96.]))
        np.testing.assert_allclose(scores(model, b, 100, True), scores(model, b), atol=1e-12)
        self.assertGreater(np.max(np.abs(scores(model, b, 100) - scores(model, b))), 1)

    def test_delay_is_past_only_and_same_query_cohort(self):
        t = np.r_[np.arange(0, 20, .2), np.arange(40, 60, .2)]
        run = dict(t=t, r=np.ones(len(t)), d=np.ones(len(t)))
        pairs = delayed_pairs(run, (0, 1, 5))
        cohort = pairs[0][1]
        for lag, (past, query) in pairs.items():
            np.testing.assert_array_equal(query, cohort)
            self.assertTrue(np.all(t[query] - t[past] >= lag - 1e-10))
            self.assertTrue(np.all(t[query] - t[past] <= lag + 2))
            self.assertTrue(np.all((t[query] < 20) == (t[past] < 20)))

    def test_fit_does_not_depend_on_test_labels(self):
        d = np.array([10., 20., 40., 80.])
        model = np.array([-40., -22.])
        fit = fit_model(dict(d=d, r=expected(model, d)))
        np.testing.assert_allclose(fit, model, atol=1e-10)

    def test_empty_dropout_blocks_are_retained_as_empty(self):
        run = dict(t=np.arange(5.), r=np.ones(5), d=np.ones(5))
        b = blocks(run, 20, np.ones(5, dtype=bool))
        self.assertEqual(len(b['r']), 0)


if __name__ == '__main__':
    unittest.main()
