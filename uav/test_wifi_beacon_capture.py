"""Synthetic packet fixtures only; no field coordinates or capture bytes."""
import io
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wifi_beacon_capture as wifi


BODY = bytes.fromhex('fa0bbc0d07') + bytes([0x02, 0x12]) + b'TEST-UAS-01'.ljust(20, b'\0') + bytes(3)


def beacon(body=BODY, radiotap=None, tail=b''):
    # flags, channel and dBm signal; channel aligns to 2 after the flags.
    rt = radiotap or struct.pack('<BBHI', 0, 0, 15, 0x2a) + b'\0\0' + struct.pack('<HHb', 2412, 0, -61)
    frame = bytearray(36)
    frame[0] = 0x80
    frame[10:16] = bytes.fromhex('020000000001')
    frame[16:22] = bytes.fromhex('020000000001')
    frame[22:24] = struct.pack('<H', 16)
    frame[24:32] = struct.pack('<Q', 100)
    return rt + bytes(frame) + bytes([221, len(body)]) + body + tail


def pcap(packet, endian='<', nano=False, original=None):
    magic = (b'\x4d\x3c\xb2\xa1' if nano else b'\xd4\xc3\xb2\xa1') if endian == '<' else (
        b'\xa1\xb2\x3c\x4d' if nano else b'\xa1\xb2\xc3\xd4')
    return magic + struct.pack(endian + 'HHIIII', 2, 4, 0, 0, 4096, 127) + struct.pack(
        endian + 'IIII', 1700000000, 0, len(packet), original or len(packet)) + packet


class WifiBeaconTests(unittest.TestCase):
    def test_android_vendor_content_matches_pi(self):
        row, = wifi.decode_beacon(beacon())
        self.assertEqual(row['rssi_dbm'], -61)
        self.assertEqual(row['frequency_mhz'], 2412)
        self.assertEqual(row['odid_counter'], 7)
        self.assertEqual(row['messages'][0]['message_type'], 'basic_id')
        self.assertNotIn('uas_id', row['messages'][0])
        self.assertEqual(row['vendor_content_digest'], wifi.hashlib.sha256(BODY).hexdigest())
        self.assertEqual(row['physical_packet_match'], 'unconfirmed')

    def test_absent_signal_is_not_zero(self):
        rt = struct.pack('<BBHI', 0, 0, 8, 0)
        row, = wifi.decode_beacon(beacon(radiotap=rt))
        self.assertIsNone(row['rssi_dbm'])
        self.assertEqual(row['rssi_missing_reason'], 'RADIOTAP_DBM_SIGNAL_ABSENT')

    def test_extended_presence_words_and_tsft_alignment(self):
        rt = struct.pack('<BBHII', 0, 0, 25, 0x80000021, 0) + bytes(4) + struct.pack('<Qb', 0, -72)
        self.assertEqual(wifi.decode_beacon(beacon(radiotap=rt))[0]['rssi_dbm'], -72)

    def test_bad_fcs_rejected_and_fcs_tail_removed(self):
        packet = bytearray(beacon())
        packet[8] = 0x40
        with self.assertRaisesRegex(ValueError, 'bad FCS'):
            wifi.decode_beacon(packet)
        packet[8] = 0x10
        row, = wifi.decode_beacon(bytes(packet) + bytes(4))
        self.assertEqual(row['frame_digest'], wifi.decode_beacon(beacon())[0]['frame_digest'])

    def test_truncated_ie_rejected(self):
        with self.assertRaisesRegex(ValueError, 'IE body'):
            wifi.decode_beacon(beacon(tail=b'\xdd\x05\x00'))

    def test_invalid_odid_not_valid_observation(self):
        row, = wifi.decode_beacon(beacon(body=bytes.fromhex('fa0bbc0d07f21902')))
        self.assertEqual(row['rid_parse_status'], 'invalid')
        self.assertEqual(row['messages'], [])

    def test_other_vendor_and_data_frame_not_remote_id(self):
        self.assertEqual(wifi.decode_beacon(beacon(body=b'not-remote-id')), [])
        data = bytearray(beacon()); data[15] = 8
        self.assertEqual(wifi.decode_beacon(data), [])

    def test_pcap_byte_order_and_timestamp_resolution(self):
        for endian in ['<', '>']:
            for nano in [False, True]:
                out = io.StringIO()
                counts = wifi.consume(io.BytesIO(pcap(beacon(), endian, nano)), out, 'test-node', 'replay')
                self.assertEqual(counts['decoded_ies'], 1)
                row = json.loads(out.getvalue())
                self.assertEqual(row['source_type'], 'replay')
                self.assertIsNone(row['receiver_position'])
                self.assertIsNone(row['time_uncertainty_ms'])

    def test_truncated_frame_not_decoded(self):
        out = io.StringIO()
        counts = wifi.consume(io.BytesIO(pcap(beacon(), original=4096)), out, 'test-node', 'replay')
        self.assertEqual(counts['truncated_frames'], 1)
        self.assertEqual(out.getvalue(), '')

    def test_unsupported_pcapng_or_linktype_rejected(self):
        for packet in [bytes(24), pcap(beacon())[:20] + struct.pack('<I', 1) + pcap(beacon())[24:]]:
            with self.assertRaises(ValueError):
                list(wifi.pcap_packets(io.BytesIO(packet)))

    def test_unbounded_pcap_record_rejected(self):
        packet = pcap(beacon())[:24] + struct.pack('<IIII', 0, 0, 9999999, 9999999)
        with self.assertRaisesRegex(ValueError, 'PCAP record'):
            list(wifi.pcap_packets(io.BytesIO(packet)))

    def test_output_permissions_overwrite_and_symlink_rejection(self):
        previous = wifi.ROOT
        with tempfile.TemporaryDirectory() as directory:
            wifi.ROOT = Path(directory)
            try:
                path = wifi.ROOT / 'captures/run/out.jsonl'
                with wifi.private_output(path) as out:
                    out.write('test')
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
                with self.assertRaises(FileExistsError): wifi.private_output(path)
                with self.assertRaises(ValueError): wifi.private_output(wifi.ROOT / 'public.jsonl')
                (wifi.ROOT / 'captures/link').symlink_to(path.parent, target_is_directory=True)
                with self.assertRaises(ValueError): wifi.private_output(wifi.ROOT / 'captures/link/new.jsonl')
                os.chmod(path.parent, 0o755)
                with self.assertRaises(ValueError): wifi.private_output(path.parent / 'new.jsonl')
            finally:
                wifi.ROOT = previous


if __name__ == '__main__':
    unittest.main()
