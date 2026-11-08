"""PR6 mathematical/input-boundary fixtures; native RF is audited separately."""
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from external_scene import DIRECTIONS,claim_position,selection,spec_for,render
from scene import RX_POSITIONS,layout_positions,ini_for
from plan_external import plan
from setup import ROOT


class ExternalSceneTests(unittest.TestCase):
    def test_baseline_layout_and_ini_bytes_remain_backwards_compatible(self):
        expected={0:(100,100,2),2:(300,100,2),3:(100,300,2),4:(300,300,2),5:(200,100,8)}
        self.assertEqual(RX_POSITIONS,expected)
        text=ini_for(dict(count=20,gap_s=10,seed=701,model='fixed',case='FixedNormal')).replace(str(ROOT),'<PACKAGE>')
        self.assertEqual(hashlib.sha256(text.encode()).hexdigest(),'3d4c3ec039dfa74a35f3566ae0b83a7eb2af1c8fb4fca4571de5e498c788c24d')

    def test_all_directions_have_equal_3d_displacement(self):
        p=[200,200,40];a=[100,100,2]
        for direction in DIRECTIONS:
            for d in [30,100]:
                q=claim_position(p,a,direction,d)
                self.assertAlmostEqual(math.dist(p,q),d,places=10)
                if direction=='equidistant':self.assertAlmostEqual(math.dist(p,a),math.dist(q,a),places=10)
                if direction=='toward':self.assertLess(math.dist(q,a),math.dist(p,a))
                if direction=='away':self.assertGreater(math.dist(q,a),math.dist(p,a))
                if direction=='vertical':self.assertEqual(q[:2],p[:2])

    def test_invalid_or_undefined_geometry_is_not_silently_clamped(self):
        for args in [([100,100,40],[100,100,2],'tangent',30),([110,100,40],[100,100,2],'equidistant',100),([480,100,40],[100,100,2],'x',100)]:
            with self.assertRaises(ValueError):claim_position(*args)
        with self.assertRaises(ValueError):layout_positions('unknown')

    def test_private_schedule_is_deterministic_but_key_dependent(self):
        a=selection(b'a'*32,701,'private_random',20);b=selection(b'b'*32,701,'private_random',20)
        self.assertEqual(a,selection(b'a'*32,701,'private_random',20));self.assertNotEqual(a,b)
        self.assertTrue(set(a)<={0,2,3,4,5})
        with self.assertRaises(ValueError):selection(b'',701,'private_random',20)

    def test_blind_native_configuration_cannot_read_the_private_assignment(self):
        cell=dict(layout='irregular',direction='toward',profile='free',schedule='private_random',bound_db=10,attack_n=2)
        a=spec_for(cell,701,'schedule_blind',30,b'a'*32);b=spec_for(cell,701,'schedule_blind',30,b'b'*32)
        self.assertNotEqual(a['defender_schedule'],b['defender_schedule'])
        self.assertEqual(render(a),render(b));self.assertNotIn('observerSchedule',render(a))
        c=spec_for(cell,701,'schedule_aware',30,b'a'*32)
        self.assertIn('observerSchedule',render(c))

    def test_declared_plan_is_sparse_and_preserves_reference_20_seeds(self):
        cfg=json.loads((ROOT/'config/external-validity.json').read_text());result=plan(cfg)
        self.assertEqual(result['planned_main_new_rf_cases'],1122)
        self.assertEqual(result['planned_main_transmissions'],25400)
        self.assertLess(result['estimated_all_raw_mib'],result['maximum_all_raw_mib'])
        self.assertEqual(result['cells'][0]['evaluation_seeds'],20)

    def test_native_geometry_matches_independent_python_formula(self):
        compiler=shutil.which('c++');self.assertIsNotNone(compiler)
        source=r'''
#include "Issue77ClaimMath.h"
#include <iomanip>
#include <iostream>
int main() {
  issue77::Point p={200,200,40},a={100,100,2};
  for (const auto& name:{"x","toward","away","tangent","vertical","equidistant"}) {
    auto q=issue77::claim(p,a,name,100);
    std::cout<<std::setprecision(17)<<q[0]<<" "<<q[1]<<" "<<q[2]<<"\n";
  }
}
'''
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'a.cc').write_text(source)
            result=subprocess.run([compiler,'-std=c++17','-I',str(ROOT/'native'),str(root/'a.cc'),'-o',str(root/'a')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            values=subprocess.check_output([str(root/'a')],text=True).splitlines()
            for name,line in zip(DIRECTIONS,values):self.assertLess(math.dist(list(map(float,line.split())),claim_position([200,200,40],[100,100,2],name,100)),1e-10)


if __name__=='__main__':unittest.main()
