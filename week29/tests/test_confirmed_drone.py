import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from analyze_confirmed_drone import horizontal_distance, payload_overlap, stats


class ConfirmedDroneTests(unittest.TestCase):
    def test_horizontal_distance(self):
        self.assertEqual(horizontal_distance(35, 135, 35, 135), 0)
        self.assertAlmostEqual(horizontal_distance(0, 0, 0, 1), 111194.9266, places=3)
        self.assertAlmostEqual(horizontal_distance(35, 135, 36, 136),
                               horizontal_distance(36, 136, 35, 135), places=6)

    def test_overlap_is_content_not_packet_or_rows(self):
        def row(payload):return {'capture':{'odid_payload_hex':payload}}
        self.assertEqual(payload_overlap([row('a'),row('a'),row('b')],
                                         [row('a'),row('a')]),1)

    def test_missing_or_nonfinite_measurements(self):
        self.assertEqual(stats([None,float('nan')]),{'n':0})
        self.assertEqual(stats([1,3,None])['median'],2)


if __name__=='__main__':unittest.main()
