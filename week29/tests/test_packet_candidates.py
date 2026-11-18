import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from audit_packet_candidates import classify


class PacketCandidatesTests(unittest.TestCase):
    def row(self,t=100):return dict(utc=t,bssid='synthetic',frequency=1)

    def test_close_time_and_matching_wrapped_counter_never_confirm(self):
        a=dict(self.row(),counter=0,sequence=0)
        b=dict(self.row(100.01),counter=0,sequence=0)
        self.assertEqual(classify([a],[b],(0,0),(0,0),1)[0],'candidate')

    def test_repeated_content_candidates_are_preserved_as_ambiguous(self):
        self.assertEqual(classify([self.row(),self.row(100.1)],[self.row()],(0,0),(0,0),1)[0],'ambiguous')

    def test_unknown_clock_and_clock_jump_do_not_confirm(self):
        self.assertEqual(classify([self.row()],[self.row()],None,(0,0),1)[0],'ambiguous')
        self.assertEqual(classify([self.row()],[self.row(120)],(0,0),(0,0),1)[0],'unmatched')

    def test_window_and_clock_sensitivity(self):
        self.assertEqual(classify([self.row()],[self.row(102)],(0,0),(0,0),1)[0],'unmatched')
        self.assertEqual(classify([self.row()],[self.row(102)],(0,0),(-2,-2),1)[0],'candidate')
        self.assertEqual(classify([self.row()],[self.row(102)],(0,0),(-2,-2),1,5)[0],'unmatched')

    def test_other_transmitter_does_not_match_by_content(self):
        self.assertEqual(classify([self.row()],[dict(self.row(),bssid='other')],(0,0),(0,0),1)[0],'unmatched')


if __name__=='__main__':unittest.main()
