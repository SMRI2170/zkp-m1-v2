"""Synthetic fixtures only; geometry cannot be inferred from real RSS in tests."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
import numpy as np
from dataset21_adapter import nearest_indices,local_xy,geometry,groups,load_d1
from run_dataset21_eval import decision_bins,metrics,designs,fit_model,make_input,synthesize_inputs


def fixture():
    streams={}
    t=np.arange(0,1000,.25)
    for i in range(5):
        role=np.full(len(t),'embargo',dtype='<U10');role[t<400]='train';role[(t>=450)&(t<650)]='calibrate';role[t>=700]='evaluate'
        streams[f'LW{i+1}']=dict(time=t.copy(),elapsed=t.copy(),role=role,rss=np.ones((len(t),2)),
                                lon=np.zeros(len(t)),lat=np.zeros(len(t)),z=np.ones(len(t))*40)
    return streams


class AdapterTests(unittest.TestCase):
    def test_geometry_missing_is_not_a_zero_detection_rate(self):
        receivers,gate=geometry(fixture(),None)
        self.assertIsNone(receivers);self.assertEqual(gate['status'],'MISSING_RECEIVER_METADATA')
        self.assertEqual(metrics(np.array([np.nan,np.nan]),1.)['und_rate'],1.)
        self.assertIsNone(metrics(np.array([np.nan]),1.)['alarm_scored'])

    def test_false_vertical_reference_cannot_enable_evaluation(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'metadata.json';p.write_text(json.dumps(dict(horizontal_crs='EPSG:4326',vertical_reference='AGL',receivers={})))
            with self.assertRaises(ValueError):geometry(fixture(),p)

    def test_local_projection_units_and_origin_are_metric(self):
        self.assertTrue(np.allclose(local_xy(0.,0.,0.,0.),[0,0]))
        east=local_xy(.001,0.,0.,0.);self.assertAlmostEqual(east[0],111.3194908,places=5)
        self.assertAlmostEqual(east[1],0.)

    def test_chronological_source_groups_never_cross_roles(self):
        streams=fixture();g=groups(streams,5,'evaluate',.2,lag_s=100.)
        for j,s in enumerate(streams.values()):
            self.assertTrue(np.all(s['role'][g['selected'][g['accepted'],j]]=='evaluate'))
        train=groups(streams,1,'train',.2)
        self.assertFalse(set(train['selected'][:,0])&set(g['reference_indices']))

    def test_repeated_nearest_source_not_counted_twice(self):
        streams=fixture();s=streams['LW2']
        for key in list(s):s[key]=s[key][::4]
        g=groups(streams,2,'evaluate',2.)
        ids=g['selected'][g['accepted'],1]
        self.assertEqual(len(ids),len(set(ids)))
        self.assertGreater(g['source_reuse_removed'],0)

    def test_late_observation_is_not_clamped_or_relabelled_as_reference_time(self):
        streams=fixture();g=groups(streams,5,'evaluate',.2,lag_s=3600.)
        self.assertEqual(g['unique_complete'],0)
        self.assertFalse(g['physical_same_packet'])

    def test_missing_source_row_stays_missing_and_never_falls_back(self):
        streams=fixture()
        a=groups(streams,5,'evaluate',.2,missing=.5,seed=801);b=groups(streams,5,'evaluate',.2,missing=.5,seed=801)
        np.testing.assert_array_equal(a['selected'],b['selected']);np.testing.assert_array_equal(a['present'],b['present'])
        baseline=groups(streams,5,'evaluate',.2)
        np.testing.assert_array_equal(a['selected'],baseline['selected'])
        self.assertLess(a['unique_complete'],baseline['unique_complete'])

    def test_five_second_windows_have_real_time_bounds_not_five_adjacent_rows(self):
        streams=fixture();g=groups(streams,1,'evaluate',.2);bins=decision_bins(streams,g,'evaluate')
        self.assertEqual(len(bins),59) # full [700,995) windows; last sample999.75
        self.assertTrue(all(len(ids)==20 for _,ids in bins))

    @unittest.skipUnless(importlib.util.find_spec('scipy'),'Numerical adapter test runs in dedicated SciPy CI job')
    def test_default_ghostbuster_api_and_explicit_bounds_both_work(self):
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'week27-rid-sim/scripts'))
        from ghostbuster import locate_frames
        r=np.array([[0,0,-30],[500,0,-20],[500,500,-25],[0,500,0.]])
        p=np.array([[210.,220.,-10.]])
        estimate,audit=locate_frames(np.linalg.norm(p[:,None]-r,axis=-1),r,bounds=([-1000,-1000,-500],[1000,1000,500]),start_heights=(-10,100))
        self.assertTrue(np.allclose(p,estimate,atol=1.e-4));self.assertTrue(audit['frame_stationary'].all())

    @unittest.skipUnless(importlib.util.find_spec('scipy'),'End-to-end numerical fixture runs in dedicated SciPy CI job')
    def test_adapter_to_existing_ghostbuster_and_train_only_fit(self):
        from ghostbuster import window_scores
        streams=fixture();receivers=np.array([[0,0,0],[500,0,0],[500,500,0],[0,500,0],[200,160,10.]])
        for j,s in enumerate(streams.values()):
            t=s['elapsed'];s['xyz']=np.c_[200+80*np.cos(t/30),200+80*np.sin(t/30),40+np.zeros(len(t))]
            d=np.linalg.norm(s['xyz']-receivers[j],axis=1)
            s['rss']=np.c_[-30-20*np.log10(d),-32-20*np.log10(d)]
        before,n=fit_model(streams,receivers,0)
        self.assertAlmostEqual(n,2.,places=9)
        design=dict(k=5,max_span_s=.2,lag_s=0.,missing=0.,seed=801)
        rss,claims,g=make_input(streams,receivers,design,'evaluate',0,50.,'unchanged')
        score,_=window_scores(rss,claims,receivers,before,n,bounds=([-5000,-5000,-500],[5000,5000,500]))
        self.assertTrue(np.allclose(score,50.,atol=1.e-4))
        for s in streams.values():s['rss'][s['role']=='evaluate']+=100
        after,other=fit_model(streams,receivers,0)
        np.testing.assert_array_equal(before,after);self.assertEqual(n,other)

    def test_real_input_injection_contract_preserves_baseline_and_offsets(self):
        streams=fixture()
        with tempfile.TemporaryDirectory() as folder:
            result=synthesize_inputs(streams,dict(offsets_m=[20,50,100,200]),Path(folder))
            self.assertEqual(len(result),20)
            arrays=np.load(Path(folder)/'LW1-synthetic-inputs.npz')
            np.testing.assert_array_equal(arrays['measured_rss'],arrays['synthetically_perturbed_rss'][:,0])
            self.assertTrue(np.allclose(arrays['synthetically_perturbed_rss'][:,1]-arrays['measured_rss'],6))
            self.assertTrue(all(not r['position_detection_executed'] for r in result))

    @unittest.skipUnless(importlib.util.find_spec('scipy'),'D1 .mat fixture runs in pinned numerical CI job')
    def test_d1_reader_reproduces_gps_interpolation_and_embargo(self):
        from scipy.io import savemat
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);inventory=[]
            t=np.linspace(0,999,1000)
            for i in range(1,6):
                path=root/f'D1_RSS_Measurements/LW{i}/GPS_RSS_data_40m_fs20MHz_LW{i}.mat';path.parent.mkdir(parents=True)
                # Explicit synthetic coordinates, not field data.
                d=dict(timestamp_meas=t,timestamp_gps=t,GPSx=t*.000001,GPSy=t*.000002,GPSz=np.ones(1000)*40,
                       mX=t*.000001,mY=t*.000002,mZ=np.ones(1000)*40,RSS1=np.ones(1000)*-60,RSS2=np.ones(1000)*-62)
                savemat(path,d);inventory.append(dict(file=str(path.relative_to(root)),sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
            streams,source=load_d1(root,dict(inventory=inventory))
            self.assertEqual(source['raw_rows'],5000)
            self.assertTrue(all(source['coordinate_errors'][0]['interpolation_max_error'][k]<1.e-10 for k in ['mX','mY','mZ']))
            roles=streams['LW1']['role'];self.assertTrue((roles=='embargo').any())
            path.write_bytes(path.read_bytes()+b'corruption')
            with self.assertRaises(ValueError):load_d1(root,dict(inventory=inventory))


if __name__=='__main__':unittest.main()
