import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from permission_evidence import permission_granted,active_location_requests,stored_fix_providers

class PermissionEvidenceTests(unittest.TestCase):
    def test_no_service_samples_is_not_a_liveness_success(self):
        import tempfile,sqlite3
        from smoke_device_persistence import analyze_database
        with tempfile.TemporaryDirectory() as d:
            paths=[]
            for name in ('before','after'):
                p=Path(d)/(name+'.sqlite');paths.append(p)
                with sqlite3.connect(p) as db:db.execute('CREATE TABLE observations(id TEXT,raw_json TEXT,text_line TEXT)')
            result=analyze_database(*paths,[dict(name='no_samples',start_us=0,end_us=2000000,samples=[])])
            self.assertIsNone(result['phases'][0]['foreground_service_all_samples'])
    def test_complete_empty_asus_runtime_list_denies_declared_runtime_permission(self):
        text='requested permissions:\n android.permission.ACCESS_FINE_LOCATION\n install permissions:\n runtime permissions:\n\nAsus Customized Information:'
        self.assertFalse(permission_granted(text,'ACCESS_FINE_LOCATION'))
        self.assertIsNone(permission_granted(text.replace('Asus Customized Information:',''),'ACCESS_FINE_LOCATION'))
        self.assertIsNone(permission_granted(text,'ACCESS_COARSE_LOCATION'))
    def test_missing_permission_is_unknown(self):
        self.assertIsNone(permission_granted('requested permissions: android.permission.ACCESS_FINE_LOCATION','ACCESS_FINE_LOCATION'))
    def test_grant_is_not_inferred_from_another_permission(self):
        package='  android.permission.ACCESS_FINE_LOCATION: granted=false, flags=[ USER_SET ]\n  android.permission.ACCESS_COARSE_LOCATION: granted=true, flags=[]'
        self.assertFalse(permission_granted(package,'ACCESS_FINE_LOCATION'));self.assertTrue(permission_granted(package,'ACCESS_COARSE_LOCATION'))
    def test_historical_or_cached_location_is_not_active_request(self):
        text='Active Records by Provider:\n gps:\nHistorical Records by Provider:\n app: gps: Interval 1 seconds\nLast Known Locations:\n UpdateRecord[gps app Request[]]'
        self.assertEqual(active_location_requests(text,'app'),{'gps':False,'network':False})
    def test_exact_package_and_provider_only(self):
        text='UpdateRecord[gps app.other Request[]]\n UpdateRecord[network app(12345) Request[]]'
        self.assertEqual(active_location_requests(text,'app'),{'gps':False,'network':True})
    def test_provider_summary_does_not_copy_coordinates_or_unknown_provider_text(self):
        self.assertEqual(stored_fix_providers([{'provider':'gps','latitude':12},{'provider':'private data'},{'provider':'network'}]),{'gps':1,'other_or_unknown':1,'network':1})

class ExternalDialogTests(unittest.TestCase):
    def test_only_known_play_store_crash_can_be_closed(self):
        from permission_evidence import known_play_store_crash_close
        text='<hierarchy><node package="android" text="Google Play ストア が停止しました"/><node package="android" text="アプリを閉じる" enabled="true" bounds="[1,2][3,4]"/></hierarchy>'
        self.assertEqual(known_play_store_crash_close(text),(1,2,3,4))
        self.assertIsNone(known_play_store_crash_close(text.replace('Google Play ストア','別のアプリ')))
    def test_app_dialog_or_permission_request_is_not_dismissed(self):
        from permission_evidence import known_play_store_crash_close
        text='<hierarchy><node package="com.android.packageinstaller" text="Google Play ストア に位置を許可"/><node package="android" text="アプリを閉じる" enabled="true" bounds="[1,2][3,4]"/></hierarchy>'
        self.assertIsNone(known_play_store_crash_close(text))

class SnapshotRecoveryTests(unittest.TestCase):
    def test_hot_journal_is_recovered_without_changing_raw_evidence(self):
        import tempfile,sqlite3,subprocess,hashlib
        from permission_evidence import recover_private_snapshot
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'source.sqlite'
            with sqlite3.connect(source) as db:
                db.execute('CREATE TABLE items(value TEXT)');db.execute("INSERT INTO items VALUES('committed')")
            code="import sqlite3,sys,os; c=sqlite3.connect(sys.argv[1]); c.execute('PRAGMA cache_size=1'); c.execute('BEGIN IMMEDIATE'); c.execute(\"UPDATE items SET value=printf('%020000d',1)\"); os._exit(0)"
            subprocess.run([sys.executable,'-c',code,str(source)],check=True)
            journal=Path(str(source)+'-journal');self.assertTrue(journal.exists())
            hashes=[hashlib.sha256(p.read_bytes()).hexdigest() for p in (source,journal)]
            dest=recover_private_snapshot(source,journal,root/'derived.sqlite')
            with sqlite3.connect(dest) as db:self.assertEqual(db.execute('SELECT value FROM items').fetchone()[0],'committed')
            self.assertEqual(hashes,[hashlib.sha256(p.read_bytes()).hexdigest() for p in (source,journal)])
    def test_clean_database_is_copied_without_journal(self):
        import tempfile,sqlite3
        from permission_evidence import recover_private_snapshot
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'source.sqlite'
            with sqlite3.connect(source) as db:db.execute('CREATE TABLE items(value TEXT)')
            dest=recover_private_snapshot(source,None,Path(d)/'derived.sqlite')
            self.assertTrue(dest.exists());self.assertEqual(dest.stat().st_mode & 0o777,0o600)

if __name__=='__main__':unittest.main()
