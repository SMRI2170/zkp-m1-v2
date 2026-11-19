import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from build_drone_trajectory import ecef, enu, valid_location


class TrajectoryTests(unittest.TestCase):
    def test_wgs84_equator_and_pole(self):
        self.assertAlmostEqual(ecef(0,0,0)[0],6378137)
        self.assertAlmostEqual(ecef(90,0,0)[2],6356752.314245,places=5)

    def test_enu_origin_and_vertical(self):
        ref=(35,135,100)
        self.assertEqual(enu(*ref,ref),(0,0,0))
        east,north,up=enu(35,135,110,ref)
        self.assertAlmostEqual(east,0,places=6)
        self.assertAlmostEqual(north,0,places=6)
        self.assertAlmostEqual(up,10,places=6)

    def test_unknown_altitude_and_invalid_coordinate(self):
        d=dict(location_valid=True,claimed_latitude=35,claimed_longitude=135,claimed_altitude_geo_m=100)
        self.assertTrue(valid_location(d))
        self.assertFalse(valid_location(dict(d,claimed_altitude_geo_m=-1000)))
        self.assertFalse(valid_location(dict(d,claimed_latitude=91)))


if __name__=='__main__':unittest.main()
