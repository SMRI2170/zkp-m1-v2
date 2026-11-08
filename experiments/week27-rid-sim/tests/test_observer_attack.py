"""PR5 algebra, information isolation and native-math unit fixtures, not RF data."""
from pathlib import Path
import math
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from observer_attack import attack_delta,apply_limits,delta_for,attack_spec,attack_ini,SCHEDULE
from observations import detector_projection
from mlat_geometry import circular_layout_counterexample
from audit_attack_model import dipole_pair_gain


class ObserverAttackTests(unittest.TestCase):
    def test_vertical_dipole_model_has_expected_orientation_gain_and_null(self):
        self.assertAlmostEqual(dipole_pair_gain([10,0,0],[0,0,0]),20*math.log10(1.5))
        self.assertAlmostEqual(dipole_pair_gain([10,0,10],[0,0,0]),10*math.log10(.75**2))
        with self.assertRaises(ValueError):dipole_pair_gain([0,0,10],[0,0,0])
    def test_cocircular_four_receivers_leave_scale_height_ambiguity(self):
        result=circular_layout_counterexample()
        self.assertLess(result['max_rssi_difference_db'],1e-10)
        self.assertTrue(result['both_heights_positive'])
    def test_sign_matches_claimed_distance_prediction(self):
        change=delta_for([10,0,0],[100,0,0],[0,0,0])
        self.assertAlmostEqual(change,-20.)
        self.assertAlmostEqual(13+change-20*math.log10(10),13-20*math.log10(100))

    def test_attack_and_phy_clipping_are_separate(self):
        r=apply_limits(20,15,10,-80,23)
        self.assertTrue(r['clamped_by_attack_bound']);self.assertTrue(r['clamped_by_phy_limit'])
        self.assertEqual(r['effective_phy_tx_dbm'],23);self.assertEqual(r['applied_delta_db'],3)
        self.assertEqual(r['compensation_error_db'],-12)
        self.assertEqual(apply_limits(-12,-20,20,-8,23)['effective_phy_tx_dbm'],-8)

    def test_oracle_schedule_is_serialized_only_for_aware_case(self):
        aware=attack_spec(701,'schedule_aware',100,'strong')
        self.assertIn('*.host[1].typename = "Issue75PowerHost"',attack_ini(aware))
        self.assertIn('observerSchedule = "0 2 3 4 5"',attack_ini(aware))
        blind=attack_spec(701,'schedule_blind',100,'strong')
        original=attack_ini(blind);blind['defender_schedule']=list(reversed(SCHEDULE))
        self.assertEqual(original,attack_ini(blind));self.assertNotIn('observerSchedule',original)

    def test_fixed_oracle_receiver_matches_reference_compensation(self):
        p=[200,150,40];q=[300,150,40];catalog={0:[100,100,2],2:[300,100,2]}
        self.assertEqual(attack_delta('reference_rx0',p,q,catalog),attack_delta('schedule_aware',p,q,catalog,0))

    def test_blind_prior_has_no_selected_receiver_effect(self):
        p=[200,150,40];q=[300,150,40];catalog={0:[100,100,2],2:[300,100,2]}
        # The optional target is not consumed by the blind implementation.
        self.assertEqual(attack_delta('schedule_blind',p,q,catalog,0),attack_delta('schedule_blind',p,q,catalog,2))

    def test_invalid_constraints_and_extreme_distances_fail_closed(self):
        for args in [(13,float('nan'),10,-80,23),(13,1,-1,-80,23),(13,1,10,24,23)]:
            with self.assertRaises(ValueError):apply_limits(*args)
        for position in [[0,0,0],[1e-5,0,0],[float('inf'),0,0]]:
            with self.assertRaises(ValueError):delta_for(position,[100,0,0],[0,0,0])

    def test_attack_truth_is_excluded_from_detector_input(self):
        r=dict(tx_event_id=1,rx_event_id='0:1',rx_node_id=0,rx_time=.1,rx_xyz=[0,0,0],claimed_xyz=[100,0,0],rx_claimed_xyz=[100,0,0],claimed_timestamp=100,serial=1,rssi_dbm=-70,delivered=True,
               target_rx_id=0,requested_delta_db=-20,effective_phy_tx_dbm=-7,clamped_by_attack_bound=True,attack_case='schedule_aware')
        result=detector_projection([r],'opaque')[0]
        for key in ['target_rx_id','requested_delta_db','effective_phy_tx_dbm','clamped_by_attack_bound','attack_case']:
            self.assertNotIn(key,result)

    def test_native_math_header_compiles_and_checks_sign_limits_and_blind_api(self):
        compiler=shutil.which('c++')
        self.assertIsNotNone(compiler,'C++17 compiler is required for the original native math tests')
        header=Path(__file__).resolve().parents[1]/'native'
        source=r'''
#include "Issue75AttackMath.h"
#include <cassert>
int main() {
    using namespace issue75;
    Point p={10,0,0},q={100,0,0},r={0,0,0};
    assert(std::abs(compensation(p,q,r)+20)<1e-12);
    assert(std::abs(13+compensation(p,q,r)-20*std::log10(10.)-(13-20*std::log10(100.)))<1e-12);
    auto a=apply(20,15,10,-80,23);
    assert(a.attackClamped && a.phyClamped && a.power==23 && a.error==-12);
    bool rejected=false;try {compensation(r,q,r);} catch (std::invalid_argument&) {rejected=true;}
    assert(rejected);
    auto blind=blindCompensation(p,q,{r,{200,0,0}});
    assert(std::isfinite(blind));
    // There is no observer schedule/RX-feedback argument in blindCompensation.
}
'''
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'test.cc').write_text(source)
            built=subprocess.run([compiler,'-std=c++17','-I',str(header),str(root/'test.cc'),'-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            self.assertEqual(subprocess.run([str(root/'test')]).returncode,0)


if __name__=='__main__':unittest.main()
