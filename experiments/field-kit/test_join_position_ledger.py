import copy
import json
from pathlib import Path
import tempfile
import unittest

from join_position_ledger import join_event, summarize, load_private, run


class LedgerTests(unittest.TestCase):
    def setUp(self):
        # All coordinates and times are synthetic, not field records.
        self.p = dict(alias='B', run_id='synthetic', boot_id='boot-test', kind='fixed',
                      latitude=0, longitude=0, horizontal_accuracy_m=3, crs='EPSG:4326',
                      valid_from_utc='2026-01-01T00:00:00Z', valid_until_utc='2026-01-01T00:01:00Z',
                      method='synthetic survey', evidence_ref='synthetic-fixture',
                      altitude_m=0, altitude_reference='MSL', vertical_accuracy_m=2)
        self.e = dict(alias='B', run_id='synthetic', boot_id='boot-test', moving=False,
                      observed_utc='2026-01-01T00:00:30Z', clock_uncertainty_s=1,
                      clock_evidence_ref='synthetic-anchor',
                      claim=dict(latitude=0, longitude=.001, horizontal_accuracy_m=5,
                                 altitude_m=20, altitude_reference='MSL', vertical_accuracy_m=4))

    def result(self):
        return join_event(self.e, [self.p])

    def test_geometry_and_uncertainty(self):
        r = self.result()
        self.assertAlmostEqual(r['horizontal_distance_m'], 111.1949, places=3)
        self.assertGreater(r['slant_distance_m'], r['horizontal_distance_m'])
        self.assertEqual(r['horizontal_uncertainty_sum_m'], 8)
        self.assertEqual(r['vertical_uncertainty_sum_m'], 6)
        self.assertFalse(r['claim_is_truth'])

    def test_no_ledger(self):
        self.assertEqual(join_event(self.e, [])['reasons'], ['POSITION_LEDGER_MISSING'])

    def test_wrong_node_run_boot(self):
        for field in ['alias', 'run_id', 'boot_id']:
            with self.subTest(field=field):
                p = copy.deepcopy(self.p); p[field] = 'other'
                self.assertEqual(join_event(self.e, [p])['status'], 'HELD')

    def test_validity_clock_interval(self):
        self.e['observed_utc'] = '2026-01-01T00:00:00Z'
        self.assertIn('OUTSIDE_VALIDITY_WITH_CLOCK_UNCERTAINTY', self.result()['reasons'])

    def test_naive_invalid_time(self):
        for t in ['2026-01-01T00:00:30', 'invalid', None]:
            self.e['observed_utc'] = t
            self.assertEqual(self.result()['status'], 'HELD')

    def test_unverified_clock(self):
        del self.e['clock_evidence_ref']
        self.assertIn('CLOCK_EVIDENCE_MISSING', self.result()['reasons'])

    def test_ambiguous_overlap(self):
        self.assertEqual(join_event(self.e, [self.p, copy.deepcopy(self.p)])['reasons'], ['AMBIGUOUS_LEDGER_MATCH'])

    def test_unknown_accuracy_nan_bool_and_invalid_coordinate(self):
        for key, v in [('horizontal_accuracy_m', 0), ('latitude', float('nan')),
                       ('latitude', True), ('longitude', 181), ('crs', 'unknown')]:
            p = copy.deepcopy(self.p); p[key] = v
            self.assertEqual(join_event(self.e, [p])['status'], 'HELD')

    def test_altitude_mismatch_preserves_2d(self):
        for v in ['WGS84_ellipsoid', 'local_ground', None]:
            self.e['claim']['altitude_reference'] = v
            r = self.result()
            self.assertEqual(r['status'], 'CLAIM_2D_ONLY')
            self.assertIsNone(r['slant_distance_m'])

    def test_vertical_accuracy_missing(self):
        del self.p['vertical_accuracy_m']
        self.assertEqual(self.result()['status'], 'CLAIM_2D_ONLY')

    def test_missing_claim_accuracy_not_replaced_with_zero(self):
        del self.e['claim']['horizontal_accuracy_m']
        self.assertIsNone(self.result()['horizontal_uncertainty_sum_m'])

    def test_moving_rejects_static(self):
        self.e['moving'] = True
        self.assertEqual(self.result()['status'], 'HELD')

    def test_track_freshness_includes_clock_error(self):
        self.e['moving'] = True
        self.p.update(kind='track_fix', fix_utc='2026-01-01T00:00:29Z')
        self.assertEqual(self.result()['status'], 'CLAIM_3D_METADATA_COMPATIBLE')
        self.e['clock_uncertainty_s'] = 1.01
        self.assertEqual(self.result()['status'], 'HELD')

    def test_missing_claim(self):
        self.e['claim'] = None
        self.assertEqual(self.result()['status'], 'HELD')

    def test_public_summary_has_no_location_or_timestamp(self):
        text = json.dumps(summarize([self.result()]))
        for secret in ['latitude', 'longitude', '111.19', 'boot-test', '2026-01', 'synthetic-anchor']:
            self.assertNotIn(secret, text)

    def test_outside_private_root_denied(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'input.json'; p.write_text('[]')
            with self.assertRaises(ValueError): load_private(p)

    def test_private_cli_outputs_and_no_overwrite(self):
        root = Path(__file__).resolve().parents[2]/'captures'
        root.mkdir(mode=0o700, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='ledger-synthetic-test-', dir=root) as d:
            p = Path(d)
            events, ledger = p/'events.json', p/'ledger.json'
            for path, value in [(events, [self.e]), (ledger, [self.p])]:
                path.write_text(json.dumps(value)); path.chmod(0o600)
            before = (events.read_bytes(), ledger.read_bytes())
            out = run(events, ledger, p/'private', p/'public')
            self.assertEqual(out['statuses'], {'CLAIM_3D_METADATA_COMPATIBLE': 1})
            self.assertEqual((events.read_bytes(), ledger.read_bytes()), before)
            for path in (p/'private').iterdir():
                self.assertEqual(path.stat().st_mode & 0o077, 0)
            with self.assertRaises(ValueError): run(events, ledger, p/'private', p/'public')
            events.chmod(0o644)
            with self.assertRaises(ValueError): load_private(events)

    def test_symlink_input_denied(self):
        root = Path(__file__).resolve().parents[2]/'captures'
        root.mkdir(mode=0o700, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='ledger-synthetic-test-', dir=root) as d:
            p = Path(d)
            (p/'source.json').write_text('[]'); (p/'source.json').chmod(0o600)
            (p/'link.json').symlink_to(p/'source.json')
            with self.assertRaises(ValueError): load_private(p/'link.json')


if __name__ == '__main__':
    unittest.main()
