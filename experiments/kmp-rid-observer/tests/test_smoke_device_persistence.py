import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS=Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0,str(SCRIPTS))
import smoke_device_persistence as smoke


class DeviceEvidenceTests(unittest.TestCase):
    def test_android7_and_new_pss_formats_preserve_unknown(self):
        self.assertEqual(smoke.pss_kib('  TOTAL 12345 234 999\n'),12345)
        self.assertEqual(smoke.pss_kib(' TOTAL PSS: 45678 TOTAL RSS: 0\n'),45678)
        self.assertIsNone(smoke.pss_kib('service unavailable'))

    def test_phase_separates_stale_and_excludes_boundary_observations(self):
        rows=[dict(monotonic_time_us=t,cache_stale=stale,direction=direction) for t,stale,direction in [
            (1_000_001,False,None),(1_200_000,False,dict(missing_reason=None,phone_heading_magnetic_deg=90)),
            (1_400_000,True,dict(missing_reason='STALE',phone_heading_magnetic_deg=None)),(1_999_999,False,None)]]
        result=smoke.phase_counts(rows,1_000_000,2_000_000)
        self.assertEqual(result,dict(scan_records=2,fresh_records=1,heading_matched_records=1))

    def test_disabled_control_is_not_clicked(self):
        class Fake:
            ui_path='test.xml'
            def __init__(self):self.reads=0;self.taps=[]
            def shell(self,*args):
                if args[:1]==('cat',):
                    self.reads+=1
                    enabled='false' if self.reads==1 else 'true'
                    return '<hierarchy><node package="'+smoke.PKG+'" text="記録開始" enabled="'+enabled+'" bounds="[0,0][20,20]"/></hierarchy>'
                if args[:2]==('input','tap'):self.taps.append(args)
                return ''
        d=Fake()
        with patch.object(smoke.time,'sleep'):smoke.tap_enabled(d,'記録開始')
        self.assertEqual(d.reads,2)
        self.assertEqual(len(d.taps),1)

    def test_secure_lockscreen_is_never_dismissed(self):
        class Fake:
            def __init__(self,secure):self.secure=secure;self.calls=[]
            def shell(self,*args):
                self.calls.append(args)
                return 'showing=true\nsecure='+self.secure+'\n' if args[:1]==('dumpsys',) else ''
        secure=Fake('true')
        with self.assertRaises(RuntimeError):smoke.wake_app(secure)
        self.assertNotIn(('input','keyevent','KEYCODE_MENU'),secure.calls)
        swipe=Fake('false');smoke.wake_app(swipe)
        self.assertIn(('input','keyevent','KEYCODE_MENU'),swipe.calls)

    def test_database_analyzer_detects_old_row_modification(self):
        def make(path,rows):
            with sqlite3.connect(path) as c:
                c.execute('create table observations(id integer primary key, raw_json text,text_line text)')
                c.executemany('insert into observations values (?,?,?)',rows)
        old_json=json.dumps(dict(monotonic_time_us=10,cache_stale=False))
        new_json=json.dumps(dict(monotonic_time_us=1_300_000,cache_stale=False,direction=None))
        with tempfile.TemporaryDirectory() as d:
            before=Path(d)/'before.sqlite';after=Path(d)/'after.sqlite'
            make(before,[(1,old_json,'raw_vendor_ie_hex=00')])
            make(after,[(1,old_json,'MODIFIED'),(2,new_json,'raw_vendor_ie_hex=01')])
            phases=[dict(name='home_screen',start_us=1_000_000,end_us=2_000_000,
                samples=[dict(foreground_service=True,pss_kib=None)])]
            r=smoke.analyze_database(before,after,phases)
            self.assertFalse(r['old_rows_unchanged'])
            self.assertEqual(r['new_rows'],1)
            self.assertEqual(r['phases'][0]['fresh_records'],1)
            self.assertIsNone(r['phases'][0]['pss_max_kib'])
            self.assertEqual(r['integrity_check'],'ok')


if __name__=='__main__':unittest.main()
