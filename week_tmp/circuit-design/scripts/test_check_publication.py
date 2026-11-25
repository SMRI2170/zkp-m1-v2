import json,tempfile,unittest
from pathlib import Path
from check_publication import check
class Tests(unittest.TestCase):
 def test_public_summary(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'summary.json').write_text(json.dumps({'rows':27,'proof_generated':False,'public_fields':['Core_Claim_0']}));self.assertEqual(check(p),[])
 def test_capture_values(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'raw.json').write_text(json.dumps({'receiver_latitude':.1}));self.assertTrue(check(p))
 def test_count_not_coordinate(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'summary.json').write_text(json.dumps({'fix_nonnull':{'latitude':100}}));self.assertEqual(check(p),[])
   (p/'summary.json').write_text(json.dumps({'fix_nonnull':{'latitude':.1}}));self.assertTrue(check(p))
 def test_private_artifacts(self):
  for name in ['x.jsonl','x.proof','x.vk','x-private.csv','ledger.json','db.sqlite-wal']:
   with tempfile.TemporaryDirectory() as d:
    p=Path(d);(p/name).write_text('{}');self.assertTrue(check(p),name)
if __name__=='__main__':unittest.main()
