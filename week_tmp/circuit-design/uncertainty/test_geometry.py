import unittest
from geometry import ecef,enu,normalize_geometry,NotEvaluable
class Tests(unittest.TestCase):
 def setUp(self):
  self.o=dict(latitude=0.,longitude=0.,altitude_m=0.,altitude_datum='WGS84_ELLIPSOID',datum_verified=True)
  self.p=dict(self.o,horizontal_accuracy_m=1.,vertical_accuracy_m=2.)
 def test_origin(self):self.assertEqual(enu(self.p,self.o,0.),(0.,0.,0.))
 def test_ecef(self):self.assertEqual(ecef(0.,0.,0.),(6378137.,0.,0.))
 def test_ellipsoid_height(self):self.assertAlmostEqual(enu(self.p,self.o,10.)[2],10.)
 def test_2d_missing_altitude_allowed(self):
  p=dict(self.p);p.pop('altitude_m');p.pop('vertical_accuracy_m')
  r=normalize_geometry(p,p,self.o,2,projection_allowance_m=.02)
  self.assertEqual(r['receiver']['axis_error_cm'],[103,103,0])
 def test_3d(self):self.assertEqual(normalize_geometry(self.p,self.p,self.o,3,projection_allowance_m=0)['receiver']['axis_error_cm'],[101,101,201])
 def test_vertical_missing_blocks_3d(self):
  p=dict(self.p);p.pop('vertical_accuracy_m')
  with self.assertRaisesRegex(NotEvaluable,'VERTICAL_ACCURACY'):normalize_geometry(p,p,self.o,3,projection_allowance_m=0)
 def test_unverified_datum(self):
  p=dict(self.p,datum_verified=False)
  with self.assertRaisesRegex(NotEvaluable,'DATUM'):normalize_geometry(p,p,self.o,3,projection_allowance_m=0)
 def test_missing_allowance(self):
  with self.assertRaisesRegex(NotEvaluable,'ALLOWANCE'):normalize_geometry(self.p,self.p,self.o,2)
 def test_invalid_lat(self):
  with self.assertRaises(NotEvaluable):ecef(91,0,0)
 def test_outside_frame(self):
  with self.assertRaisesRegex(NotEvaluable,'OUTSIDE_LOCAL_FRAME'):normalize_geometry(dict(self.p,longitude=1),self.p,self.o,2,projection_allowance_m=0)
 def test_missing_horizontal(self):
  p=dict(self.p);p.pop('horizontal_accuracy_m')
  with self.assertRaisesRegex(NotEvaluable,'HORIZONTAL'):normalize_geometry(p,p,self.o,2,projection_allowance_m=0)
if __name__=='__main__':unittest.main()
