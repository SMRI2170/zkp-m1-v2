import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('pixel_eval',Path(__file__).parents[1]/'scripts/evaluate_pixel.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)

class EvaluationBoundaryTest(unittest.TestCase):
    def test_no_device_does_not_create_an_experiment(self):
        with patch.object(p.subprocess,'check_output',return_value='List of devices attached\n'), \
             patch.object(p.sys,'argv',['eval','--source-kind','unknown','--output','captures/not-created']), \
             patch.object(p,'private_output') as create:
            with self.assertRaisesRegex(RuntimeError,'Pixel 8'):p.main()
            create.assert_not_called()
    def test_other_android_is_never_selected(self):
        devices='List of devices attached\nfixture device usb:0 model:ASUS_Z017DA device:test\n'
        with patch.object(p.subprocess,'check_output',return_value=devices), \
             patch.object(p.sys,'argv',['eval','--source-kind','unknown','--output','captures/not-created']):
            with self.assertRaisesRegex(RuntimeError,'Pixel 8'):p.main()
    def test_capture_paths_reject_escape_and_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(p,'ROOT',Path(tmp)):
            root=Path(tmp);(root/'captures').mkdir(mode=0o700)
            with self.assertRaises(ValueError):p.private_output(root/'captures/../outside')
            (root/'captures/link').symlink_to(root,target_is_directory=True)
            with self.assertRaises(ValueError):p.private_output(root/'captures/link/run')
            out=p.private_output(root/'captures/new')
            self.assertEqual(out.stat().st_mode & 0o777,0o700)
            with self.assertRaises(FileExistsError):p.private_output(out)

class CleanupOutcomeTest(unittest.TestCase):
    def evaluate(self, cleanup_ok):
        class FakeDevice:
            def __init__(self, serial):self.ui_path='fixture-ui'
            def shell(self,*args):
                if args[:2]==('dumpsys','package'):
                    return 'android.permission.ACCESS_FINE_LOCATION: granted=true\nandroid.permission.POST_NOTIFICATIONS: granted=true'
                if args[:2]==('settings','get'):return '1'
                if args[:1]==('getprop',):return '36'
                if args[:1]==('run-as',):return '<map><string name="last_run">00000000-0000-0000-0000-000000000000</string></map>'
                return ''
            def tap(self,label):
                if label=='記録停止' and not cleanup_ok:raise RuntimeError('fixture locked')
            def time_us(self):return 1
            def copy(self,run,name,dest):dest.write_bytes(b'')
        with tempfile.TemporaryDirectory() as tmp,patch.object(p,'ROOT',Path(tmp)), \
             patch.object(p.subprocess,'check_output',return_value='fixture device usb:0 model:Pixel_8 device:test\n'), \
             patch.object(p,'Device',FakeDevice),patch.object(p.time,'sleep'), \
             patch.object(p.time,'monotonic',side_effect=[0,31,60,91,120,151]), \
             patch.object(p.sys,'argv',['eval','--source-kind','unknown','--phase-seconds','30','--output',str(Path(tmp)/'captures/run')]):
            if cleanup_ok:p.main()
            else:
                with self.assertRaisesRegex(RuntimeError,'stop is unconfirmed'):p.main()
            return p.json.loads((Path(tmp)/'captures/run/phases.json').read_text())
    def test_locked_cleanup_does_not_report_success(self):
        plan=self.evaluate(False)
        self.assertEqual(plan['completion'],'phases_completed_cleanup_unconfirmed')
        self.assertIn('unconfirmed',plan['cleanup'])
    def test_clean_shutdown_reports_completion(self):
        plan=self.evaluate(True)
        self.assertEqual(plan['completion'],'phases_completed')
        self.assertEqual(plan['cleanup'],'stopped_by_ui')
