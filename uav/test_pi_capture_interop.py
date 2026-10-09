import asyncio
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_v2_pi_capture_fixture import SESSION_KEY, _run_capture


class PiCaptureCallbackInteropTests(unittest.TestCase):
    def test_production_capture_callback_writes_one_grouped_private_message_pack_event(self):
        receive_ms = int(time.time() * 1000)
        with tempfile.TemporaryDirectory() as temp_dir:
            capture_path = Path(temp_dir) / "pi-capture.jsonl"
            key_path = Path(temp_dir) / "pi-session.key"
            key_path.write_bytes(SESSION_KEY)
            os.chmod(key_path, 0o600)

            status = asyncio.run(_run_capture(capture_path, key_path, receive_ms))

            self.assertEqual(status, 0)
            self.assertEqual(capture_path.stat().st_mode & 0o777, 0o600)
            records = [json.loads(line) for line in capture_path.read_text().splitlines()]
            starts = [row for row in records if row["record_type"] == "capture_start"]
            observations = [row for row in records if row["record_type"] == "observation"]
            ends = [row for row in records if row["record_type"] == "capture_end"]

            self.assertEqual(len(starts), 1)
            self.assertEqual(len(observations), 2)
            self.assertEqual(len(ends), 1)
            self.assertEqual({row["message_type"] for row in observations}, {"basic_id", "location"})
            self.assertEqual({row["capture_event_seq"] for row in observations}, {1})
            self.assertEqual({row["captured_at_unix_ms"] for row in observations}, {receive_ms})
            self.assertEqual({row["rssi_dbm"] for row in observations}, {-40})
            self.assertEqual(len({row["uas_id_tag"] for row in observations}), 1)
            self.assertTrue(all(row["raw_message_hex"] for row in observations))
            self.assertTrue(all("uas_id" not in row for row in observations))

            identity = {
                "run_id": "phone-interop-run-01",
                "observer_id": "pi-interop-01",
                "calibration_profile_id": 2,
                "uas_id_tag_scope": "shared_session_key_and_run_id",
            }
            for row in records:
                for field, value in identity.items():
                    self.assertEqual(row[field], value)
            self.assertEqual(starts[0]["observer_location"]["source"], "cli_asserted_unverified")
            self.assertEqual(ends[0]["captured"], 2)
            self.assertEqual(ends[0]["capture_event_count"], 1)


if __name__ == "__main__":
    unittest.main()
