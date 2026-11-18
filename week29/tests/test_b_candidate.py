import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from analyze_b_candidate import deduplicate, split_segments


class CandidateTests(unittest.TestCase):
    def test_exact_duplicate_only(self):
        def row(t, digest):
            return {'capture': {'received_at_utc': '2026-01-01T00:00:00Z',
                                'monotonic_time_us': t, 'bssid': 'synthetic',
                                'frequency_mhz': 2437, 'vendor_content_digest': digest}}
        rows = [row(1, 'a'), row(1, 'a'), row(2, 'a'), row(2, 'b')]
        self.assertEqual(len(deduplicate(rows)), 3)

    def test_gap_and_clock_boundary(self):
        rows = [dict(origin=1, mono=0), dict(origin=1, mono=60),
                dict(origin=1, mono=121), dict(origin=2, mono=1)]
        self.assertEqual([len(x) for x in split_segments(rows)], [2, 1, 1])


if __name__ == '__main__':
    unittest.main()
