"""Dispatcher tests use fake tools and are explicitly not proof validation."""
import ast
import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import render
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'unified-distance-bench'))
from protocol import validate_samples

class DriverTests(unittest.TestCase):
    def test_archived_security_checks_retained(self):
        for framework,marker in [('circom','for(let i=0;i<cases.length;i++){'),('noir','for i,a in enumerate(CASES):')]:
            s,meta=render.render(framework)
            original=(render.ROOT/meta['archived_source']).read_text()
            self.assertEqual(s.split('for(let sample_id=' if framework=='circom' else 'for sample_id in')[0],original.split(marker)[0])
            for needle in (['native-invalid-witness','invalid_cases_rejected:6',"attempt.signal",'phase1_contributed','phase2_contributed','zkey_verified','negative_verifier_exit_code:1'] if framework=='circom' else ["'-t','evm'",'tampered proof: expected ordinary invalid-proof exit','changed public: expected ordinary invalid-proof exit',"command([nargo,'test']"]):
                self.assertIn(needle,s)
            self.assertIn('distance-u16-balanced-v1',s)
    def test_generated_syntax(self):
        ast.parse(render.render('noir')[0])
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'bench.cjs';p.write_text(render.render('circom')[0])
            subprocess.run(['node','--check',str(p)],check=True,capture_output=True)
    def test_noir_dispatch_and_tmpfs_cleanup_with_fake_tools(self):
        # Patch only the test's temporary-directory allocator. Production remains /dev/shm.
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);source=root/'source';source.mkdir()
            (source/'Nargo.toml').write_text('test fixture, not a circuit')
            tool=root/'tool';tool.write_text('''#!/usr/bin/env python3
import sys
from pathlib import Path
a=sys.argv[1:]
if '--version' in a:print('FAKE TOOL, NO CRYPTOGRAPHY');raise SystemExit(0)
if a[0]=='prove':
 out=Path(a[a.index('-o')+1]);out.mkdir();[(out/n).write_bytes(b'test bytes only') for n in ['proof','vk','public_inputs']]
if a[0]=='verify':
 raise SystemExit(1 if any('badproof' in x or 'badpublic' in x for x in a) else 0)
''');tool.chmod(0o700)
            driver=root/'bench.py';driver.write_text(render.render('noir')[0]);out=root/'log.jsonl'
            real=tempfile.TemporaryDirectory
            directories=[]
            def tmpdir(*args,**kwargs):
                self.assertEqual(kwargs['dir'],'/dev/shm')
                x=real(prefix='TEST-ONLY-',dir=root);directories.append(x.name);return x
            with out.open('w') as stream,patch.object(sys,'argv',[str(driver),str(source),str(tool),str(tool)]),patch.object(sys,'stdout',stream),patch.object(tempfile,'TemporaryDirectory',side_effect=tmpdir):
                runpy.run_path(str(driver),run_name='__main__')
            rows=[json.loads(s) for s in out.read_text().splitlines()]
            self.assertTrue(validate_samples([r for r in rows if r.get('phase')=='sample'],True))
            self.assertEqual(rows[-1]['samples'],21)
            self.assertTrue(all(not Path(p).exists() for p in directories))
            # These results must never be called actual Noir/Barretenberg proofs.
            self.assertIn('FAKE TOOL',rows[0]['nargo'])

if __name__=='__main__':unittest.main()
