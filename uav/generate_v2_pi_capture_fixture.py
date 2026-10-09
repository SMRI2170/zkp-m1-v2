#!/usr/bin/env python3
"""Generate a disposable Pi capture through the production BLE callback.

This test-only fixture replaces Bleak's radio scanner with one synthetic
advertisement. Never use its fixed identifier, session key, or location for a
field run.
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import observer_capture


RUN_ID = "phone-interop-run-01"
OBSERVER_ID = "pi-interop-01"
PROFILE_ID = 2
SESSION_KEY = bytes([0x11]) * 32
UAS_ID = b"TEST-PHONE-001"


def _messages(receive_ms):
    basic = bytearray(25)
    basic[0] = 0x02  # Basic ID, protocol version 2
    basic[1] = 0x12  # ID type 1, UA type 2
    basic[2:2 + len(UAS_ID)] = UAS_ID

    location = bytearray(25)
    location[0] = 0x12  # Location, protocol version 2
    location[1] = 0x03
    location[5:9] = int(350000000).to_bytes(4, "little", signed=True)
    location[9:13] = int(1390000100).to_bytes(4, "little", signed=True)
    location[15:17] = int(2020).to_bytes(2, "little")  # 10 m geometric altitude
    location[21:23] = int((receive_ms % 3_600_000) // 100).to_bytes(2, "little")

    payload = bytes([0xF2, 25, 2]) + bytes(basic) + bytes(location)
    return payload


def _utc_millis(unix_ms):
    return datetime.fromtimestamp(unix_ms / 1000, timezone.utc).isoformat(
        timespec="milliseconds"
    ).replace("+00:00", "Z")


async def _run_capture(
    output_path,
    key_path,
    receive_ms,
    observer_id=OBSERVER_ID,
    profile_id=PROFILE_ID,
    observer_lon=139.000005,
    run_id=RUN_ID,
):
    advertisement_payload = _messages(receive_ms)

    class FakeDevice:
        address = "AA:BB:CC:DD:EE:FF"

    class FakeAdvertisement:
        rssi = -40
        service_data = {observer_capture.SERVICE_UUID: advertisement_payload}

    class FakeBleakScanner:
        def __init__(self, detection_callback, **_kwargs):
            self._detection_callback = detection_callback

        async def __aenter__(self):
            self._detection_callback(FakeDevice(), FakeAdvertisement())
            return self

        async def __aexit__(self, _exception_type, _exception, _traceback):
            return False

    bleak_stub = ModuleType("bleak")
    bleak_stub.BleakScanner = FakeBleakScanner
    args = argparse.Namespace(
        duration=0.001,
        output=str(output_path),
        run_id=run_id,
        observer_id=observer_id,
        calibration_profile_id=profile_id,
        session_key_file=str(key_path),
        observer_lat=35.0,
        observer_lon=observer_lon,
        observer_alt_m=10.0,
        include_raw=True,
    )
    with patch.dict(sys.modules, {"bleak": bleak_stub}), \
            patch.object(observer_capture.time, "time_ns", return_value=receive_ms * 1_000_000), \
            patch.object(observer_capture, "_utc_now", side_effect=lambda: _utc_millis(receive_ms)):
        return await observer_capture.capture(args)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("receive_ms", type=int)
    parser.add_argument("--observer-id", type=observer_capture.opaque_local_id, default=OBSERVER_ID)
    parser.add_argument("--profile-id", type=observer_capture.uint32_id, default=PROFILE_ID)
    parser.add_argument("--observer-lon", type=float, default=139.000005)
    parser.add_argument("--run-id", type=observer_capture.opaque_local_id, default=RUN_ID)
    args = parser.parse_args()
    if not args.output_dir.is_dir():
        parser.error("output_dir must already exist")
    if args.receive_ms < 0:
        parser.error("receive_ms must be nonnegative")

    key_path = args.output_dir / "pi-session.key"
    with key_path.open("xb") as key_file:
        os.chmod(key_path, 0o600)
        key_file.write(SESSION_KEY)
    capture_path = args.output_dir / "pi-capture.jsonl"
    if not -180 <= args.observer_lon <= 180:
        parser.error("observer longitude must be between -180 and 180")
    status = asyncio.run(_run_capture(
        capture_path,
        key_path,
        args.receive_ms,
        observer_id=args.observer_id,
        profile_id=args.profile_id,
        observer_lon=args.observer_lon,
        run_id=args.run_id,
    ))
    if status != 0:
        raise SystemExit(status)

    print(json.dumps({
        "capture_path": str(capture_path),
        "session_key_path": str(key_path),
        "run_id": args.run_id,
        "observer_id": args.observer_id,
        "calibration_profile_id": args.profile_id,
        "event_seq": 1,
        "window_start_unix_ms": args.receive_ms // 60_000 * 60_000,
        "window_end_unix_ms": (args.receive_ms // 60_000 + 1) * 60_000,
    }))


if __name__ == "__main__":
    main()
