import math,unittest
from evaluate import accuracy_codes,radii,distance_bounds,interval_decision,slant_bounds

class Tests(unittest.TestCase):
 def test_v0_accuracy_bytes(self):
  m=bytearray(25);m[0]=0x10;m[19]=0x4a;m[20]=0x40;m[23]=1
  self.assertEqual(accuracy_codes((bytes([0xf0,25,1])+m).hex()),[10,4,4,1])
 def test_unknown_not_zero_error(self):
  self.assertEqual(radii([0,0,0,0]),dict(horizontal_m=None,vertical_m=None,baro_m=None,time_s=None))
 def test_reserved_unknown(self):self.assertIsNone(radii([15,15,15,0])['horizontal_m'])
 def test_bad_version(self):
  with self.assertRaises(ValueError):accuracy_codes('f21900')
 def test_ambiguous_location(self):
  m=bytes([0x10])+bytes(24)
  with self.assertRaises(ValueError):accuracy_codes((bytes([0xf0,25,2])+m+m).hex())
 def test_codes_reported(self):self.assertEqual(radii([10,4,4,1]),dict(horizontal_m=10,vertical_m=10,baro_m=10,time_s=.1))
 def test_interval(self):self.assertEqual(distance_bounds(5,10),(0,15))
 def test_invalid_radius(self):
  with self.assertRaises(ValueError):distance_bounds(5,-1)
 def test_zero_nearfield_hold(self):self.assertEqual(interval_decision(-70,0,10,-30,2,5),'hold')
 def test_point(self):self.assertEqual(interval_decision(-50,10,10,-30,2,5),'consistent')
 def test_point_alarm(self):self.assertEqual(interval_decision(-70,10,10,-30,2,5),'alarm')
 def test_mixed_hold(self):self.assertEqual(interval_decision(-50,1,100,-30,2,5),'hold')
 def test_vertical_interval(self):
  lo,hi=slant_bounds(3,4,1,2)
  self.assertAlmostEqual(lo,math.sqrt(8));self.assertAlmostEqual(hi,math.sqrt(52))
 def test_height_sign_symmetry(self):self.assertEqual(slant_bounds(3,4,1,2),slant_bounds(3,-4,1,2))
 def test_degenerate_geometry(self):self.assertEqual(slant_bounds(0,0,0,0),(0,0))
 def test_larger_error_does_not_add_alarm(self):
  # Fixed row/model: enlarging the possible distance set cannot create a new alarm.
  for r in range(-100,-20):
   a=interval_decision(r,9,11,-30,2,5);b=interval_decision(r,5,15,-30,2,5)
   if b=='alarm':self.assertEqual(a,'alarm')
if __name__=='__main__':unittest.main()
