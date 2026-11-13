import sys,time,unittest,struct
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'uav'))
from flight_sensors import parse_gga,gps_snapshot,pressure_height
from flight_payload import build_ie
from flight_beacon import choose_channel
from install_flight import units
from observer_capture import parse_rid_payload
from adaptive_scan import AdaptiveScanPlan
from wifi_scan_capture import parse_scan


def sentence(quality='1',msl='100.0',geoid='30.0'):
    body=f'GNGGA,120102.50,0100.0000,N,00200.0000,E,{quality},10,0.8,{msl},M,{geoid},M,,'
    checksum=0
    for b in body.encode():checksum^=b
    return '$'+body+'*'+f'{checksum:02X}'


class FlightSensorTests(unittest.TestCase):
    def test_gps_msl_and_ellipsoid_are_separate(self):
        d=parse_gga(sentence());self.assertEqual(d['altitude_msl_m'],100)
        self.assertEqual(d['geoid_separation_m'],30);self.assertEqual(d['altitude_ellipsoid_m'],130)
        self.assertEqual(d['seconds_within_hour'],62.5)
        self.assertEqual(parse_gga(sentence(msl='-20'))['altitude_ellipsoid_m'],10)

    def test_no_fix_missing_geoid_checksum_and_stale(self):
        self.assertFalse(parse_gga(sentence(quality='0'))['valid'])
        self.assertIsNone(parse_gga(sentence(geoid=''))['altitude_ellipsoid_m'])
        with self.assertRaises(ValueError):parse_gga(sentence()[:-2]+'00')
        sample=dict(parse_gga(sentence()),received_monotonic_s=1)
        stale=gps_snapshot(sample,10);self.assertFalse(stale['valid']);self.assertNotIn('latitude',stale)
        self.assertFalse(gps_snapshot(None,1)['valid'])

    def test_pressure_reference_is_explicit(self):
        self.assertAlmostEqual(pressure_height(1000,1000),0)
        self.assertGreater(pressure_height(990,1000),0)
        self.assertNotEqual(pressure_height(1000,1000),pressure_height(1000,1013.25))
        self.assertIsNone(pressure_height(0,1000))

    def test_wire_gps_and_baro_roundtrip(self):
        gps=dict(parse_gga(sentence()),received_monotonic_s=10)
        sensor=dict(host_monotonic_s=10,gps=gps,bme280=dict(valid=True,measurement_monotonic_s=10,pressure_altitude_isa_m=50))
        ie,meta=build_ie('PI-RID-TEST-A',7,sensor,10.1)
        messages=[m for _,m in parse_rid_payload(ie[7:])]
        self.assertTrue(meta['location_included']);self.assertEqual(len(messages),2)
        self.assertEqual(messages[0].id_type,4)
        self.assertEqual(messages[1].altitude_geo_m,130)
        self.assertEqual(messages[1].altitude_baro_m,50)
        raw=ie[7+3+25:];self.assertEqual(raw[1]>>4,0) # no fabricated airborne state
        self.assertEqual(raw[2:5],bytes([181,255,126]))

    def test_stale_or_unavailable_gps_sends_id_only(self):
        for sensor in [None,dict(host_monotonic_s=1,gps=dict(valid=True,received_monotonic_s=1))]:
            ie,meta=build_ie('PI-RID-TEST-A',0,sensor,10)
            self.assertFalse(meta['location_included']);self.assertEqual(len(ie),35)
        with self.assertRaises(ValueError):build_ie('DJI-SERIAL',0,None,0)

    def test_standard_unknown_altitude_zero_does_not_become_minus_1000(self):
        sensor=dict(host_monotonic_s=10,gps=dict(parse_gga(sentence(geoid='')),received_monotonic_s=10),bme280=dict(valid=False))
        ie,_=build_ie('PI-RID-TEST-A',0,sensor,10)
        messages=[m for _,m in parse_rid_payload(ie[7:])]
        self.assertIsNone(messages[1].altitude_geo_m);self.assertIsNone(messages[1].altitude_baro_m)
        self.assertEqual(messages[1].altitude_geo_raw,0)

    def test_adaptive_scan_keeps_discovery_and_multiple_sources(self):
        p=AdaptiveScanPlan();self.assertIsNone(p.choose(0));p.accepted(None,0)
        p.learn(dict(frequency_mhz=2452,cache_stale=False),1)
        p.learn(dict(frequency_mhz=2437,cache_stale=False),2)
        self.assertEqual(p.choose(3),(2437,2452));self.assertIsNone(p.choose(31))
        p.accepted(None,31);self.assertEqual(p.choose(32),(2437,2452))
        self.assertIsNone(p.choose(200))

    def test_decimal_iw_frequency_is_normalized_without_rounding_fractional_channels(self):
        base='BSS 02:00:00:00:00:01(on wlan0)\n\tfreq: '
        self.assertEqual(parse_scan(base+'2452.0')[0]['frequency_mhz'],2452)
        self.assertEqual(parse_scan(base+'2452')[0]['frequency_mhz'],2452)
        self.assertIsNone(parse_scan(base+'2452.5')[0]['frequency_mhz'])

    def test_station_channel_and_standalone_modes_do_not_force_station_retune(self):
        self.assertEqual(choose_channel(''),(6,2437,'standalone_default_no_reported_station_channel'))
        self.assertEqual(choose_channel('channel 9 (2452 MHz)')[0],9)
        with self.assertRaises(ValueError):choose_channel('channel 44 (5220 MHz)')
        generated=units(Path('/home/pi/zkp-beacon-observer/releases/test'),Path('/home/pi/zkp-beacon-observer'))
        self.assertIn('SupplementaryGroups=dialout i2c',generated['zkp-flight-sensors.service'])
        self.assertIn('CAP_NET_ADMIN CAP_NET_RAW',generated['zkp-flight-marker.service'])
        self.assertNotIn('network-online.target',generated['zkp-flight-marker.service'])

    def test_stale_frequency_is_not_learned_and_budget_is_bounded(self):
        p=AdaptiveScanPlan(max_frequencies=2);p.accepted(None,0)
        p.learn(dict(frequency_mhz=2412,cache_stale=True),1);self.assertFalse(p.known)
        for i,f in enumerate([2412,2437,2452]):p.learn(dict(frequency_mhz=f,cache_stale=False),i+1)
        self.assertEqual(len(p.known),2);self.assertNotIn(2412,p.known)


if __name__=='__main__':unittest.main()
