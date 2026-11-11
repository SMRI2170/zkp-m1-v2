#!/usr/bin/env python3
"""Local BLE capture for evaluating Remote ID observer measurements.

This records received RSSI and decodes Basic ID / Location fields plus
OpenDroneID Authentication page framing. Authentication payloads are preserved
as page data but are not assembled or cryptographically verified. The tool does
not authenticate a Remote ID broadcast, attest an observer, or create a proof.
Raw BLE addresses and UAS IDs are pseudonymized with a per-run secret; the
secret is intentionally not written to disk.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import hmac
import json
import math
import os
import re
import secrets
import stat
import sys
import time
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


SERVICE_UUID = "0000fffa-0000-1000-8000-00805f9b34fb"
MESSAGE_SIZE = 25
PROTOCOL_VERSION = 2
MAX_AUTH_PAGES = 16
AUTH_PAGE_ZERO_DATA_SIZE = 17
AUTH_PAGE_DATA_SIZE = 23
MESSAGE_PACK_TYPE = 0x0F
MESSAGE_PACK_HEADER_SIZE = 3
MAX_PACK_MESSAGES = 9
OPAQUE_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")


@dataclass(frozen=True)
class RidMessage:
    message_type: str
    protocol_version: int
    message_type_id: Optional[int] = None
    id_type: Optional[int] = None
    ua_type: Optional[int] = None
    uas_id: Optional[str] = None
    latitude_deg: Optional[float] = None
    longitude_deg: Optional[float] = None
    altitude_geo_m: Optional[float] = None
    rid_timestamp_raw: Optional[int] = None
    rid_seconds_within_hour: Optional[float] = None
    auth_type: Optional[int] = None
    auth_data_page: Optional[int] = None
    auth_last_page_index: Optional[int] = None
    auth_length: Optional[int] = None
    auth_timestamp_2019: Optional[int] = None
    auth_data_hex: Optional[str] = None
    message_pack_index: Optional[int] = None
    message_pack_size: Optional[int] = None


def parse_service_uuid(value: str) -> Optional[str]:
    """Normalize Bleak's UUID key (also accepting the 16-bit form 0xFFFA)."""
    normalized = value.strip().lower().strip("{}")
    if normalized.startswith("0x"):
        normalized = normalized[2:]
    normalized = normalized.replace("-", "")
    if len(normalized) == 4:
        normalized = "0000" + normalized + "00001000800000805f9b34fb"
    if len(normalized) != 32:
        return None
    return "-".join((normalized[0:8], normalized[8:12], normalized[12:16],
                     normalized[16:20], normalized[20:32]))


def parse_rid_message(raw: bytes) -> RidMessage:
    """Decode selected 25-byte ASTM/OpenDroneID fields and auth-page framing.

    Authentication data is returned page-by-page; this function does not
    reassemble pages, validate FEC, or verify DRIP signatures/trust chains.
    Unsupported message types/versions and malformed fields raise ValueError.
    """
    if len(raw) != MESSAGE_SIZE:
        raise ValueError("message must be exactly 25 bytes")

    message_type_id = (raw[0] >> 4) & 0x0F
    version = raw[0] & 0x0F
    if version != PROTOCOL_VERSION:
        raise ValueError("unsupported protocol version")

    if message_type_id == 0:  # Basic ID
        id_type = (raw[1] >> 4) & 0x0F
        ua_type = raw[1] & 0x0F
        uas_id_bytes = raw[2:22].split(b"\x00", 1)[0]
        try:
            uas_id = uas_id_bytes.decode("ascii", errors="strict").strip()
        except UnicodeDecodeError as exc:
            raise ValueError("Basic ID is not ASCII") from exc
        return RidMessage(
            message_type="basic_id",
            protocol_version=version,
            message_type_id=message_type_id,
            id_type=id_type,
            ua_type=ua_type,
            uas_id=uas_id or None,
        )

    if message_type_id == 1:  # Location
        latitude = int.from_bytes(raw[5:9], "little", signed=True) / 10_000_000
        longitude = int.from_bytes(raw[9:13], "little", signed=True) / 10_000_000
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            raise ValueError("Location coordinates are outside valid bounds")

        altitude_raw = int.from_bytes(raw[15:17], "little", signed=False)
        timestamp_raw = int.from_bytes(raw[21:23], "little", signed=False)
        timestamp_seconds = None
        if timestamp_raw != 0xFFFF:
            timestamp_seconds = timestamp_raw / 10
            if timestamp_seconds >= 3600:
                raise ValueError("Location timestamp is outside the hour")

        return RidMessage(
            message_type="location",
            protocol_version=version,
            message_type_id=message_type_id,
            latitude_deg=latitude,
            longitude_deg=longitude,
            altitude_geo_m=None if altitude_raw == 0xFFFF else altitude_raw * 0.5 - 1000,
            rid_timestamp_raw=None if timestamp_raw == 0xFFFF else timestamp_raw,
            rid_seconds_within_hour=timestamp_seconds,
        )

    if message_type_id == 2:  # Authentication page
        auth_data_page = raw[1] & 0x0F
        auth_type = (raw[1] >> 4) & 0x0F
        if auth_data_page == 0:
            last_page_index = raw[2]
            auth_length = raw[3]
            if last_page_index >= MAX_AUTH_PAGES:
                raise ValueError("authentication last page index is out of range")
            max_auth_bytes = AUTH_PAGE_ZERO_DATA_SIZE + last_page_index * AUTH_PAGE_DATA_SIZE
            if auth_length > max_auth_bytes:
                raise ValueError("authentication length exceeds declared page capacity")
            return RidMessage(
                message_type="authentication",
                protocol_version=version,
                message_type_id=message_type_id,
                auth_type=auth_type,
                auth_data_page=auth_data_page,
                auth_last_page_index=last_page_index,
                auth_length=auth_length,
                auth_timestamp_2019=int.from_bytes(raw[4:8], "little"),
                auth_data_hex=raw[8:25].hex(),
            )

        return RidMessage(
            message_type="authentication",
            protocol_version=version,
            message_type_id=message_type_id,
            auth_type=auth_type,
            auth_data_page=auth_data_page,
            auth_data_hex=raw[2:25].hex(),
        )

    # Preserve the message type for other assigned F3411 messages so callers
    # can opt into storing the raw bytes for a later DRIP evidence check.
    simple_message_types = {
        3: "self_id",
        4: "system",
        5: "operator_id",
    }
    if message_type_id in simple_message_types:
        return RidMessage(
            message_type=simple_message_types[message_type_id],
            protocol_version=version,
            message_type_id=message_type_id,
        )

    raise ValueError("unsupported Remote ID message type")


def parse_rid_payload(raw: bytes) -> list[tuple[bytes, RidMessage]]:
    """Decode one legacy ASTM message or an extended-transport Message Pack.

    A pack contains a three-byte header followed by 1..9 fixed 25-byte
    messages. Return each original 25-byte message so raw signatures/hashes can
    be rechecked without confusing the pack envelope with signed message bytes.
    """
    if len(raw) == MESSAGE_SIZE:
        return [(raw, parse_rid_message(raw))]
    if not raw:
        raise ValueError("payload must not be empty")

    message_type_id = (raw[0] >> 4) & 0x0F
    version = raw[0] & 0x0F
    if message_type_id != MESSAGE_PACK_TYPE:
        raise ValueError("message must be a 25-byte RID message or Message Pack")
    if version != PROTOCOL_VERSION:
        raise ValueError("unsupported message pack protocol version")
    if len(raw) < MESSAGE_PACK_HEADER_SIZE:
        raise ValueError("message pack header is truncated")

    single_message_size = raw[1]
    message_count = raw[2]
    if single_message_size != MESSAGE_SIZE:
        raise ValueError("message pack single message size must be 25")
    if not 1 <= message_count <= MAX_PACK_MESSAGES:
        raise ValueError("message pack count is out of range")
    expected_length = MESSAGE_PACK_HEADER_SIZE + single_message_size * message_count
    if len(raw) != expected_length:
        raise ValueError("message pack length does not match declared count")

    decoded: list[tuple[bytes, RidMessage]] = []
    for index in range(message_count):
        start = MESSAGE_PACK_HEADER_SIZE + index * single_message_size
        message_bytes = raw[start:start + single_message_size]
        message = parse_rid_message(message_bytes)
        message = replace(
            message,
            message_pack_index=index,
            message_pack_size=message_count,
        )
        decoded.append((message_bytes, message))
    return decoded


def ephemeral_tag(session_key: bytes, domain: str, value: str, context: str = "") -> str:
    """Return a context- and domain-separated pseudonym."""
    parts = [part.encode("utf-8") for part in (domain, context, value)]
    message = b"signal.observer-tag.v1" + b"".join(
        len(part).to_bytes(4, "big") + part for part in parts
    )
    digest = hmac.new(session_key, message, hashlib.sha256)
    return digest.hexdigest()[:24]


def session_salt_from_key(session_key: bytes, run_id: str) -> int:
    """Derive the private 248-bit V2 RID-commitment salt for one run."""
    if len(session_key) != 32:
        raise ValueError("session key must contain exactly 32 bytes")
    if not OPAQUE_ID_PATTERN.fullmatch(run_id):
        raise ValueError("run_id must be a bounded opaque ASCII identifier")
    message = b"signal.observer-circuit-salt.v2\x00" + run_id.encode("ascii")
    salt = int.from_bytes(hmac.new(session_key, message, hashlib.sha256).digest()[:31], "big")
    if salt == 0:
        raise ValueError("derived session salt must not be zero")
    return salt


def load_session_key_file(path: str | Path) -> bytes:
    """Load an exact 32-byte owner-private key without following symlinks."""
    key_path = Path(path).expanduser()
    nofollow = getattr(os, "O_NOFOLLOW", None)
    if nofollow is None:
        raise ValueError("this platform cannot safely reject symlinked session-key files")
    try:
        fd = os.open(str(key_path), os.O_RDONLY | nofollow)
    except OSError as exc:
        raise ValueError("session-key file cannot be safely opened") from exc

    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("session-key file must be a regular file")
        mode = stat.S_IMODE(info.st_mode)
        if mode & ~0o600 or not mode & 0o400:
            raise ValueError("session-key file must be owner-readable and no broader than mode 0600")
        if hasattr(os, "geteuid") and info.st_uid != os.geteuid():
            raise ValueError("session-key file must be owned by the current user")

        data = bytearray()
        while len(data) <= 32:
            try:
                chunk = os.read(fd, 33 - len(data))
            except OSError as exc:
                raise ValueError("session-key file could not be read") from exc
            if not chunk:
                break
            data.extend(chunk)
        if len(data) != 32:
            raise ValueError("session-key file must contain exactly 32 raw bytes")
        return bytes(data)
    finally:
        os.close(fd)


def message_fields_for_log(message: RidMessage) -> Dict[str, Any]:
    """Return decoded fields without persisting the broadcast UAS identifier."""
    fields = asdict(message)
    fields.pop("uas_id", None)
    return fields


def opaque_local_id(value: str) -> str:
    """Validate a bounded local pseudonym; callers must not supply real names."""
    if not OPAQUE_ID_PATTERN.fullmatch(value):
        raise argparse.ArgumentTypeError(
            "must be 1..64 ASCII letters/digits/dot/underscore/hyphen and start alphanumeric"
        )
    return value


def uint32_id(value: str) -> int:
    if not re.fullmatch(r"(?:0|[1-9][0-9]*)", value):
        raise argparse.ArgumentTypeError("must be a canonical decimal uint32")
    try:
        parsed = int(value, 10)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a canonical decimal uint32") from exc
    if parsed < 0 or parsed > 0xFFFFFFFF:
        raise argparse.ArgumentTypeError("must be a canonical decimal uint32")
    return parsed


def capture_identity_fields(args: argparse.Namespace, shared_session_key: bool = False) -> Dict[str, Any]:
    return {
        "run_id": args.run_id,
        "observer_id": args.observer_id,
        "calibration_profile_id": args.calibration_profile_id,
        "uas_id_tag_scope": (
            "shared_session_key_and_run_id" if shared_session_key else "process_local_key_and_run_id"
        ),
    }


def attach_capture_identity(record: Dict[str, Any], identity: Dict[str, Any]) -> Dict[str, Any]:
    return {
        **record,
        "schema": "signal.observer-capture.v1",
        **identity,
    }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _open_private_new_file(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(str(path), flags, 0o600)
    try:
        os.chmod(path, 0o600)
    except OSError:
        os.close(fd)
        raise
    return os.fdopen(fd, "w", encoding="utf-8", buffering=1)


async def capture(args: argparse.Namespace) -> int:
    try:
        shared_session_key = (
            load_session_key_file(args.session_key_file) if args.session_key_file else None
        )
    except ValueError as exc:
        print("Invalid session-key file: {}".format(exc), file=sys.stderr)
        return 2

    try:
        from bleak import BleakScanner
    except ImportError:
        print("BLE scanner dependency missing. Install it with: python3 -m pip install bleak", file=sys.stderr)
        return 2

    output_path = Path(args.output).expanduser()
    try:
        output = _open_private_new_file(output_path)
    except FileExistsError:
        print("Output already exists; choose a new file (existing logs are never overwritten).", file=sys.stderr)
        return 2
    except OSError as exc:
        print("Cannot create private output file: {}".format(exc), file=sys.stderr)
        return 2

    process_key = secrets.token_bytes(32)
    uas_tag_key = shared_session_key or process_key
    address_to_uas_tag: Dict[str, str] = {}
    stats: Dict[str, Any] = {
        "captured": 0,
        "capture_event_count": 0,
        "authentication_page_records": 0,
        "unsupported_or_malformed": 0,
    }
    capture_event_sequence = 0
    capture_identity = capture_identity_fields(args, shared_session_key is not None)
    observer_location = None
    if args.observer_lat is not None:
        observer_location = {
            "latitude_deg": args.observer_lat,
            "longitude_deg": args.observer_lon,
            "altitude_m": args.observer_alt_m,
            "source": "cli_asserted_unverified",
        }

    def write_record(record: Dict[str, Any]) -> None:
        record = attach_capture_identity(record, capture_identity)
        output.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
        output.flush()

    write_record({
        **capture_identity,
        "schema": "signal.observer-capture.v1",
        "record_type": "capture_start",
        "captured_at_utc": _utc_now(),
        "duration_seconds": args.duration,
        "transport": "BLE",
        "service_uuid": SERVICE_UUID,
        "authentication_status": "not_evaluated",
        "observer_location": observer_location,
        "raw_payload_included": bool(args.include_raw),
    })

    def on_detection(device: Any, advertisement: Any) -> None:
        nonlocal capture_event_sequence
        advertiser_address = str(device.address)
        # Keep BLE-address pseudonyms local to this process even when UAS ID
        # correlation is explicitly enabled across observers.
        address_tag = ephemeral_tag(process_key, "ble-address", advertiser_address, args.run_id)
        service_payloads = [
            payload for uuid, payload in advertisement.service_data.items()
            if parse_service_uuid(uuid) == SERVICE_UUID
        ]
        for payload in service_payloads:
            try:
                parsed_messages = parse_rid_payload(bytes(payload))
            except ValueError:
                stats["unsupported_or_malformed"] += 1
                continue

            capture_event_sequence += 1
            stats["capture_event_count"] += 1
            event_time_ns = time.time_ns()
            event_time_utc = _utc_now()
            for message_bytes, parsed in parsed_messages:
                uas_tag = address_to_uas_tag.get(advertiser_address)
                if parsed.message_type == "basic_id" and parsed.uas_id:
                    typed_uas_id = "{}:{}:{}".format(parsed.id_type, parsed.ua_type, parsed.uas_id)
                    uas_tag = ephemeral_tag(uas_tag_key, "uas-id", typed_uas_id, args.run_id)
                    address_to_uas_tag[advertiser_address] = uas_tag

                record: Dict[str, Any] = {
                    **capture_identity,
                    "schema": "signal.observer-capture.v1",
                    "record_type": "observation",
                    "captured_at_utc": event_time_utc,
                    "captured_at_unix_ms": event_time_ns // 1_000_000,
                    "capture_event_seq": capture_event_sequence,
                    "transport": "BLE",
                    "service_uuid": SERVICE_UUID,
                    "rssi_dbm": int(advertisement.rssi),
                    "advertiser_tag": address_tag,
                    "uas_id_tag": uas_tag,
                    "authentication_status": "not_evaluated",
                    "capture_scope": "single_observer_local_test",
                    "observer_location": observer_location,
                    **message_fields_for_log(parsed),
                }
                if args.include_raw:
                    record["raw_message_hex"] = message_bytes.hex()
                    if len(payload) != MESSAGE_SIZE:
                        record["raw_message_pack_hex"] = bytes(payload).hex()
                write_record(record)
                stats["captured"] += 1
                if parsed.message_type == "authentication":
                    stats["authentication_page_records"] += 1

    # BlueZ's DuplicateData filter asks BlueZ to forward duplicate advertisement
    # data as well. Hardware/controller-level duplicate filtering can still apply.
    scanner = BleakScanner(
        detection_callback=on_detection,
        service_uuids=[SERVICE_UUID],
        bluez={"filters": {"DuplicateData": True}},
    )
    try:
        async with scanner:
            await asyncio.sleep(args.duration)
    except KeyboardInterrupt:
        print("Capture interrupted; writing the records collected so far.", file=sys.stderr)
    except Exception as exc:
        write_record({"schema": "signal.observer-capture.v1", "record_type": "capture_error",
                      "captured_at_utc": _utc_now(), "error_type": type(exc).__name__,
                      "message": str(exc)[:300]})
        print("BLE scan failed: {}".format(exc), file=sys.stderr)
        output.close()
        return 1

    write_record({"schema": "signal.observer-capture.v1", "record_type": "capture_end",
                  **capture_identity, "captured_at_utc": _utc_now(), **stats,
                  "notes": ["RSSI is receiver-reported and environment-dependent.",
                            "Parsing does not establish Remote ID authenticity or observer attestation."]})
    output.close()
    print("Saved {} observations to {} (mode 0600).".format(stats["captured"], output_path))
    if stats["unsupported_or_malformed"]:
        print("Ignored {} unsupported or malformed Remote ID payloads.".format(
            stats["unsupported_or_malformed"]), file=sys.stderr)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Capture local BLE Remote ID RSSI observations as private JSONL.")
    parser.add_argument("--duration", type=float, default=60,
                        help="capture duration in seconds (default: 60)")
    parser.add_argument("--output", required=True, help="new JSONL output file; existing file is not overwritten")
    parser.add_argument("--run-id", required=True, type=opaque_local_id,
                        help="shared opaque ID for the same field session across all observer nodes")
    parser.add_argument("--observer-id", required=True, type=opaque_local_id,
                        help="stable local pseudonym for this receiver; reuse across its calibration/evaluation runs")
    parser.add_argument("--calibration-profile-id", required=True, type=uint32_id,
                        help="decimal uint32 ID for the immutable receiver/calibration record")
    parser.add_argument("--session-key-file",
                        help="optional owner-private 32-byte raw key shared only by nodes in this run; enables cross-node UAS-ID matching")
    parser.add_argument("--observer-lat", type=float, help="optional asserted observer latitude (sensitive local data)")
    parser.add_argument("--observer-lon", type=float, help="optional asserted observer longitude (sensitive local data)")
    parser.add_argument("--observer-alt-m", type=float,
                        help="optional asserted observer altitude in metres (not sensor-attested)")
    parser.add_argument("--include-raw", action="store_true",
                        help="include raw 25-byte payloads; this exposes the broadcast UAS ID")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if not math.isfinite(args.duration) or args.duration <= 0:
        parser.error("--duration must be a positive finite number")
    if (args.observer_lat is None) != (args.observer_lon is None):
        parser.error("--observer-lat and --observer-lon must be provided together")
    if args.observer_alt_m is not None and args.observer_lat is None:
        parser.error("--observer-alt-m requires --observer-lat and --observer-lon")
    if args.observer_alt_m is not None and not math.isfinite(args.observer_alt_m):
        parser.error("--observer-alt-m must be finite")
    if args.observer_lat is not None:
        if not -90 <= args.observer_lat <= 90:
            parser.error("--observer-lat must be between -90 and 90")
        if not -180 <= args.observer_lon <= 180:
            parser.error("--observer-lon must be between -180 and 180")
    try:
        return asyncio.run(capture(args))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
