import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('probe_summary',Path(__file__).parents[1]/'scripts/summarize_probe.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class PublicSummaryTests(unittest.TestCase):
    def fixture(self, root):
        s=dict(model='test phone',android='test',sdk=36,errors=[{'stage':'test','error':'Example','private_message':'DO_NOT_PUBLISH'}],
               capabilities={'ranging_api':{'recorded_elapsed_nanos':'DO_NOT_PUBLISH'}},targets=[dict(alias='DO_NOT_PUBLISH',estimate={'status':'INSUFFICIENT_ROTATION','peak_phone_heading_magnetic_deg':123})],
               wifi_rows_including_cache=1,wifi_information_elements=1,wifi_vendor_elements=1)
        (root/'summary.json').write_text(json.dumps(s));(root/'summary.json').chmod(0o600)
        event=dict(type='wifi_observation',fresh_broadcast=True,unique_timestamp=True,key='DO_NOT_PUBLISH',
                   ies=[dict(id=221,body_hex='DO_NOT_PUBLISH')])
        (root/'observations.jsonl').write_text(json.dumps(event)+'\n');(root/'observations.jsonl').chmod(0o600)
        (root/'fixture.apk').write_bytes(b'fake-test-apk')

    def test_only_aggregates_leave_private_capture(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);self.fixture(p);s=module.summarize(p,p/'fixture.apk')
            self.assertNotIn('DO_NOT_PUBLISH',json.dumps(s))
            self.assertNotIn('peak_phone_heading_magnetic_deg',json.dumps(s))
            self.assertEqual(s['fresh_unique_wifi_observations'],1)
            self.assertFalse(s['accuracy_established'])

    def test_public_read_rejects_world_readable_raw_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);self.fixture(p);(p/'observations.jsonl').chmod(0o644)
            with self.assertRaises(ValueError):module.summarize(p,p/'fixture.apk')

    def test_missing_installed_apk_hash_is_not_invented(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);self.fixture(p);s=module.summarize(p,p/'fixture.apk')
            self.assertIsNone(s['tested_apk'])


if __name__=='__main__':unittest.main()
