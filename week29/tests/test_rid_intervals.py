import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from audit_rid_intervals import analyze_group,time_status
from audit_field_time import clock_partitions


class RidIntervalTests(unittest.TestCase):
    def row(self,t,payload='aa',boot='fixture'):
        return dict(node='synthetic',utc=1000+t,mono=t,boot=boot,key=str(t),
                    bssid='fixture',frequency=1,digest=payload,payload=payload)

    def test_reused_observation_time_is_deduped_not_reception(self):
        a=self.row(1);b=self.row(3)
        values,unique,intervals,changes=analyze_group([a,dict(a),b])
        self.assertEqual(values['repeated_observation_keys'],1)
        self.assertEqual(values['consecutive_same_pack_rows'],1)
        self.assertEqual(intervals,[2]);self.assertEqual(changes,[])
        self.assertEqual(len(unique),2)

    def test_return_to_old_content_is_change_not_new_distinct_content(self):
        values,_,intervals,changes=analyze_group([self.row(1),self.row(2,'bb'),self.row(5)])
        self.assertEqual(values['distinct_pack_contents'],2)
        self.assertEqual(values['content_change_events'],3)
        self.assertEqual(changes,[1,3]);self.assertEqual(intervals,[1,3])

    def test_boot_and_clock_reset_never_bridge_intervals(self):
        rows=[self.row(1),self.row(3),self.row(1,boot='new'),self.row(2,boot='new')]
        # A reset in mono while calendar time advances changes UTC-minus-mono.
        reset=dict(self.row(.1),utc=1020)
        groups=clock_partitions(rows+[reset])
        self.assertEqual(len(groups),3)
        intervals=[v for _,_,_,g in groups for v in analyze_group(g)[2]]
        self.assertEqual(sorted(intervals),[1,2])

    def test_unknown_nonfinite_monotonic_is_held(self):
        base=dict(received_at_utc='2026-01-01T00:00:00Z',monotonic_time_us=1)
        self.assertEqual(time_status(base),'ELIGIBLE_TIME')
        for value in [None,0,-1,True,float('nan'),float('inf')]:
            self.assertEqual(time_status(dict(base,monotonic_time_us=value)),'MONOTONIC_UNKNOWN')
        self.assertEqual(time_status(dict(base,received_at_utc='bad')),'UTC_UNKNOWN')

    def test_different_sender_streams_do_not_form_intervals(self):
        rows=[self.row(1),dict(self.row(2),bssid='other')]
        values,_,intervals,_=analyze_group(rows)
        self.assertEqual(intervals,[])
        self.assertEqual(values['content_change_events'],2)


if __name__=='__main__':unittest.main()
