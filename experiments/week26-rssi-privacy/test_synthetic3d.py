import json
from pathlib import Path
import unittest

import numpy as np
from simulate3d_independent import generate, scenario, receive, conformal_radius, summarize


class SyntheticChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c=json.loads(Path(__file__).with_name('synthetic3d_config.json').read_text())
        cls.base=generate(cls.c,23,'test')

    def test_one_receiver_per_event_and_hourly_flight_starts(self):
        d=self.base
        for f in np.unique(d['flight']):
            mask=d['flight']==f
            self.assertEqual(mask.sum(),40)
            self.assertEqual(len(set(d['receiver'][mask])),1)
        starts=[d['time'][d['flight']==f][0] for f in np.unique(d['flight'])]
        np.testing.assert_array_equal(np.diff(starts),3600)
        self.assertEqual(len(set(d['time'])),len(d['time']))

    def test_splits_do_not_share_flights_or_event_times(self):
        a=generate(self.c,23,'train');b=generate(self.c,23,'calibration')
        self.assertFalse(set(a['flight']) & set(b['flight']))
        self.assertFalse(set(a['time']) & set(b['time']))
        self.assertFalse(set(a['time']) & set(self.base['time']))

    def test_position_only_keeps_observable_rssi_and_censoring(self):
        d=scenario(self.base,self.c,'position_only',23,np.array([-42.]))
        np.testing.assert_array_equal(d['raw'],self.base['raw'])
        for a,b in zip(receive(d,self.c,'mixed'),receive(self.base,self.c,'mixed')):
            np.testing.assert_array_equal(a,b)
        self.assertTrue(np.all((d['d_true']<30)!=(d['d_claim']<30)))

    def test_joint_power_compensation_and_bound(self):
        a=scenario(self.base,self.c,'joint',23,np.array([-42.]))
        # Before quantization and selection, true geometry and claimed geometry
        # give exactly the same required-power residual after joint compensation.
        n=self.c['path_loss_exponent']
        np.testing.assert_allclose(a['raw']+10*n*np.log10(a['d_claim']),
                                   self.base['raw']+10*n*np.log10(self.base['d_true']),atol=1e-10)
        b=scenario(self.base,self.c,'joint_bounded8',23,np.array([-42.]))
        self.assertLessEqual(np.max(np.abs(b['power']-self.base['power'])),8+1e-10)

    def test_whitebox_requires_instantaneous_channel_knowledge(self):
        d=scenario(self.base,self.c,'whitebox',23,np.array([-42.]))
        np.testing.assert_allclose(d['raw']-d['bias_est']+22*np.log10(d['d_claim']),-42,atol=1e-10)

    def test_calibration_unit_is_flight_max_not_packet(self):
        residual=np.arange(26*40)/100
        flights=np.repeat(np.arange(26),40)
        expected=np.sort([max(abs(residual[flights==f])) for f in range(26)])[24]
        self.assertEqual(conformal_radius(residual,flights,.9),expected)

    def test_gps_error_and_ideal_channel(self):
        self.assertTrue(np.any(self.base['d_true']!=self.base['d_claim']))
        d=generate(self.c,23,'test','ideal')
        np.testing.assert_array_equal(d['d_true'],d['d_claim'])
        self.assertFalse(d['nlos'].any());self.assertTrue(receive(d,self.c,'ideal')[0].all())


if __name__=='__main__':unittest.main()
