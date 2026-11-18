import importlib.util,json,os,subprocess,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'uav'))
from observer_capture import parse_rid_payload
p=ROOT/'week29/scripts/analyze_b_snapshot.py';sp=importlib.util.spec_from_file_location('b_snapshot',p);m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
class ReferenceTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.binary=ROOT/'.cache/week29-odid-reference/decode'
  if not cls.binary.exists() and os.environ.get('WEEK29_REQUIRE_REFERENCE')=='1':raise RuntimeError('Required pinned reference decoder is missing')
  if not cls.binary.exists():raise unittest.SkipTest('Build the pinned optional OpenDroneID reference decoder before these integration tests')
 def packet(self,version):
  msg=bytes([version,0x12])+b'TEST-REFERENCE'.ljust(20,b'\0')+bytes(3)
  return bytes([0xf0|version,25,1])+msg
 def decode(self,pack):return m.reference_decode(self.binary,[pack.hex()])[0]
 def test_reference_v0_is_separate_from_production_admission(self):
  x=self.decode(self.packet(0));self.assertTrue(x['reference_decode_ok']);self.assertTrue(x['basic_id_valid']);self.assertFalse(x['identity_verified'])
  with self.assertRaisesRegex(ValueError,'protocol version'):parse_rid_payload(self.packet(0))
 def test_production_v2_still_decodes(self):
  self.assertTrue(self.decode(self.packet(2))['reference_decode_ok']);self.assertEqual(len(parse_rid_payload(self.packet(2))),1)
 def test_reference_rejects_truncated_bad_count_and_unknown_version(self):
  for packet in [self.packet(0)[:-1],bytes([0xf0,25,10])+bytes(250),self.packet(5),b'\xF0\x18\x01'+bytes(24)]:self.assertFalse(self.decode(packet)['reference_decode_ok'])
class AggregateTests(unittest.TestCase):
 def test_percentile_and_empty_intervals(self):
  self.assertIsNone(m.percentile([],.95));self.assertEqual(m.percentile([1,3,2],.5),2)
if __name__=='__main__':unittest.main()
