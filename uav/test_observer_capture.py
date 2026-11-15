import argparse
import os
import struct
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from observer_capture import (
    capture_identity_fields,
    attach_capture_identity,
    ephemeral_tag,
    load_session_key_file,
    message_fields_for_log,
    opaque_local_id,
    parse_rid_message,
    parse_rid_payload,
    parse_service_uuid,
    session_salt_from_key,
    uint32_id,
)


def basic_id_message(uas_id=b"TEST-UAS-01"):
    return bytes([0x02, 0x12]) + uas_id[:20].ljust(20, b"\x00") + bytes(3)


def location_message(latitude=35.1234567, longitude=139.7654321,
                     altitude_raw=2200, timestamp_raw=12345):
    raw = bytearray(25)
    raw[0] = 0x12  # Location, protocol version 2
    struct.pack_into("<ii", raw, 5, round(latitude * 10_000_000), round(longitude * 10_000_000))
    struct.pack_into("<H", raw, 15, altitude_raw)
    struct.pack_into("<H", raw, 21, timestamp_raw)
    return bytes(raw)


def authentication_message(data_page=0, auth_type=5, last_page_index=2,
                           length=63, timestamp=0x01020304):
    raw = bytearray(25)
    raw[0] = 0x22  # Authentication, protocol version 2
    raw[1] = ((auth_type & 0x0F) << 4) | (data_page & 0x0F)
    if data_page == 0:
        raw[2] = last_page_index
        raw[3] = length
        struct.pack_into("<I", raw, 4, timestamp)
        raw[8:25] = bytes(range(17))
    else:
        raw[2:25] = bytes(range(23))
    return bytes(raw)


def message_pack(*messages):
    return bytes([0xF2, 25, len(messages)]) + b"".join(messages)


class ParseServiceUuidTests(unittest.TestCase):
    def test_accepts_canonical_and_16_bit_forms(self):
        expected = "0000fffa-0000-1000-8000-00805f9b34fb"
        self.assertEqual(parse_service_uuid(expected.upper()), expected)
        self.assertEqual(parse_service_uuid("0xFFFA"), expected)

    def test_normalizes_but_does_not_confuse_unrelated_uuid(self):
        unrelated = parse_service_uuid("0000180f-0000-1000-8000-00805f9b34fb")
        self.assertNotEqual(unrelated, "0000fffa-0000-1000-8000-00805f9b34fb")


class RidMessageTests(unittest.TestCase):
    def test_parses_basic_id_without_changing_id(self):
        parsed = parse_rid_message(basic_id_message())
        self.assertEqual(parsed.message_type, "basic_id")
        self.assertEqual(parsed.protocol_version, 2)
        self.assertEqual(parsed.id_type, 1)
        self.assertEqual(parsed.ua_type, 2)
        self.assertEqual(parsed.uas_id, "TEST-UAS-01")

    def test_log_fields_never_contain_plaintext_uas_id(self):
        fields = message_fields_for_log(parse_rid_message(basic_id_message()))
        self.assertNotIn("uas_id", fields)

    def test_parses_location_fields_and_units(self):
        parsed = parse_rid_message(location_message())
        self.assertEqual(parsed.message_type, "location")
        self.assertAlmostEqual(parsed.latitude_deg, 35.1234567)
        self.assertAlmostEqual(parsed.longitude_deg, 139.7654321)
        self.assertEqual(parsed.altitude_geo_m, 100)
        self.assertAlmostEqual(parsed.rid_seconds_within_hour, 1234.5)

    def test_handles_unknown_altitude_and_timestamp(self):
        parsed = parse_rid_message(location_message(altitude_raw=0xFFFF, timestamp_raw=0xFFFF))
        self.assertIsNone(parsed.altitude_geo_m)
        self.assertIsNone(parsed.rid_timestamp_raw)
        self.assertIsNone(parsed.rid_seconds_within_hour)

    def test_parses_authentication_page_zero_without_claiming_verification(self):
        parsed = parse_rid_message(authentication_message())
        self.assertEqual(parsed.message_type, "authentication")
        self.assertEqual(parsed.message_type_id, 2)
        self.assertEqual(parsed.auth_type, 5)
        self.assertEqual(parsed.auth_data_page, 0)
        self.assertEqual(parsed.auth_last_page_index, 2)
        self.assertEqual(parsed.auth_length, 63)
        self.assertEqual(parsed.auth_timestamp_2019, 0x01020304)
        self.assertEqual(parsed.auth_data_hex, bytes(range(17)).hex())

    def test_parses_nonzero_authentication_page_as_raw_fragment(self):
        parsed = parse_rid_message(authentication_message(data_page=2))
        self.assertEqual(parsed.auth_type, 5)
        self.assertEqual(parsed.auth_data_page, 2)
        self.assertIsNone(parsed.auth_last_page_index)
        self.assertIsNone(parsed.auth_length)
        self.assertIsNone(parsed.auth_timestamp_2019)
        self.assertEqual(parsed.auth_data_hex, bytes(range(23)).hex())

    def test_rejects_authentication_page_zero_with_invalid_page_capacity(self):
        with self.assertRaisesRegex(ValueError, "declared page capacity"):
            parse_rid_message(authentication_message(last_page_index=0, length=18))
        with self.assertRaisesRegex(ValueError, "last page index"):
            parse_rid_message(authentication_message(last_page_index=16, length=255))

    def test_preserves_other_assigned_message_type_without_claiming_authenticity(self):
        raw = bytearray(25)
        raw[0] = 0x32  # Self ID, protocol version 2
        parsed = parse_rid_message(bytes(raw))
        self.assertEqual(parsed.message_type, "self_id")
        self.assertEqual(parsed.message_type_id, 3)

    def test_parses_message_pack_and_retains_individual_auth_message_bytes(self):
        basic = basic_id_message()
        auth_page = authentication_message(data_page=1)
        decoded = parse_rid_payload(message_pack(basic, auth_page))
        self.assertEqual(len(decoded), 2)
        self.assertEqual(decoded[0][0], basic)
        self.assertEqual(decoded[0][1].message_type, "basic_id")
        self.assertEqual(decoded[1][0], auth_page)
        self.assertEqual(decoded[1][1].message_type, "authentication")
        self.assertEqual(decoded[1][1].message_pack_index, 1)
        self.assertEqual(decoded[1][1].message_pack_size, 2)

    def test_parses_single_message_through_payload_entrypoint(self):
        raw = location_message()
        decoded = parse_rid_payload(raw)
        self.assertEqual(len(decoded), 1)
        self.assertEqual(decoded[0][0], raw)
        self.assertEqual(decoded[0][1].message_type, "location")
        self.assertIsNone(decoded[0][1].message_pack_index)

    def test_rejects_malformed_message_pack_headers_and_children(self):
        valid_child = basic_id_message()
        for raw, expected in (
            (b"\xF2\x19", "header is truncated"),
            (bytes([0xF2, 24, 1]) + valid_child, "size must be 25"),
            (bytes([0xF2, 25, 0]), "count is out of range"),
            (bytes([0xF2, 25, 10]) + valid_child * 10, "count is out of range"),
            (bytes([0xF2, 25, 2]) + valid_child, "length does not match"),
            (bytes([0xF2, 25, 1]) + b"\xF2" + bytes(24), "unsupported Remote ID message type"),
        ):
            with self.subTest(expected=expected), self.assertRaisesRegex(ValueError, expected):
                parse_rid_payload(raw)

    def test_rejects_wrong_length_version_type_and_coordinate(self):
        with self.assertRaises(ValueError):
            parse_rid_message(b"\x00" * 24)
        bad_version = bytearray(basic_id_message())
        bad_version[0] = 0x03
        with self.assertRaises(ValueError):
            parse_rid_message(bytes(bad_version))
        bad_type = bytearray(basic_id_message())
        bad_type[0] = 0xF2
        with self.assertRaises(ValueError):
            parse_rid_message(bytes(bad_type))
        with self.assertRaises(ValueError):
            parse_rid_message(location_message(latitude=91))


class EphemeralTagTests(unittest.TestCase):
    def test_shared_key_matches_observers_only_within_same_run(self):
        shared_key = b"a" * 32
        uas_id = "1:2:TEST-UAS-01"
        observer_a = ephemeral_tag(shared_key, "uas-id", uas_id, "field-run-01")
        observer_b = ephemeral_tag(shared_key, "uas-id", uas_id, "field-run-01")
        self.assertEqual(observer_a, observer_b)
        self.assertNotEqual(observer_a, ephemeral_tag(shared_key, "uas-id", uas_id, "field-run-02"))
        self.assertNotEqual(observer_a, ephemeral_tag(b"b" * 32, "uas-id", uas_id, "field-run-01"))
        self.assertNotEqual(observer_a, ephemeral_tag(shared_key, "ble-address", uas_id, "field-run-01"))

    def test_tag_encoding_is_unambiguous(self):
        key = b"k" * 32
        self.assertNotEqual(
            ephemeral_tag(key, "domain", "a:b", "context"),
            ephemeral_tag(key, "domain", "b", "context:a"),
        )


class SessionKeyFileTests(unittest.TestCase):
    def test_loads_exact_owner_private_32_byte_key(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "session-key.bin"
            path.write_bytes(b"k" * 32)
            os.chmod(path, 0o600)
            self.assertEqual(load_session_key_file(path), b"k" * 32)

    def test_rejects_wrong_length_and_permissions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "session-key.bin"
            for value in (b"short", b"k" * 33):
                path.write_bytes(value)
                os.chmod(path, 0o600)
                with self.subTest(length=len(value)), self.assertRaises(ValueError):
                    load_session_key_file(path)

            path.write_bytes(b"k" * 32)
            os.chmod(path, 0o640)
            with self.assertRaises(ValueError):
                load_session_key_file(path)

    def test_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            real_path = Path(temp_dir) / "real-key.bin"
            link_path = Path(temp_dir) / "linked-key.bin"
            real_path.write_bytes(b"k" * 32)
            os.chmod(real_path, 0o600)
            link_path.symlink_to(real_path)
            with self.assertRaises(ValueError):
                load_session_key_file(link_path)


class SessionSaltTests(unittest.TestCase):
    def test_kdf_vector_matches_v2_prover_and_is_run_scoped(self):
        key = b"0123456789abcdef0123456789abcdef"
        self.assertEqual(
            session_salt_from_key(key, "field-run-01"),
            386295568514927445142053419718468866944094829984725124563547894352370537259,
        )
        self.assertNotEqual(session_salt_from_key(key, "field-run-01"),
                            session_salt_from_key(key, "field-run-02"))
        self.assertNotEqual(session_salt_from_key(key, "field-run-01"),
                            session_salt_from_key(b"b" * 32, "field-run-01"))

    def test_rejects_invalid_key_and_run_id(self):
        with self.assertRaises(ValueError):
            session_salt_from_key(b"short", "field-run-01")
        with self.assertRaises(ValueError):
            session_salt_from_key(b"k" * 32, "run id with spaces")


class CaptureMetadataTests(unittest.TestCase):
    def test_capture_identity_is_attached_without_changing_identifiers(self):
        args = argparse.Namespace(
            run_id="field-run-01",
            observer_id="observer-pi-01",
            calibration_profile_id=7,
        )
        self.assertEqual(capture_identity_fields(args), {
            "run_id": "field-run-01",
            "observer_id": "observer-pi-01",
            "calibration_profile_id": 7,
            "uas_id_tag_scope": "process_local_key_and_run_id",
        })
        self.assertEqual(capture_identity_fields(args, shared_session_key=True)["uas_id_tag_scope"],
                         "shared_session_key_and_run_id")
        self.assertEqual(attach_capture_identity(
            {"record_type": "observation", "rssi_dbm": -54},
            capture_identity_fields(args),
        ), {
            "schema": "signal.observer-capture.v1",
            "record_type": "observation",
            "rssi_dbm": -54,
            "run_id": "field-run-01",
            "observer_id": "observer-pi-01",
            "calibration_profile_id": 7,
            "uas_id_tag_scope": "process_local_key_and_run_id",
        })

    def test_validates_opaque_ids_and_uint32_profiles(self):
        self.assertEqual(opaque_local_id("field-run-01"), "field-run-01")
        self.assertEqual(uint32_id("0"), 0)
        self.assertEqual(uint32_id("4294967295"), 0xFFFFFFFF)
        for invalid in ("", " contains-space", "user/name", "x" * 65):
            with self.subTest(value=invalid):
                with self.assertRaises(argparse.ArgumentTypeError):
                    opaque_local_id(invalid)
        for invalid in ("-1", "4294967296", "1.5", "profile", "+1", "01"):
            with self.subTest(value=invalid):
                with self.assertRaises(argparse.ArgumentTypeError):
                    uint32_id(invalid)


if __name__ == "__main__":
    unittest.main()
