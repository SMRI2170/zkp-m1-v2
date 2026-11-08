"""Synthetic audit fixtures; actual RF integration evidence is separate."""
from decimal import Decimal
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from run_power import physical_audit, compare_rssi, target_events, check_paired_geometry, expected_total_rss, check_paired_claim_inputs
from normalize import read_vectors


class PowerAuditTests(unittest.TestCase):
    def test_applied_phy_power_must_match_requested(self):
        events={('N.host[1].wlan[0].radio.transmitter',10,Decimal('.1')):{'PHY Packet ID':1.,'PHY Power dBm':13.,'PHY Power Tag Present':1.}}
        tx=[dict(tx_event_id=1,tx_power_dbm_truth_only=7.)]
        with self.assertRaisesRegex(ValueError,'actual PHY'):
            physical_audit(events,tx,[])

    def test_missing_packet_tag_is_not_accepted(self):
        events={('N.host[1].wlan[0].radio.transmitter',10,Decimal('.1')):{'PHY Packet ID':1.,'PHY Power dBm':13.,'PHY Power Tag Present':0.}}
        with self.assertRaisesRegex(ValueError,'actual PHY'):
            physical_audit(events,[dict(tx_event_id=1,tx_power_dbm_truth_only=13.)],[])

    def test_no_phy_logging_distinct_from_received_failure(self):
        rows=[dict(tx_event_id=1,delivered=False,delivery='NOT_OBSERVED')]
        summary=physical_audit({},[dict(tx_event_id=1)],rows)
        self.assertEqual(summary['phy_tx_count'],0)
        self.assertEqual(summary['enqueued_without_phy'],1)
        self.assertEqual(rows[0]['delivery'],'PHY_TX_NOT_LOGGED_BY_HORIZON')

    def test_received_packet_requires_actual_phy(self):
        with self.assertRaisesRegex(ValueError,'RX without PHY'):
            physical_audit({},[dict(tx_event_id=1)],[dict(tx_event_id=1,delivered=True)])

    def test_duplicate_physical_id_is_ambiguous(self):
        fields={'PHY Packet ID':1.,'PHY Power dBm':13.,'PHY Power Tag Present':1.}
        events={('A',1,Decimal('.1')):fields,('A',2,Decimal('.2')):fields}
        with self.assertRaisesRegex(ValueError,'duplicate PHY'):
            physical_audit(events,[],[])

    def test_rssi_pairing_does_not_impute_missing_receivers(self):
        first=[dict(tx_time=.1,rx_node_id=0,rssi_dbm=-60),dict(tx_time=.1,rx_node_id=2,rssi_dbm=-70)]
        second=[dict(tx_time=.1,rx_node_id=0,rssi_dbm=-54),dict(tx_time=.1,rx_node_id=2,rssi_dbm=None)]
        self.assertEqual(compare_rssi(first,second),[6])

    def test_target_filter_uses_packet_not_claimed_identity(self):
        events={('N.host[1].wlan[0].mgmt',1,Decimal('.1')):{'Transmission Packet ID':100},
                ('N.host[3].wlan[0].mgmt',2,Decimal('.1')):{'Transmission Packet ID':200},
                ('N.host[0].wlan[0].mgmt',3,Decimal('.2')):{'Packet ID':200,'Serial Number':1},
                ('N.host[0].wlan[0].mgmt',4,Decimal('.3')):{'Packet ID':100,'Serial Number':1}}
        selected=target_events(events)
        self.assertEqual(len(selected),2)
        self.assertNotIn(('N.host[0].wlan[0].mgmt',3,Decimal('.2')),selected)

    def test_repeated_gcs_callbacks_require_explicit_framing(self):
        names=['callback_id','packet_id','report_count','claimed_timestamp_ms','claimed_serial']
        values=[[1,2],[100,200],[2,3],[10,20],[1,1]]
        lines=['version 2','run synthetic']
        for index,(name,items) in enumerate(zip(names,values)):
            lines.append(f'vector {index} N.gcs[0] "{name}" ETV')
            lines.extend(f'{index} 10 .1 {v}' for v in items)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'fixture.vec';path.write_text('\n'.join(lines)+'\n')
            events=read_vectors(path)
        self.assertEqual(len(events),2)
        self.assertEqual([v['packet_id'] for v in events.values()],[100,200])

    def test_repeated_gcs_without_counter_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'fixture.vec'
            path.write_text('vector 1 N.gcs[0] "packet_id" ETV\n1 10 .1 100\n1 10 .1 200\n')
            with self.assertRaisesRegex(ValueError,'callback_id'):
                read_vectors(path)

    def test_paired_geometry_accepts_only_roundoff(self):
        a=[dict(tx_time=.1,true_tx_xyz=[1,2,3])]
        b=[dict(tx_time=.1,true_tx_xyz=[1+6e-11,2,3])]
        self.assertLess(check_paired_geometry({'FixedNormal':a,'Other':b})['max_position_difference_m'],1e-8)
        b[0]['true_tx_xyz'][0]=1.001
        with self.assertRaisesRegex(ValueError,'trajectories'):
            check_paired_geometry({'FixedNormal':a,'Other':b})

    def test_rss_control_includes_background_noise(self):
        import math
        signal=1e-6;noise=1e-10
        measured=10*math.log10(signal+noise)
        expected=10*math.log10(signal*10**.6+noise)
        self.assertAlmostEqual(expected_total_rss(measured,6),expected,places=10)
        self.assertNotEqual(expected-measured,6)
        with self.assertRaises(ValueError):expected_total_rss(-110,6)

    def test_position_pair_must_not_change_identity_or_timestamp(self):
        row=dict(tx_time=.1,rx_node_id=0,serial=1,claimed_timestamp=100,delivered=True)
        tx=[dict(tx_time=.1,tx_power_dbm_truth_only=13)]
        rows={'FixedNormal':[row],'PositionOnly':[dict(row)]}
        self.assertTrue(check_paired_claim_inputs(rows,{'FixedNormal':tx,'PositionOnly':tx})['identity_timestamp_pairs_verified'])
        rows['PositionOnly'][0]['serial']=0
        with self.assertRaisesRegex(ValueError,'identity/timestamp'):
            check_paired_claim_inputs(rows,{'FixedNormal':tx,'PositionOnly':tx})


if __name__=='__main__':
    unittest.main()
