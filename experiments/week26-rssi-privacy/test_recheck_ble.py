"""Checks for block accounting, held-out sectors and threshold ties."""
import unittest

from recheck_ble import BEACONS, block_medians, detect, quantile


class AnalysisTests(unittest.TestCase):
    def test_full_blocks_only(self):
        # The final ten normal rows do not form a full 20-row decision.
        self.assertEqual(block_medians(list(range(50)), 20), [9.5, 29.5])
        self.assertEqual(block_medians([3, 1, 7, 2], 2), [2, 4.5])

    def test_quantile_interpolation_and_invalid_inputs(self):
        self.assertAlmostEqual(quantile([0, 10], .95), 9.5)
        with self.assertRaises(ValueError):
            quantile([], .95)
        with self.assertRaises(ValueError):
            block_medians([1], 0)

    def test_baseline_not_used_as_normal_evaluation(self):
        # Large baseline/normal difference must remain visible after centering.
        data = {}
        for power in [-8, -4, 0]:
            data[power] = {}
            for sector in range(1, 29):
                for beacon in BEACONS:
                    values = [-100] * 50 + [-80 if sector % 2 else -90] * 50
                    data[power][sector, beacon] = values if power == -8 else [-60] * 100
        rows, summary = detect(data)
        for row in rows:
            # Calibrate even sectors at +10; test odd sectors at +20 and vice versa.
            self.assertEqual(row['threshold_db'], 10 if row['calibration_sector_parity'] == 0 else 20)
            if row['nominal_tx_dbm'] == -8:
                self.assertEqual(row['alarm_rate'], 1 if row['test_sector_parity'] == 1 else 0)
        self.assertEqual(summary[0]['normal_fpr_decisions'], 8400)
        self.assertEqual(summary[2]['normal_fpr_decisions'], 336)
        self.assertEqual(summary[2]['shift8_tpr_decisions'], 840)

    def test_ties_do_not_trigger_strict_upper_alarm(self):
        data = {power: {(s, b): [-70] * 100 for s in range(1, 29) for b in BEACONS}
                for power in [-8, -4, 0]}
        rows, summary = detect(data)
        self.assertTrue(all(r['alarm_count'] == 0 for r in rows))


if __name__ == '__main__':
    unittest.main()
