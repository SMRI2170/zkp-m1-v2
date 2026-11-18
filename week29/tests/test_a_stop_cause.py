import ast,importlib.util,unittest,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
p=ROOT/'week29/scripts/analyze_a_stop_cause.py';sp=importlib.util.spec_from_file_location('cause',p);m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
class CauseTests(unittest.TestCase):
 def test_sensor_predicate_selects_inner_raise_and_strict_boundary(self):
  src="""
if now >= next_budget:
    files=[]
    if len(files)>10000 or sum(x.stat().st_size for x in files)>192*1024**2 or shutil.disk_usage(a.output).free<512*1024**2:
        raise RuntimeError('sensor capture budget/headroom reached')
"""
  expr,c=m.guard_expression(src,'sensor capture budget/headroom reached')
  def check(n):return eval(c,{'__builtins__':{}},dict(used_bytes=n,file_count=595,disk_free=9*1024**3))
  self.assertFalse(check(192*1024**2));self.assertTrue(check(192*1024**2+1));self.assertFalse(check(0))
 def test_tx_deployed_style_budget_keeps_disk_and_file_guards(self):
  # Pin the deployed pre-fix predicate used by the historical audit, not the repaired program.
  old=json.loads((ROOT/'week29/results/a-stop-cause/summary.json').read_text())
  expression=next(v['expression'] for v in old['guard_checks'] if v['kind']=='tx')
  s='if '+expression+": raise RuntimeError('TX capture budget/headroom reached')"
  _,c=m.guard_expression(s,'TX capture budget/headroom reached')
  def check(n,files=797,free=9*1024**3):return eval(c,{'__builtins__':{}},dict(used_bytes=n,file_count=files,disk_free=free))
  self.assertFalse(check(128*1024**2));self.assertTrue(check(128*1024**2+1));self.assertTrue(check(0,10001));self.assertTrue(check(0,1,1))
 def test_receiver_reservation_and_reason_priority(self):
  s=(ROOT/'experiments/week28-beacon-observers/boot_observer.py').read_text();f=next(n for n in ast.parse(s).body if isinstance(n,ast.FunctionDef) and n.name=='capacity');ns={'__builtins__':{}}
  exec(compile(ast.Module(body=[f],type_ignores=[]),'capacity-test','exec'),ns);c=ns['capacity'];mem=1024*1024;free=9*1024**3
  self.assertIsNone(c(None,mem,free,192*1024**2,100))
  self.assertEqual(c(None,mem,free,192*1024**2+1,100),'CAPTURE_BUDGET_REACHED')
  self.assertEqual(c(None,1,free,323*1024**2,100),'MEMORY_HEADROOM_LOW')
  self.assertEqual(c(None,mem,1,323*1024**2,100),'DISK_HEADROOM_LOW')
if __name__=='__main__':unittest.main()
