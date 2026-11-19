import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from plot_rssi_tracks import track_points,finite
from build_drone_android_3d import line_coordinates


class RssiTrackTests(unittest.TestCase):
    def row(self,t,height_type=0):
        return dict(mono=t,rssi=-60,payload='synthetic',key=str(t),reference=dict(
            claimed_latitude=0,claimed_longitude=0,claimed_altitude_geo_m=10,
            claimed_height_m=5,height_type=height_type))

    def test_gap_boundary_and_height_reference_change(self):
        points=track_points([self.row(1),self.row(61),self.row(122),self.row(123,1)],(0,0,10))
        self.assertEqual([p['segment'] for p in points],[1,1,2,3])
        x,y,z=line_coordinates(points,'geo_m',60)
        self.assertEqual(z,[10,10,None,10,None,10])

    def test_coordinate_reference_and_missing_rssi(self):
        rows=[self.row(1)];rows[0]['rssi']=None
        points=track_points(rows,(0,0,10))
        self.assertAlmostEqual(points[0]['east_m'],0)
        self.assertAlmostEqual(points[0]['north_m'],0)
        self.assertFalse(finite(points[0]['rssi_dbm']))
        self.assertFalse(finite(float('nan')))
        self.assertFalse(finite(True))

    def test_identical_audit_row_not_drawn_twice(self):
        row=self.row(1)
        self.assertEqual(len(track_points([row,dict(row)],(0,0,10))),1)


if __name__=='__main__':unittest.main()
