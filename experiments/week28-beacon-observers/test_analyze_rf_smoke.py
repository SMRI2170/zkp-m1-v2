import hashlib
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze_rf_smoke import summarize


def fixture(counter=204, rssi=-50):
    basic = bytes([2]) + bytes(24)
    location = bytes([0x12]) + bytes(24)
    pack = bytes([0xf2, 25, 2]) + basic + location
    digest = hashlib.sha256(bytes.fromhex('fa0bbc0d') + bytes([counter]) + pack).hexdigest()
    return dict(odid_counter=counter, odid_payload_hex=pack.hex(), vendor_content_digest=digest, rssi_dbm=rssi)


class ReceptionSummaryTests(unittest.TestCase):
    def test_other_phase_not_counted_as_current_reception(self):
        row=fixture();receipt=dict(counter=204,vendor_content_sha256=row['vendor_content_digest'])
        result=summarize([row,fixture(211)],receipt,'test','fixture-node')
        self.assertEqual(result['exact_content_match_and_decode'],1)
        self.assertEqual(result['other_counter_rows'],1)
        self.assertIsNone(result['packet_reception_rate'])
        self.assertIsNone(result['independent_packet_count'])

    def test_counter_match_alone_is_not_content_match(self):
        row=fixture();receipt=dict(counter=204,vendor_content_sha256='0'*64)
        result=summarize([row],receipt,'test','fixture-node')
        self.assertEqual(result['exact_content_match_and_decode'],0)
        self.assertFalse(result['receipt_matches_all_selected'])

    def test_missing_rssi_is_not_zero_dbm(self):
        row=fixture(rssi=None);receipt=dict(counter=204,vendor_content_sha256=row['vendor_content_digest'])
        result=summarize([row],receipt,'test','fixture-node')
        self.assertEqual(result['exact_content_match_and_decode'],1)
        self.assertEqual(result['rssi_count'],0)
        self.assertIsNone(result['rssi_median_dbm'])


if __name__=='__main__':unittest.main()
