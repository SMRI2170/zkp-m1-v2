import unittest
import numpy as np
from snr_four_station import centered,select_groups,time_windows,adjacent,split_drift

class SNRFourStationTests(unittest.TestCase):
    def row(self,receiver='1',**changes):
        r=dict(name='flight',transmission_idx='0',rrh_idx=receiver,latitude='1',longitude='2',
            payload_base64='abc',sf='10',cr='1',fc='862500000',bandwidth='250000',area='uav',
            area_type='drone_los',rx_timestamp_full='100',rx_timestamp_frac='.1',snr=str(int(receiver)))
        r.update(changes);return r
    def test_common_per_frame_shift_cancels(self):
        s=np.array([[1.,2.,4.,8.],[6.,-2.,9.,10.]])
        shifted=s+np.array([[7.],[-30.]])
        np.testing.assert_allclose(centered(s),centered(shifted))
        np.testing.assert_allclose(centered(s).sum(axis=1),0,atol=1e-12)
        np.testing.assert_allclose(s[:,0]-s[:,3],shifted[:,0]-shifted[:,3])
    def test_exact_same_frame_four_receivers_required(self):
        good=[self.row(str(i)) for i in range(1,5)]
        a,c=select_groups(good);self.assertEqual(c['accepted_four_station_groups'],1)
        np.testing.assert_array_equal(a['flight']['s'],[[1,2,3,4]])
        for bad in [good[:3],good[:3]+[good[0]],good[:3]+[self.row('4',latitude='')],good[:3]+[self.row('4',payload_base64='wrong')]]:
            a,c=select_groups(bad);self.assertEqual(c['accepted_four_station_groups'],0)
    def test_frame_ids_are_scoped_by_session(self):
        a,c=select_groups([self.row(str(i),name=name) for name in ['A','B'] for i in range(1,5)])
        self.assertEqual(len(a),2);self.assertEqual(c['accepted_four_station_groups'],2)
    def test_sparse_and_incomplete_windows_are_not_filled(self):
        t=np.array([0.,1.,2.,3.,4.,20.,21.,22.,23.,24.,30.,31.])
        windows=time_windows(t)
        self.assertEqual([i for i,_ in windows],[0,2])
        self.assertEqual([int(m.sum()) for _,m in windows],[5,5])
    def test_adjacent_correlation_excludes_reception_gaps(self):
        result=adjacent(np.array([0.,1.,2.,10.,11.]),np.array([1.,2.,3.,-10.,-9.]))
        self.assertEqual(result['adjacent_pairs'],3)
        self.assertIsNone(adjacent(np.array([0.,1.,2.]),np.ones(3))['lag_one_correlation'])
    def test_drift_uses_elapsed_time_thirds_and_refuses_sparse_segments(self):
        t=np.arange(90.);x=np.r_[np.zeros(30),np.full(30,999),np.full(30,4)]
        d=split_drift(t,x);self.assertEqual(d['late_minus_early_db'],4)
        self.assertIsNone(split_drift(t[:30],x[:30])['late_minus_early_db'])

if __name__=='__main__':unittest.main()
