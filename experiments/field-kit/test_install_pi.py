import hashlib
import io
from pathlib import Path
import tarfile
import tempfile
import unittest
from install_pi import verified_members,main
from unittest.mock import patch
from contextlib import redirect_stderr


class BundleTests(unittest.TestCase):
    def test_dual_role_rejects_non_a_before_accessing_bundle(self):
        with patch('sys.argv',['install_pi.py','--kit','/unused','--node-id','observer-d','--role','dual']),patch('install_pi.os.getuid',return_value=1000),redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error:main()
        self.assertEqual(error.exception.code,2)

    def archive(self,d,name,data=b'fixture',link=False):
        p=Path(d)/'fixture.tar.gz'
        with tarfile.open(p,'w:gz') as tar:
            item=tarfile.TarInfo(name);item.size=len(data)
            if link:item.type=tarfile.SYMTYPE;item.linkname='/tmp/outside'
            tar.addfile(item,None if link else io.BytesIO(data))
        return p
    def test_verified_exact_set_and_no_path_escape(self):
        with tempfile.TemporaryDirectory() as d:
            digest=hashlib.sha256(b'fixture').hexdigest()
            p=self.archive(d,'uav/fixture.py')
            self.assertEqual(verified_members(p,{'uav/fixture.py':digest}),{'uav/fixture.py':b'fixture'})
            with self.assertRaises(ValueError):verified_members(p,{'uav/fixture.py':'wrong'})
            with self.assertRaises(ValueError):verified_members(p,{'uav/fixture.py':digest,'missing.py':digest})
            for name,link in [('../outside.py',False),('/outside.py',False),('uav/link.py',True)]:
                p=self.archive(d,name,link=link)
                with self.assertRaises(ValueError):verified_members(p,{name:digest})


if __name__=='__main__':unittest.main()
