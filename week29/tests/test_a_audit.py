import contextlib,datetime as dt,importlib.util,io,json,sys,tempfile,unittest
from pathlib import Path
S=Path(__file__).resolve().parents[1]/'scripts/analyze_a_snapshot.py'
spec=importlib.util.spec_from_file_location('a_audit',S);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class AuditTests(unittest.TestCase):
 def test_timezones_and_invalid_time(self):
  self.assertEqual(m.stamp('2026-11-16T05:00:00Z'),m.START)
  self.assertIsNone(m.stamp('2026-11-16T14:00:00'))
  self.assertIsNone(m.stamp('not a date'))
 def test_window_dedup_missing_time_and_bad_json(self):
  with tempfile.TemporaryDirectory() as d:
   base=Path(d);r=base/'snapshot/releases/kit-509808cf5258-c838fbec/captures';r.mkdir(parents=True)
   sensor=r/'flight-sensors';sensor.mkdir()
   rows=[{'host_utc':'2026-11-16T05:00:00Z','gps':None}, {'host_utc':'2026-11-16T09:00:00Z'}]
   text='\n'.join(map(json.dumps,rows))+'\ninvalid-json\n'
   (sensor/'telemetry-1.jsonl').write_text(text);(sensor/'telemetry-copy.jsonl').write_text(text)
   tx=r/'flight-tx';tx.mkdir();(tx/'sent-1.jsonl').write_text(json.dumps({'host_monotonic_s':1,'sequence':1})+'\n')
   (base/'a-captures.tar.gz').write_bytes(b'test fixture for hashing only')
   old=sys.argv
   try:
    sys.argv=[str(S),'--input',str(base),'--output',str(base/'analysis')]
    with contextlib.redirect_stdout(io.StringIO()):m.main()
   finally:sys.argv=old
   s=json.loads((base/'analysis/summary.json').read_text())
   self.assertEqual(s['stats']['active/sensor']['rows'],2)
   self.assertEqual(s['stats']['active/sensor']['field_rows'],1) # end boundary is excluded
   self.assertEqual(s['stats']['active/sensor']['duplicate_files'],1)
   self.assertEqual(s['stats']['active/sensor']['invalid_json'],1)
   self.assertEqual(s['stats']['active/tx']['without_timestamp'],1)
   self.assertEqual(s['stats']['active/tx']['timestamped'],0)
if __name__=='__main__':unittest.main()
