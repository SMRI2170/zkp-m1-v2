import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from audit_android_position import association,eligible,fix_key,movement,valid_fix


class AndroidPositionAuditTests(unittest.TestCase):
    def fixture(self):
        fix=dict(latitude=0.0,longitude=0.0,accuracy_m=3.0,fix_elapsed_us=10_000_000,
                 provider='fixture',mock=False,match_status='MATCHED',scan_delta_us=0,boot_scope='boot-a')
        row=dict(boot_scope='boot-a',cache_stale=False,monotonic_time_us=10_000_000,receiver_position=fix)
        return row,{fix_key('boot-a',fix):[dict(fix)]}

    def test_missing_stale_and_unknown_freshness(self):
        row,index=self.fixture()
        self.assertEqual(association(row,index),'ELIGIBLE_TIME_POSITION')
        self.assertEqual(association(dict(row,cache_stale=True),index),'STALE_WIFI_OBSERVATION')
        self.assertEqual(association(dict(row,cache_stale=None),index),'WIFI_FRESHNESS_UNKNOWN')
        self.assertEqual(association(dict(row,receiver_position=None),index),'POSITION_MISSING')

    def test_boot_or_fix_content_mismatch_is_held(self):
        row,index=self.fixture()
        self.assertEqual(association(dict(row,boot_scope='boot-b'),index),'STANDALONE_FIX_MISSING_OR_AMBIGUOUS')
        self.assertEqual(association(dict(row,boot_scope=''),index),'BOOT_UNKNOWN')
        fix=dict(row['receiver_position'],latitude=.1)
        self.assertEqual(association(dict(row,receiver_position=fix),index),'FIX_CONTENT_MISMATCH')

    def test_delta_boundary_invalid_accuracy_and_mock(self):
        row,index=self.fixture();fix=dict(row['receiver_position'],fix_elapsed_us=12_000_000,scan_delta_us=2_000_000)
        index={fix_key('boot-a',fix):[fix]}
        self.assertEqual(association(dict(row,receiver_position=fix),index),'ELIGIBLE_TIME_POSITION')
        fix=dict(fix,fix_elapsed_us=12_000_001)
        self.assertEqual(association(dict(row,receiver_position=fix),index),'DELTA_OVER_2_SECONDS')
        self.assertFalse(valid_fix(dict(fix,accuracy_m=float('nan'))))
        self.assertFalse(valid_fix(dict(fix,latitude=91)))
        self.assertEqual(association(dict(row,receiver_position=dict(fix,mock=True)),index),'MOCK_OR_UNKNOWN')

    def test_ratio_and_zero_distance(self):
        self.assertTrue(eligible('ELIGIBLE_TIME_POSITION',20,5,5,.25))
        self.assertFalse(eligible('ELIGIBLE_TIME_POSITION',0,0,5,.25))
        self.assertFalse(eligible('BOOT_UNKNOWN',20,5,5,.25))
        self.assertFalse(eligible('ELIGIBLE_TIME_POSITION',10,5,5,.25))

    def test_nonfinite_observation_clock_is_held(self):
        row,index=self.fixture()
        for invalid in [float('nan'),float('inf'),True]:
            self.assertEqual(association(dict(row,monotonic_time_us=invalid),index),'OBSERVED_TIME_UNKNOWN')

    def test_movement_never_bridges_boot_or_long_gap(self):
        row,_=self.fixture();a=row['receiver_position']
        fixes=[a,dict(a,fix_elapsed_us=11_000_000),dict(a,fix_elapsed_us=100_000_000),
               dict(a,boot_scope='boot-b',fix_elapsed_us=101_000_000)]
        intervals,steps,speeds,gaps=movement(fixes)
        self.assertEqual(intervals,[1,89]);self.assertEqual(len(steps),1)
        self.assertEqual(speeds,[0]);self.assertEqual(gaps,1)


if __name__=='__main__':unittest.main()
