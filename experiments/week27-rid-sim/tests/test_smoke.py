"""Synthetic unit fixtures only; these are not OMNeT++ execution evidence."""
import copy
import contextlib
from decimal import Decimal
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from normalize import integer, normalize, read_vectors
from run_smoke import assert_case
from smoke_callback import SmokeAudit
import run_smoke


def fixture():
    tx = {'Transmission Packet ID': 100., 'Transmission Is Spoofed': 0., 'Transmission Power': 13.}
    rx = {'Packet ID': 100., 'Reception Power': -65., 'Serial Number': 1., 'Reception Timestamp': 100.}
    for axis, true, received in zip('XYZ', [150., 100., 40.], [100., 100., 2.]):
        tx['Transmission My ' + axis + ' Coordinate'] = true
        tx['Transmission ' + axis + ' Coordinate'] = true
        rx['Reception ' + axis + ' Coordinate'] = true
        rx['Reception My ' + axis + ' Coordinate'] = received
    return {
        ('BasicUav.host[1].wlan[0].mgmt', 10, Decimal('.1')): tx,
        ('BasicUav.host[0].wlan[0].mgmt', 12, Decimal('.101')): rx,
        ('BasicUav.gcs[0]', 13, Decimal('.102')): {'packet_id': 100., 'report_count': 1.}
    }


class SmokeTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((ROOT / 'config/smoke.json').read_text())

    def test_tx_receiver_denominator_includes_unobserved(self):
        rows, tx, _, summary = normalize(fixture(), 'Normal', self.config)
        self.assertEqual((summary['tx_enqueued'], summary['receiver_opportunities'], summary['rx_delivered']), (1, 2, 1))
        lost = next(r for r in rows if not r['delivered'])
        self.assertIsNone(lost['rssi_dbm'])
        self.assertIsNone(lost['serial'])
        self.assertEqual(lost['delivery'], 'NOT_OBSERVED')
        assert_case('Normal', rows, tx, summary)

    def test_missing_rssi_does_not_shift_other_observations(self):
        events = fixture()
        rx = next(v for k, v in events.items() if '.host[0]' in k[0])
        del rx['Reception Power']
        rows, _, _, summary = normalize(events, 'Normal', self.config)
        delivered = next(r for r in rows if r['delivered'])
        self.assertIsNone(delivered['rssi_dbm'])
        self.assertEqual(delivered['serial'], 1)
        self.assertEqual(summary['delivered_without_rssi'], 1)

    def test_actual_zero_rssi_not_treated_as_missing(self):
        events = fixture()
        next(v for k, v in events.items() if '.host[0]' in k[0])['Reception Power'] = 0.
        rows, _, _, _ = normalize(events, 'Normal', self.config)
        self.assertEqual(next(r for r in rows if r['delivered'])['rssi_dbm'], 0.)

    def test_unknown_rx_packet_rejected(self):
        events = fixture()
        next(v for k, v in events.items() if '.host[0]' in k[0])['Packet ID'] = 101.
        with self.assertRaisesRegex(ValueError, 'exact TX'):
            normalize(events, 'Normal', self.config)

    def test_duplicate_rx_rejected(self):
        events = fixture()
        key = next(k for k in events if '.host[0]' in k[0])
        events[(key[0], 20, Decimal('.2'))] = copy.deepcopy(events[key])
        with self.assertRaisesRegex(ValueError, 'Duplicate RX'):
            normalize(events, 'Normal', self.config)

    def test_received_claim_mismatch_rejected(self):
        events = fixture()
        next(v for k, v in events.items() if '.host[0]' in k[0])['Reception X Coordinate'] = 250.
        with self.assertRaisesRegex(ValueError, 'claim'):
            normalize(events, 'Normal', self.config)

    def test_zero_tx_is_not_success(self):
        with self.assertRaisesRegex(ValueError, 'No TX'):
            normalize({}, 'Normal', self.config)

    def test_gcs_count_mismatch_rejected(self):
        events = fixture()
        next(v for k, v in events.items() if '.gcs[' in k[0])['report_count'] = 2.
        with self.assertRaisesRegex(ValueError, 'GCS report total'):
            normalize(events, 'Normal', self.config)

    def test_wrong_attack_label_rejected(self):
        rows, tx, _, summary = normalize(fixture(), 'StaticSpoof', self.config)
        with self.assertRaisesRegex(ValueError, 'Claim/attack label'):
            assert_case('StaticSpoof', rows, tx, summary)

    def test_loss_cannot_be_reported_as_detection(self):
        rows, _, _, summary = normalize(fixture(), 'Normal', self.config)
        self.assertTrue(all(r['decision'] == 'UNDETERMINED' and r['score'] is None for r in rows))
        self.assertIsNone(summary['fpr'])
        self.assertIsNone(summary['tpr'])

    def test_large_packet_id_precision_rejected(self):
        for value in (float(2**53), float('nan'), 1.5, None):
            with self.assertRaises(ValueError):
                integer(value)

    def test_etv_event_alignment_not_row_index(self):
        text = 'version 2\nrun fixture\nvector 1 BasicUav.host[0].wlan[0].mgmt "Packet ID" ETV\nvector 2 BasicUav.host[0].wlan[0].mgmt "Reception Power" ETV\n1 10 .1 100\n1 20 .2 200\n2 20 .2 -70\n'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'fixture.vec'
            path.write_text(text)
            events = read_vectors(path)
        self.assertNotIn('Reception Power', events[('BasicUav.host[0].wlan[0].mgmt', 10, Decimal('.1'))])
        self.assertEqual(events[('BasicUav.host[0].wlan[0].mgmt', 20, Decimal('.2'))]['Reception Power'], -70.)

    def test_callback_logs_only_observed_fields(self):
        data = {'packet_id': 3, 'serial_number': 0, 'rid_timestamp': 0, 'reports': [{'rssi_dbm': -80}]}
        result = SmokeAudit().on_gcs_reports(data)
        self.assertEqual(result['log']['report_count'], 1)
        self.assertNotIn('detected', result['log'])

    def test_duplicate_tx_id_rejected(self):
        events = fixture()
        key = next(k for k in events if '.host[1]' in k[0])
        events[(key[0], 20, Decimal('.2'))] = copy.deepcopy(events[key])
        with self.assertRaisesRegex(ValueError, 'Duplicate TX'):
            normalize(events, 'Normal', self.config)

    def test_different_packets_same_claimed_timestamp_are_not_merged(self):
        events = fixture()
        for key, fields in list(events.items()):
            fields = copy.deepcopy(fields)
            for name in ['Transmission Packet ID', 'Packet ID', 'packet_id']:
                if name in fields:
                    fields[name] = 200.
            events[(key[0], key[1] + 100, key[2] + Decimal('1'))] = fields
        rows, tx, _, summary = normalize(events, 'Normal', self.config)
        self.assertEqual(len(tx), 2)
        self.assertEqual({r['tx_event_id'] for r in rows}, {100, 200})
        self.assertEqual(summary['receiver_opportunities'], 4)

    def test_gcs_total_cannot_hide_wrong_packet_association(self):
        events = fixture()
        for key, fields in list(events.items()):
            fields = copy.deepcopy(fields)
            for name in ['Transmission Packet ID', 'Packet ID', 'packet_id']:
                if name in fields:
                    fields[name] = 200.
            events[(key[0], key[1] + 100, key[2] + Decimal('1'))] = fields
        key = next(k for k in events if '.gcs[' in k[0] and k[1] > 100)
        events[key]['packet_id'] = 100.
        with self.assertRaisesRegex(ValueError, 'per-packet'):
            normalize(events, 'Normal', self.config)

    def test_non_etv_vectors_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'fixture.vec'
            path.write_text('vector 1 BasicUav.host[0].wlan[0].mgmt "Packet ID" TV\n')
            with self.assertRaisesRegex(ValueError, 'ETV'):
                read_vectors(path)

    def test_blocked_environment_creates_no_observation_data(self):
        captures = ROOT.parents[1] / 'captures'
        captures.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=captures) as directory:
            directory = Path(directory)
            argv = ['run_smoke.py', '--workspace', str(directory / 'missing-dependencies'),
                    '--raw-dir', str(directory / 'raw'), '--summary-dir', str(directory / 'summary')]
            with patch.object(sys, 'argv', argv), patch.object(run_smoke.subprocess, 'check_output', side_effect=ValueError('synthetic missing dependency')), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(run_smoke.main(), 2)
            summary = json.loads((directory / 'summary/summary.json').read_text())
            self.assertEqual(summary['status'], 'ENV_BLOCKED')
            self.assertTrue(all(c['status'] == 'NOT_RUN' for c in summary['cases']))
            self.assertEqual(list((directory / 'raw').iterdir()), [])


if __name__ == '__main__':
    unittest.main()
