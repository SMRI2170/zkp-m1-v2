import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from analyze_clock_candidates import active_release_path,overlaps_window,paths_to_anchor


class ClockCandidateTests(unittest.TestCase):
    def test_release_identity_survives_snapshot_root_change(self):
        self.assertTrue(active_release_path('/local/snapshot/releases/kit-a/captures/log','/remote/releases/kit-a'))
        self.assertFalse(active_release_path('/local/snapshot/releases/kit-ab/captures/log','/remote/releases/kit-a'))

    def test_paths_and_reversed_offsets(self):
        graph={'A':[('B',9,11),('C',19,21)],'B':[('A',-11,-9),('C',9,11)],
               'C':[('A',-21,-19),('B',-11,-9)]}
        forward=paths_to_anchor(graph,'A','C')
        self.assertEqual(len(forward),2)
        self.assertEqual(min(x['offset_low_s'] for x in forward),18)
        self.assertEqual(max(x['offset_high_s'] for x in forward),22)
        reverse=paths_to_anchor(graph,'C','A')
        self.assertEqual(min(x['offset_low_s'] for x in reverse),-22)
        self.assertEqual(paths_to_anchor(graph,'missing','C'),[])

    def test_anchor_has_zero_model_offset_not_proven_clock(self):
        self.assertEqual(paths_to_anchor({},'A','A'),[{'path':['A'],'offset_low_s':0,'offset_high_s':0}])

    def test_window_boundary_and_uncertainty(self):
        self.assertTrue(overlaps_window(9,0,1,10,20))
        self.assertFalse(overlaps_window(20,0,0,10,20))
        self.assertTrue(overlaps_window(20,-1,0,10,20))


if __name__=='__main__':unittest.main()
