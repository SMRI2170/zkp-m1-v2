import json
from pathlib import Path
import unittest
import numpy as np
from sensitivity_suite import (radial_claim,receiver_sites,profiled_power_score,
                               claim_points,remap_async,power_forecast,fit_identity_offsets,
                               personalization_study)


class SensitivityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root=Path(__file__).parent
        cls.cfg=json.loads((root/'sensitivity_config.json').read_text())
        cls.old=json.loads((root/'synthetic3d_config.json').read_text())

    def test_same_range_negative_control_and_invalid_displacement(self):
        base={'d_true':np.array([10.,100.]),'d_claim':np.array([11.,99.])}
        claim,valid=radial_claim(base,30,'same_range')
        np.testing.assert_array_equal(claim,base['d_claim'])
        np.testing.assert_array_equal(valid,[False,True])
        claim,valid=radial_claim(base,30,'in')
        np.testing.assert_array_equal(valid,[False,True])
        self.assertEqual(claim[1],69.)

    def test_unknown_common_power_is_removed_not_per_link_power(self):
        distances=np.array([[10.,30.,60.],[20.,50.,80.]])
        r=np.array([[-50.,-60.,-70.],[-55.,-65.,-75.]])
        score=profiled_power_score(r,distances,22)
        np.testing.assert_allclose(score,profiled_power_score(r+np.array([[13.],[-7.]]),distances,22),atol=1e-12)
        np.testing.assert_array_equal(profiled_power_score(r[:,:1],distances[:,:1],22),[0.,0.])
        self.assertFalse(np.allclose(score,profiled_power_score(r+np.array([0.,10.,0.]),distances,22)))

    def test_synchronous_geometric_same_range_is_actual_3d_displacement(self):
        sites=receiver_sites(3,100)
        points=np.array([[0.,0.,30.],[30.,20.,15.]])
        claim,valid=claim_points(points,sites,20,'same_range_first_rx',np.zeros(2))
        self.assertTrue(valid.all())
        np.testing.assert_allclose(np.linalg.norm(claim-points,axis=1),20,atol=1e-10)
        np.testing.assert_allclose(np.linalg.norm(claim-sites[0],axis=1),np.linalg.norm(points-sites[0],axis=1),atol=1e-10)

    def test_async_count_does_not_add_events_or_change_true_power(self):
        one=remap_async(self.old,4,'test',1);ten=remap_async(self.old,4,'test',10)
        for k in ['time','flight','d_true','power','d_claim']:
            np.testing.assert_array_equal(one[k],ten[k])
        self.assertEqual(len(set(one['receiver'])),1)
        self.assertEqual(len(set(ten['receiver'])),10)
        self.assertEqual(len(set(one['time'])),len(one['time']))

    def test_temporal_history_loses_value_as_correlation_decays(self):
        anchor=np.array([-30.,-50.])
        short,v_short=power_forecast(anchor,-42,0,6,2,1,'ou_matched')
        long,v_long=power_forecast(anchor,-42,0,6,2,0,'ou_matched')
        np.testing.assert_array_equal(long,[-42,-42])
        self.assertGreater(v_long,v_short)
        self.assertGreater(short[0],long[0])

    def test_rid_cold_start_has_no_personalization(self):
        z=np.ones((2,10));r=-42-22*z
        offset,shrink,a,b,fallback=fit_identity_offsets(r,z,-42,22,0,9,1,4,10)
        np.testing.assert_array_equal(offset,[0,0]);np.testing.assert_array_equal(shrink,[0,0])
        np.testing.assert_array_equal(a,[-42,-42]);self.assertEqual(fallback,2)

    def test_rid_offset_uses_only_enrollment_prefix(self):
        z=np.array([[1.,1.5,2.,2.5]])
        r=-42-22*z+6
        a=fit_identity_offsets(r,z,-42,22,3,36,1,4,10)
        changed=r.copy();changed[:,-1]+=1000
        b=fit_identity_offsets(changed,z,-42,22,3,36,1,4,10)
        for x,y in zip(a[:4],b[:4]):np.testing.assert_array_equal(x,y)
        self.assertAlmostEqual(a[0][0],6)
        self.assertGreater(a[1][0],0);self.assertLess(a[1][0],6)


if __name__=='__main__':unittest.main()
