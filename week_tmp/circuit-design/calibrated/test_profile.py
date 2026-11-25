import json,random,unittest
from pathlib import Path
from profile import build,decision,continuous_oracle,geometry
ROOT=Path(__file__).resolve().parents[3]
class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.card=build(ROOT/'week29/results/issue96-attacks-a/summary.json')
 def test_frozen_profile_exact(self):self.assertEqual(self.card,json.loads((ROOT/'week_tmp/circuit-design/profiles/frozen-log-envelope-2d-v1.json').read_text()))
 def test_baseline_not_adopted(self):self.assertEqual(self.card['adoption'],'NOT_ADOPTED_REFERENCE_MODEL')
 def test_unsupported_range_holds(self):
  r=dict(claim=[10000,10000],observer=[10000,10000],receiver_radius_cm=0,claim_radius_cm=0,rssi=16000,eligible=True)
  self.assertEqual(decision(self.card,r),2)
 def test_unknown_input_holds(self):
  r=dict(claim=[10000,10000],observer=[9000,10000],receiver_radius_cm=0,claim_radius_cm=0,rssi=16000,eligible=False)
  self.assertEqual(decision(self.card,r),2)
 def test_false_definite_zero_on_500_samples(self):
  rng=random.Random(3206025);counts=[0,0,0]
  for _ in range(500):
   r=dict(claim=[10000,10000],observer=[10000-rng.randint(1,6000),10000],receiver_radius_cm=rng.randint(0,150),claim_radius_cm=rng.randint(0,100),rssi=rng.randint(6000,14000),eligible=True)
   envelope=decision(self.card,r);oracle=continuous_oracle(self.card,r);counts[envelope]+=1
   if envelope!=2:self.assertEqual(envelope,oracle)
  self.assertTrue(all(counts),counts)
 def test_interval_box(self):
  r=dict(claim=[10,20],observer=[0,0],receiver_radius_cm=1,claim_radius_cm=2)
  self.assertEqual(geometry(r),(7*7+17*17,13*13+23*23))
if __name__=='__main__':unittest.main()
