"""Unit fixtures exercise inference boundaries, not RF experiment results."""
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from evaluation import (signal_dbm,fit_geometry,single_residual,kf_scores,drss_score,
                        calibrated_threshold,decide,metrics,split_check,seed_interval,risk_mask)
from visualization_adapter import export_event


def observation(distance=100,power=13,node=0,packet=1,delivered=True):
    signal=power-40-20*math.log10(distance)
    total=10*math.log10(10**(signal/10)+1e-10)
    return dict(source_run_id='opaque',tx_event_id=packet,rx_node_id=node,serial=1,
                rx_xyz=[0,0,0],claimed_xyz=[distance,0,0],rssi_dbm=total if delivered else None,delivered=delivered)


class EvaluationTests(unittest.TestCase):
    def test_only_normal_splits_can_fit_or_calibrate(self):
        with self.assertRaisesRegex(ValueError,'normal training'):fit_geometry([],'eval_attack')
        with self.assertRaisesRegex(ValueError,'normal calibration'):calibrated_threshold([1000],'eval_attack')
        with self.assertRaisesRegex(ValueError,'leakage'):split_check([1],[2],[1,3])
        split_check([1],[2],[3])

    def test_noise_subtraction_restores_control_signal(self):
        self.assertAlmostEqual(signal_dbm(observation()),13-40-40,places=11)
        self.assertIsNone(signal_dbm(observation(delivered=False)))
        row=observation();row['rssi_dbm']=-101
        self.assertIsNone(signal_dbm(row))

    def test_geometry_model_fits_normal_observables_only(self):
        rows=[observation(d) for d in range(10,31)]
        geometry=fit_geometry(rows,'train_normal')
        self.assertAlmostEqual(geometry[0][1],-20,places=9)
        self.assertLess(max(single_residual(rows,geometry)),1e-9)

    def test_common_unknown_fixed_power_offset_is_a_nuisance(self):
        rows=[observation(d) for d in range(10,31)]
        model=fit_geometry(rows,'train_normal')
        shifted=[observation(d,power=19) for d in range(10,31)]
        self.assertLess(max(single_residual(shifted,model)),1e-9)

    def test_kf_startup_and_missing_are_und_not_zero(self):
        view=[observation(packet=1),observation(packet=2,delivered=False),observation(power=15,packet=3)]
        scores=kf_scores(view)
        self.assertIsNone(scores[0]);self.assertIsNone(scores[1])
        # first actual update, no update on the missing packet
        r0=view[0]['rssi_dbm'];r1=view[2]['rssi_dbm']
        self.assertAlmostEqual(scores[2],(r1-r0)**2/14.01)

    def test_kf_state_is_observer_and_claimed_rid_specific(self):
        view=[observation(node=0),observation(node=2,packet=2),observation(node=0,packet=3)]
        self.assertEqual(kf_scores(view)[:2],[None,None]);self.assertIsNotNone(kf_scores(view)[2])

    def test_drss_common_power_cancels_but_one_observer_abstains(self):
        geometry={0:(-27,-20),2:(-27,-20)}
        frame=[observation(100,node=0),observation(200,node=2)]
        other=[observation(100,power=19,node=0),observation(200,power=19,node=2)]
        self.assertAlmostEqual(drss_score(frame,geometry),drss_score(other,geometry),places=10)
        self.assertIsNone(drss_score(frame[:1],geometry))
        other[1]['tx_event_id']=2
        with self.assertRaisesRegex(ValueError,'one physical'):drss_score(other,geometry)

    def test_denominators_do_not_hide_missing_or_startup(self):
        result=metrics(['FLAG','BELOW_THRESHOLD','UNDETERMINED','UNDETERMINED'],[True,True,True,False])
        self.assertEqual(result['alarm_scored'],.5)
        self.assertEqual(result['alarm_received'],1/3)
        self.assertEqual(result['alarm_all_tx'],.25)
        self.assertEqual(result['und_rate'],.5)
        with self.assertRaisesRegex(ValueError,'unreceived'):metrics(['FLAG'],[False])

    def test_all_abstentions_have_no_conditional_performance(self):
        scores=[None,None];decisions=decide(scores,None)
        result=metrics(decisions,[True,False])
        self.assertIsNone(result['alarm_scored']);self.assertEqual(result['und_rate'],1)
        self.assertIsNone(calibrated_threshold(scores,'calibrate_normal'))

    def test_threshold_is_strict_and_no_attacks_are_needed(self):
        threshold=calibrated_threshold(list(range(20)),'calibrate_normal')
        self.assertEqual(threshold,18)
        self.assertEqual(decide([18,19,None],threshold),['BELOW_THRESHOLD','FLAG','UNDETERMINED'])

    def test_bootstrap_unit_is_a_seed_value_not_a_packet(self):
        ci=seed_interval([.1,.9],repeats=100)
        self.assertEqual(ci['independent_seeds'],2);self.assertAlmostEqual(ci['mean'],.5)
        self.assertIsNone(seed_interval([])['mean'])
        self.assertIsNone(seed_interval([.5])['low'])

    def test_risk_truth_is_only_an_evaluation_mask(self):
        tx=[dict(tx_time=0,true_tx_xyz=[0,0,20],claimed_xyz=[100,0,20]),
            dict(tx_time=1,true_tx_xyz=[0,0,40],claimed_xyz=[100,0,40])]
        self.assertEqual(risk_mask(tx,lambda _: [0,0,0]),[True,False])

    def test_visualization_cannot_join_different_runs_or_packets(self):
        metadata=dict(source_run_id='a')
        with self.assertRaisesRegex(ValueError,'physical event'):
            export_event([dict(tx_event_id=1),dict(tx_event_id=2)],metadata,'x',None,None,'UNDETERMINED','same_physical_packet_multirx')
        with self.assertRaisesRegex(ValueError,'source run'):
            export_event([dict(tx_event_id=1,source_run_id='b')],metadata,'x',None,None,'UNDETERMINED','same_physical_packet_multirx')

    def test_visualization_asynchronous_view_cannot_use_multiple_receivers(self):
        row=dict(tx_event_id=1,source_run_id='a')
        with self.assertRaisesRegex(ValueError,'one selected RSSI'):
            export_event([row,row],dict(source_run_id='a'),'x',None,None,'UNDETERMINED','async_single_packet_per_observation')


if __name__=='__main__':unittest.main()
