import unittest
from test_wifi_beacon_capture import BODY
from wifi_scan_capture import parse_scan, observations


def fixture(body=BODY):
    return '\n'.join(['BSS 02:00:00:00:00:01(on wlan0)', '\tlast seen: 26.274s [boottime]',
                      '\tfreq: 2412', '\tsignal: -61.00 dBm', '\tlast seen: 100 ms ago',
                      '\tSSID: SHOULD_NOT_BE_SAVED', '\tVendor specific: OUI fa:0b:bc, data: ' + body[3:].hex(' ')])


class ScanTests(unittest.TestCase):
    def test_vendor_decode_matches_raw_path_without_inventing_raw_frames(self):
        bss, = parse_scan(fixture())
        row, = observations(bss, 'fixture-node', 1700000000)
        self.assertEqual(row['rid_parse_status'], 'decoded')
        self.assertEqual(row['rssi_dbm'], -61)
        self.assertEqual(row['monotonic_time_us'], 26274000)
        self.assertIsNone(row['frame_digest'])
        self.assertEqual(row['physical_packet_match'], 'unconfirmed')
        self.assertFalse(row['cache_stale'])
        self.assertNotIn('SSID', str(row))

    def test_old_cache_is_not_new_reception(self):
        bss, = parse_scan(fixture().replace('100 ms ago', '733312 ms ago'))
        self.assertTrue(next(observations(bss, 'fixture-node', 1700000000))['cache_stale'])

    def test_missing_signal_and_age_remain_unknown(self):
        bss, = parse_scan('\n'.join(l for l in fixture().splitlines() if 'signal:' not in l and 'last seen:' not in l))
        row, = observations(bss, 'fixture-node', 1700000000)
        self.assertIsNone(row['rssi_dbm'])
        self.assertIsNone(row['received_at_utc'])
        self.assertTrue(row['cache_stale'])

    def test_wrong_vendor_and_short_payload_not_valid_rid(self):
        bss, = parse_scan(fixture().replace('fa:0b:bc', '00:11:22'))
        self.assertEqual(list(observations(bss, 'fixture', 1700000000)), [])
        bss, = parse_scan(fixture(bytes.fromhex('fa0bbc0d07')))
        self.assertEqual(next(observations(bss, 'fixture', 1700000000))['rid_parse_status'], 'invalid')


class AcquisitionTests(unittest.TestCase):
    def test_metrics_use_new_timestamped_rssi_not_polls_or_unknown_signal(self):
        from wifi_scan_capture import UpdateMetrics
        m = UpdateMetrics(20)
        bss, = parse_scan(fixture())
        row = next(observations(bss, 'fixture', 1700000000))
        m.add(dict(row, monotonic_time_us=19000000))  # before run
        for stamp in [21000000, 21000000, 23000000, 22000000, 25000000]:
            m.add(dict(row, monotonic_time_us=stamp))
        m.add(dict(row, monotonic_time_us=26000000, rssi_dbm=None))
        m.add(dict(row, monotonic_time_us=None))
        m.add(dict(row, monotonic_time_us=27000000, cache_stale=True))
        s = m.summary()
        self.assertEqual(s['current_run_timestamped_rssi_updates'], 3)
        self.assertEqual(s['interval_count'], 2)
        self.assertEqual(s['interval_median_s'], 2)
        self.assertEqual(s['missing_rssi_records'], 1)

    def test_metrics_do_not_combine_receivers_or_frequencies(self):
        from wifi_scan_capture import UpdateMetrics
        m = UpdateMetrics(20)
        row = next(observations(parse_scan(fixture())[0], 'fixture', 1700000000))
        m.add(dict(row, monotonic_time_us=21000000))
        m.add(dict(row, monotonic_time_us=22000000, bssid='02:00:00:00:00:02'))
        m.add(dict(row, monotonic_time_us=23000000, frequency_mhz=2452))
        self.assertEqual(m.summary()['interval_count'], 0)

    def exercise(self, results):
        from contextlib import nullcontext
        from io import StringIO
        from types import SimpleNamespace
        from unittest.mock import patch
        from wifi_scan_capture import capture
        now = [30.0]
        commands = []
        output, events = StringIO(), StringIO()
        iterator = iter(results)
        def run(command, **kwargs):
            commands.append((now[0], command))
            if 'trigger' in command:
                result = next(iterator)
                return SimpleNamespace(returncode=result, stderr='device busy' if result else '')
            stamp = now[0]
            return SimpleNamespace(stdout=fixture().replace('26.274s', f'{stamp}s'))
        args = SimpleNamespace(duration=5, interval=.1, scan_interval=.25,
                               active_scan=True, interface='wlan0', frequency=2412,
                               node_id='fixture', output='observations', events='events')
        with patch('wifi_scan_capture.private_output', side_effect=[nullcontext(output), nullcontext(events)]):
            code, summary = capture(args, '/sbin/iw', run=run, monotonic=lambda:now[0],
                                    sleep=lambda d:now.__setitem__(0,now[0]+d),
                                    boottime=lambda:30, wall=lambda:1700000000)
        return code, summary, commands, output.getvalue(), events.getvalue()

    def test_busy_backoff_and_deadline_flush_rssi(self):
        import json
        code, s, commands, out, events = self.exercise([1, 1, 0] + [0]*20)
        requests = [t for t, c in commands if 'trigger' in c]
        self.assertEqual(requests[:3], [30, 31, 33])
        self.assertEqual(code, 0)
        self.assertAlmostEqual(s['elapsed_s'], 5)
        self.assertEqual(s['counts']['scan_failed'], 2)
        rows = [json.loads(l) for l in out.splitlines()]
        self.assertTrue(rows)
        self.assertTrue(all(r['rssi_dbm'] == -61 and r['active_scan_requested'] for r in rows))
        self.assertNotIn('02:00:00', events)
        self.assertNotIn('SHOULD_NOT_BE_SAVED', events)

    def test_passive_mode_never_requests_scans(self):
        from contextlib import nullcontext
        from io import StringIO
        from types import SimpleNamespace
        from unittest.mock import patch
        from wifi_scan_capture import capture
        now = [30.0]
        commands = []
        def run(c, **kw):
            commands.append(c)
            return SimpleNamespace(stdout=fixture())
        args = SimpleNamespace(duration=1, interval=.25, scan_interval=1, active_scan=False,
                               interface='wlan0', frequency=None,node_id='fixture',output='output',events=None)
        with patch('wifi_scan_capture.private_output', return_value=nullcontext(StringIO())):
            code, s = capture(args,'iw',run=run,monotonic=lambda:now[0],
                              sleep=lambda d:now.__setitem__(0,now[0]+d),boottime=lambda:30)
        self.assertTrue(all('trigger' not in c for c in commands))
        self.assertFalse(s['active_scan_requested'])
        self.assertEqual(s['updates']['current_run_timestamped_rssi_updates'],0)

    def test_missing_timestamps_do_not_become_repeated_fresh_rssi(self):
        from wifi_scan_capture import UpdateMetrics
        m = UpdateMetrics(0)
        row=next(observations(parse_scan(fixture())[0], 'fixture', 1700000000))
        for _ in range(10):m.add(dict(row, monotonic_time_us=None))
        self.assertIsNone(m.summary()['interval_median_s'])
        self.assertEqual(m.summary()['current_run_timestamped_rssi_updates'],0)
