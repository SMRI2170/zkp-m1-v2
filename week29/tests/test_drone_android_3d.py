import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from build_drone_android_3d import line_coordinates,nearest,time_model


class AndroidReplayTests(unittest.TestCase):
    def test_marker_has_no_stale_position_or_extrapolation(self):
        points=[dict(time=10),dict(time=20)]
        self.assertIsNone(nearest(points,0))
        self.assertIsNone(nearest(points,15))
        self.assertEqual(nearest(points,12)['time'],10)
        self.assertIsNone(nearest([],10))

    def test_line_breaks_on_gap_and_segment_change(self):
        def p(t,segment):return dict(time=t,segment=segment,east_m=1,north_m=2,geo_m=3)
        xyz=line_coordinates([p(0,'a'),p(1,'a'),p(20,'a'),p(21,'b')],'geo_m',10)
        self.assertEqual(xyz[0],[1,1,None,1,None,1])
        self.assertEqual(len(xyz[0]),len(xyz[2]))

    def test_boot_and_clock_group_are_not_guessed(self):
        rows=[dict(node='test',clock_group='g',utc=100,mono=10,boot='fixture')]
        candidates=[dict(node='test',clock_group='g',offset_to_anchor_low_s=20,offset_to_anchor_high_s=22)]
        model=time_model('test',rows,candidates)
        self.assertEqual(model['origin'],90)
        self.assertEqual(model['offset'],21)
        self.assertEqual(model['boots'],{'fixture'})
        with self.assertRaises(ValueError):time_model('test',rows,candidates+candidates)


if __name__=='__main__':unittest.main()
