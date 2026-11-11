"""Transmit framing guard tests; synthetic bytes, never enables a radio."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from safe_beacon_tx import validate_ie


def fixture(count=2, counter=204):
    payload = bytes([0xf2, 25, count]) + (bytes([2]) + bytes(24)) * count
    body = bytes.fromhex('fa0bbc0d') + bytes([counter]) + payload
    return bytes([221, len(body)]) + body


class TransmitGuards(unittest.TestCase):
    def test_reference_envelope_accepts_declared_message_counts(self):
        for count in range(1, 10):
            raw = fixture(count)
            self.assertEqual(validate_ie(raw.hex(), 204), raw)

    def test_vendor_prefix_and_length_must_match(self):
        for index in [0, 1, 2, 5]:
            raw = bytearray(fixture()); raw[index] ^= 1
            with self.assertRaises(ValueError): validate_ie(raw.hex(), 204)

    def test_wrong_counter_is_not_the_expected_transmission(self):
        with self.assertRaises(ValueError): validate_ie(fixture().hex(), 203)

    def test_truncated_or_inconsistent_pack_is_rejected(self):
        raw = bytearray(fixture()); raw[9] = 9
        for text in [raw.hex(), fixture().hex()[:-2], 'dd00', 'not hex']:
            with self.assertRaises(ValueError): validate_ie(text, 204)


if __name__ == '__main__':
    unittest.main()
