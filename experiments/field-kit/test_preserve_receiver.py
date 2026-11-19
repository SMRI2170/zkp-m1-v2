import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import time
import unittest
from unittest.mock import patch,MagicMock

import preserve_receiver as module
from preserve_receiver import collect,preserve,service_evidence,verify_archive


class ReceiverPreservationTests(unittest.TestCase):
    def fixture(self,d):
        root=Path(d).resolve();base=root/'source';out=root/'private';out.mkdir(mode=0o700)
        capture=base/'releases/old/captures/session';capture.mkdir(parents=True)
        data=capture/'observations.jsonl';data.write_bytes(b'{"synthetic":true}\n{"incomplete":')
        config=base/'config';config.mkdir();(config/'node.json').write_text('{"node_id":"observer-b"}')
        return base,out,data

    def test_full_preservation_retains_incomplete_tail_and_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            base,out,data=self.fixture(d);before=data.read_bytes();target=out/'copy.tar.gz'
            result=preserve(base,target,offline_copy=True)
            self.assertTrue(result['archive_verified']);self.assertFalse(result['live_preservation_verified'])
            self.assertEqual(result['files'],2);self.assertEqual(data.read_bytes(),before)
            manifest=verify_archive(target,time.monotonic()+10)
            self.assertEqual(manifest['files']['releases/old/captures/session/observations.jsonl']['sha256'],hashlib.sha256(before).hexdigest())
            with self.assertRaises(ValueError):preserve(base,target,offline_copy=True)

    def test_symlink_and_nested_backup_rejected_without_touching_source(self):
        with tempfile.TemporaryDirectory() as d:
            base,out,data=self.fixture(d)
            (data.parent/'bad').symlink_to(data)
            with self.assertRaises(ValueError):preserve(base,out/'copy.tar.gz',offline_copy=True)
            self.assertTrue(data.is_file());self.assertFalse((out/'copy.tar.gz').exists())
            (data.parent/'bad').unlink()
            with self.assertRaises(ValueError):preserve(base,data.parent/'copy.tar.gz',offline_copy=True)

    def test_membership_change_retains_failed_partial_not_final(self):
        with tempfile.TemporaryDirectory() as d:
            base,out,data=self.fixture(d);original=collect;calls=[]
            def collect_changed(*args):
                calls.append(True)
                if len(calls)>1:(data.parent/'arrived.jsonl').write_bytes(b'late synthetic data')
                return original(*args)
            with patch('preserve_receiver.collect',side_effect=collect_changed):
                with self.assertRaises(ValueError):preserve(base,out/'copy.tar.gz',offline_copy=True)
            self.assertTrue((out/'copy.tar.gz.partial').exists());self.assertFalse((out/'copy.tar.gz').exists())

    def test_active_or_unknown_service_refused(self):
        for state,pid in [('active','123'),('activating','0'),('inactive','123')]:
            response=MagicMock(stdout=f'ActiveState={state}\nMainPID={pid}\n')
            with patch('preserve_receiver.subprocess.run',return_value=response):
                with self.assertRaises(ValueError):service_evidence()

    def test_live_identity_mismatch_refused_before_probe(self):
        with tempfile.TemporaryDirectory() as d:
            base,out,data=self.fixture(d);probe=MagicMock()
            with self.assertRaises(ValueError):preserve(base,out/'copy.tar.gz',node_id='observer-c',probe=probe)
            probe.assert_not_called();self.assertFalse((out/'copy.tar.gz').exists())

    def malicious(self,out,entries):
        path=out/'malicious.tar.gz';body=b'synthetic'
        manifest=dict(format='rid_receiver_snapshot_v1',files={'releases/old/captures/test.jsonl':dict(bytes=len(body),sha256=hashlib.sha256(body).hexdigest())})
        with tarfile.open(path,'w:gz') as tar:
            data=json.dumps(manifest).encode();info=tarfile.TarInfo('snapshot-manifest.json');info.size=len(data);tar.addfile(info,io.BytesIO(data))
            for name,kind,content in entries:
                info=tarfile.TarInfo(name)
                if kind=='link':info.type=tarfile.SYMTYPE;info.linkname='/outside';tar.addfile(info)
                else:info.size=len(content);tar.addfile(info,io.BytesIO(content))
        return path

    def test_duplicate_link_missing_escape_and_hash_mismatch_archives_rejected(self):
        name='releases/old/captures/test.jsonl';body=b'synthetic'
        bad=[[],[(name,'link',b'')],[('../outside','file',body)],[(name,'file',body),(name,'file',body)],[(name,'file',b'corrupted')]]
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)
            for entries in bad:
                with self.assertRaises(ValueError):verify_archive(self.malicious(out,entries),time.monotonic()+10)

    def test_expired_deadline_has_no_final_archive(self):
        with tempfile.TemporaryDirectory() as d:
            base,out,data=self.fixture(d)
            with self.assertRaises(TimeoutError):collect(base,time.monotonic()-1)
            self.assertEqual(list(out.iterdir()),[])


if __name__=='__main__':unittest.main()
