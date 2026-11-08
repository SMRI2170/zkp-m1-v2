"""Observation-boundary and mathematical tests, not fabricated RF traces."""
import math
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from observations import detector_projection,asynchronous_view,same_packet_group,unrestricted_single_rssi,nonidentifiability_counterexample,translated_trajectory_counterexample,symmetric_multisite_counterexample
from scene import ini_for
from run_smoke import run_logged


class ObservationTests(unittest.TestCase):
    def test_unbounded_power_counterexample_1000_and_5000(self):
        for n in [1000,5000]:
            result=nonidentifiability_counterexample(n)
            self.assertLess(result['max_rssi_difference_db'],1e-10)
            self.assertAlmostEqual(result['power_compensation_db'],12.041199826559248)

    def test_smooth_paths_can_also_be_nonidentifiable(self):
        result=translated_trajectory_counterexample(1000)
        self.assertLess(result['max_rssi_difference_db'],1e-10)
        self.assertTrue(result['common_claim_in_both_worlds'])

    def test_four_receivers_not_a_general_identifiability_guarantee(self):
        result=symmetric_multisite_counterexample()
        self.assertLess(result['max_rssi_difference_db'],1e-10)
        self.assertAlmostEqual(result['power_change_db'],11*math.log10(10400/16400),places=12)

    def test_different_packets_cannot_be_drss_joined(self):
        view=[dict(source_run_id='a',tx_event_id=i,rx_node_id=i,delivered=True,rssi_dbm=-60) for i in [1,2]]
        with self.assertRaisesRegex(ValueError,'one physical'):same_packet_group(view)

    def test_same_packet_id_in_different_runs_is_not_same_transmission(self):
        view=[dict(source_run_id=s,tx_event_id=1,rx_node_id=i,delivered=True,rssi_dbm=-60) for i,s in enumerate(['a','b'])]
        with self.assertRaisesRegex(ValueError,'one physical'):same_packet_group(view)

    def test_duplicate_receiver_rejected(self):
        row=dict(source_run_id='a',tx_event_id=1,rx_node_id=0,delivered=True,rssi_dbm=-60)
        with self.assertRaisesRegex(ValueError,'Duplicate receiver'):same_packet_group([row,row])

    def test_async_policy_keeps_missing_selected_receiver(self):
        rows=[]
        for packet in range(3):
            for node in [0,2]:rows.append(dict(tx_event_id=packet,tx_time=packet*3600,rx_node_id=node,delivered=node==0,rssi_dbm=-60 if node==0 else None))
        view=asynchronous_view(rows,[0,2],3)
        self.assertEqual([r['rx_node_id'] for r in view],[0,2,0])
        self.assertIsNone(view[1]['rssi_dbm'])

    def test_detector_projection_removes_all_truth_and_labels(self):
        row=dict(tx_event_id=1,rx_event_id='0:2',rx_node_id=0,rx_time=.1,rx_xyz=[0,0,0],claimed_xyz=[1,2,3],rx_claimed_xyz=[1,2,3],claimed_timestamp=100,serial=1,rssi_dbm=-60,delivered=True,true_tx_xyz=[9,9,9],tx_power_dbm_truth_only=13,is_spoofed=1,case='spoof',seed=1)
        projected=detector_projection([row],'opaque_run')[0]
        for field in ['true_tx_xyz','tx_power_dbm_truth_only','is_spoofed','case','seed']:self.assertNotIn(field,projected)
        self.assertEqual(unrestricted_single_rssi([projected])[0]['decision'],'UNDETERMINED')
        self.assertNotEqual(projected['source_run_id'],'opaque_run')

    def test_unreceived_packet_does_not_leak_the_tx_claim(self):
        row=dict(tx_event_id=1,rx_event_id=None,rx_node_id=0,rx_time=None,rx_xyz=None,claimed_xyz=[1,2,3],rx_claimed_xyz=None,claimed_timestamp=None,serial=None,rssi_dbm=None,delivered=False)
        projected=detector_projection([row],'run')[0]
        self.assertIsNone(projected['claimed_xyz'])

    def test_unrestricted_policy_rejects_multisite_input(self):
        row=dict(source_run_id='a',tx_event_id=1,rssi_dbm=-60)
        with self.assertRaisesRegex(ValueError,'one opportunity'):unrestricted_single_rssi([row,row])

    def test_long_gap_is_real_simulator_schedule_not_relabel(self):
        ini=ini_for(dict(count=10,gap_s=3600,seed=1,model='fixed',case='FixedNormal'))
        self.assertIn('beaconInterval = 3600s',ini)
        self.assertIn('sim-time-limit = 32400.15',ini)
        self.assertIn('updateInterval = 0s',ini)

    def test_zero_spacing_cannot_create_distinct_packets(self):
        with self.assertRaises(ValueError):ini_for(dict(count=10,gap_s=0,seed=1,model='fixed'))

    def test_output_budget_stops_owned_process_without_erasing_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            directory=Path(directory)
            for name in ['omnetpp-6.2.0','inet4.5']:
                (directory/name).mkdir();(directory/name/'setenv').write_text('')
            output=directory/'synthetic.vec'
            command=[sys.executable,'-c',f'import pathlib,time; pathlib.Path({str(output)!r}).write_bytes(b"x"*100000); time.sleep(10)']
            receipt=run_logged(directory,command,directory,directory/'test.log',5,watch_dir=directory,max_bytes=10000)
            self.assertEqual(receipt['stop_reason'],'output_size_budget')
            self.assertNotEqual(receipt['exit_code'],0)
            self.assertEqual(output.stat().st_size,100000)


if __name__=='__main__':unittest.main()
