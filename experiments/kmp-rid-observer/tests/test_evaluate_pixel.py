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
