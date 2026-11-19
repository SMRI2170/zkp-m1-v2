import json,os,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from capture_storage import CaptureSession,StorageLimit,MIN_FREE,MIB,limit_reason
from capture_health import health
from install_capture_indicator import unit_text
class SessionTests(unittest.TestCase):
 def test_exhausted_legacy_archive_other_roles_and_restarts_do_not_share_budget(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);old=root/'flight-sensors';old.mkdir(mode=0o700)
   p=old/'telemetry-old.jsonl';p.write_bytes(b'old data must survive');stamp=p.stat().st_mtime_ns
   sparse=old/'large-old-recording';sparse.touch()
   with sparse.open('wb') as f:f.truncate(2*1024**3)
   a=CaptureSession(old,root,'sensors',boot='test');self.addCleanup(a.close);(a.path/'data').write_bytes(b'first')
   with self.assertRaisesRegex(ValueError,'already running'):CaptureSession(old,root,'sensors',boot='test')
   a.close()
   b=CaptureSession(old,root,'sensors',boot='test');self.addCleanup(b.close);b.check()
   c=CaptureSession(root/'flight-tx',root,'transmitter',boot='test');self.addCleanup(c.close);c.check()
   self.assertNotEqual(a.path,b.path);self.assertEqual((a.path/'data').read_bytes(),b'first')
   self.assertEqual(p.read_bytes(),b'old data must survive');self.assertEqual(p.stat().st_mtime_ns,stamp)
   self.assertLess(b.last_used,1024*1024)
   for n in [a,b,c]:self.assertEqual(n.path.stat().st_mode&0o777,0o700);self.assertEqual(n.status_path.stat().st_mode&0o777,0o600)
 def test_session_cap_is_not_removed_and_exhaustion_is_visible(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);s=CaptureSession(root/'receiver',root,'receiver',budget=64*MIB);self.addCleanup(s.close)
   with (s.path/'large').open('wb') as f:f.truncate(64*MIB+1)
   with self.assertRaisesRegex(StorageLimit,'SESSION_BUDGET_REACHED'):s.check()
   self.assertEqual(json.loads(s.status_path.read_text())['state'],'SESSION_BUDGET_REACHED')
   self.assertTrue((s.path/'large').exists())
 def test_global_disk_reserve_applies_even_to_empty_new_sessions(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);s=CaptureSession(root/'sensors',root,'sensors',free_fn=lambda _:SimpleNamespace(free=MIN_FREE-1));self.addCleanup(s.close)
   with self.assertRaisesRegex(StorageLimit,'DISK_HEADROOM_LOW'):s.check()
  self.assertEqual(limit_reason(0,0,MIN_FREE+63*MIB,1024*MIB,64*MIB),'DISK_HEADROOM_LOW')
  self.assertEqual(limit_reason(0,10000,9*1024**3,1024*MIB),'SESSION_FILE_BUDGET_REACHED')
 def test_symlink_output_is_rejected_without_following_or_altering(self):
  with tempfile.TemporaryDirectory() as d,tempfile.TemporaryDirectory() as other:
   root=Path(d);(root/'sensors').symlink_to(other,target_is_directory=True)
   with self.assertRaises(ValueError):CaptureSession(root/'sensors',root,'sensors')
   self.assertEqual(list(Path(other).iterdir()),[])
 def test_indicator_requires_current_boot_and_fresh_writes(self):
  with tempfile.TemporaryDirectory() as d:
   now=[10.];root=Path(d);s=CaptureSession(root/'flight-sensors',root,'sensors',boot='boot-a',clock=lambda:now[0]);self.addCleanup(s.close);s.check();s.progress(1,force=True)
   self.assertEqual(health(root,['sensors'],now=10,boot='boot-a')['phase'],'ACTIVE')
   self.assertEqual(health(root,['sensors'],now=11,boot='boot-b')['phase'],'FAULT')
   self.assertEqual(health(root,['sensors'],now=45,boot='boot-a')['phase'],'FAULT')
   s.finish('SESSION_BUDGET_REACHED');self.assertEqual(health(root,['sensors'],now=11,boot='boot-a')['roles']['sensors']['reason'],'SESSION_BUDGET_REACHED')
 def test_led_service_has_no_radio_or_capture_write_permission(self):
  s=unit_text(Path('/home/pi/zkp-beacon-observer/releases/test'),Path('/sys/class/leds/ACT'),['receiver'])
  self.assertIn('PrivateNetwork=true',s);self.assertIn('ReadWritePaths=/sys/class/leds/ACT',s);self.assertNotIn('CAP_NET_ADMIN',s);self.assertNotIn('CAP_NET_RAW',s)
  with self.assertRaises(ValueError):unit_text(Path('/home/pi/zkp-beacon-observer/releases/test'),Path('/sys/class/leds/PWR'),['receiver'])
if __name__=='__main__':unittest.main()
