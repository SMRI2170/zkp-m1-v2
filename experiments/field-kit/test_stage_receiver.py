import hashlib
import io
import json
from pathlib import Path
import subprocess
import os
import stat
import tarfile
import tempfile
import unittest
from unittest.mock import MagicMock

from preserve_receiver import preserve
from stage_receiver import stage


class ReceiverStageTests(unittest.TestCase):
    def fixture(self,d,offline=False):
        root=Path(d).resolve();base=root/'node';private=root/'private';private.mkdir(mode=0o700)
        old=base/'releases/old';capture=old/'captures';capture.mkdir(parents=True)
        (capture/'observations.jsonl').write_bytes(b'synthetic data, not RF evidence')
        (base/'config').mkdir();(base/'config/node.json').write_text('{"node_id":"observer-b"}')
        (base/'current').symlink_to('releases/old')
        probe=lambda:dict(service_properties={'ActiveState':'inactive','MainPID':'0'},unit_text='synthetic unit')
        archive=private/'copy.tar.gz';preserve(base,archive,node_id='observer-b',probe=probe,offline_copy=offline)
        kit=root/'kit';kit.mkdir();source=b'# synthetic code fixture\n';name='experiments/week28-beacon-observers/fixture.py'
        (kit/'install_pi.py').write_text('# mock installer only\n')
        with tarfile.open(kit/'pi-source.tar.gz','w:gz') as tar:
            info=tarfile.TarInfo(name);info.size=len(source);tar.addfile(info,io.BytesIO(source))
        sources={'pi':{name:hashlib.sha256(source).hexdigest()}}
        manifest=dict(format='rid_field_kit_v1',sources=sources,source_hash=hashlib.sha256(json.dumps(sources,sort_keys=True).encode()).hexdigest(),
            payloads={n:{'sha256':hashlib.sha256((kit/n).read_bytes()).hexdigest()} for n in ['install_pi.py','pi-source.tar.gz']})
        (kit/'manifest.json').write_text(json.dumps(manifest))
        def runner(argv,**kwargs):
            release=base/'releases/kit-staged'
            if argv[1].endswith('install_pi.py'):
                file=release/name;file.parent.mkdir(parents=True);file.write_bytes(source)
                return subprocess.CompletedProcess(argv,0,stdout='VERIFIED_STAGED_RELEASE '+str(release)+'\n',stderr='')
            return subprocess.CompletedProcess(argv,0,stdout='',stderr='synthetic test result')
        return base,archive,kit,probe,runner

    def test_offline_copy_never_authorizes_installation(self):
        with tempfile.TemporaryDirectory() as d:
            base,archive,kit,_,_=self.fixture(d,offline=True);runner=MagicMock();probe=MagicMock()
            with self.assertRaisesRegex(ValueError,'Offline copies'):stage(base,archive,kit,'observer-b',runner=runner,probe=probe)
            runner.assert_not_called();probe.assert_not_called()

    def test_source_change_blocks_stage_before_installer(self):
        with tempfile.TemporaryDirectory() as d:
            base,archive,kit,probe,_=self.fixture(d);runner=MagicMock()
            (base/'releases/old/captures/observations.jsonl').write_bytes(b'new synthetic row')
            with self.assertRaisesRegex(ValueError,'differs'):stage(base,archive,kit,'observer-b',runner=runner,probe=probe)
            runner.assert_not_called()

    def test_staging_never_activates_and_retains_current_and_old_data(self):
        with tempfile.TemporaryDirectory() as d:
            base,archive,kit,probe,implementation=self.fixture(d);runner=MagicMock(side_effect=implementation)
            before=(base/'releases/old/captures/observations.jsonl').read_bytes()
            result=stage(base,archive,kit,'observer-b',runner=runner,probe=probe)
            self.assertTrue(result['stage_verified']);self.assertFalse(result['activation_executed'])
            self.assertEqual((base/'current').readlink(),Path('releases/old'))
            self.assertEqual((base/'releases/old/captures/observations.jsonl').read_bytes(),before)
            for call in runner.call_args_list:self.assertNotIn('--activate',call.args[0]);self.assertNotIn('sudo',call.args[0])

    def test_test_failure_retains_partial_release_and_old_pointer(self):
        with tempfile.TemporaryDirectory() as d:
            base,archive,kit,probe,implementation=self.fixture(d)
            def failing(argv,**kwargs):
                if argv[1]=='-m':raise subprocess.CalledProcessError(1,argv,output='',stderr='synthetic failure')
                return implementation(argv,**kwargs)
            with self.assertRaises(subprocess.CalledProcessError):stage(base,archive,kit,'observer-b',runner=failing,probe=probe)
            self.assertTrue((base/'releases/kit-staged').is_dir())
            self.assertEqual((base/'current').readlink(),Path('releases/old'))

    def test_test_scratch_is_private_and_on_release_disk_not_system_tmpfs(self):
        with tempfile.TemporaryDirectory() as d:
            base,archive,kit,probe,implementation=self.fixture(d);seen=[]
            def inspect(argv,**kwargs):
                if argv[1]=='-m':
                    scratch=Path(kwargs['env']['TMPDIR']);seen.append(scratch)
                    self.assertEqual(scratch.parent,base/'releases/kit-staged')
                    self.assertEqual(scratch.stat().st_uid,os.getuid())
                    self.assertEqual(stat.S_IMODE(scratch.stat().st_mode),0o700)
                return implementation(argv,**kwargs)
            stage(base,archive,kit,'observer-b',runner=inspect,probe=probe)
            self.assertEqual(len(seen),1);self.assertFalse(seen[0].exists())

    def test_wrong_receiver_identity_and_changed_kit_are_held(self):
        with tempfile.TemporaryDirectory() as d:
            base,archive,kit,probe,_=self.fixture(d);runner=MagicMock()
            with self.assertRaisesRegex(ValueError,'identity'):stage(base,archive,kit,'observer-c',runner=runner,probe=probe)
            (kit/'install_pi.py').write_text('# modified fixture\n')
            with self.assertRaisesRegex(ValueError,'payload hash'):stage(base,archive,kit,'observer-b',runner=runner,probe=probe)
            runner.assert_not_called()


if __name__=='__main__':unittest.main()
