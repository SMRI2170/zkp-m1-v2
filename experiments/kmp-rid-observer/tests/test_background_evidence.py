import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from background_evidence import study_ids,target_counts,doze_verified,in_phase

class BackgroundEvidenceTests(unittest.TestCase):
    def test_android_and_pi_schema_match_same_controlled_identity(self):
        self.assertEqual(study_ids({'rid_messages':[{'uas_id':'TEST'}]}),{'TEST'})
        self.assertEqual(study_ids({'claimed_uas_ids':['TEST']}),{'TEST'})
        self.assertEqual(study_ids({'rid_messages':[{},None,{'uas_id':None}]}),set())
    def test_unrelated_fresh_wifi_is_not_controlled_source_success(self):
        rows=[dict(monotonic_time_us=1500000,cache_stale=False,rid_messages=[{'uas_id':'OTHER'}])]
        self.assertEqual(target_counts(rows,1000000,2000000,'TEST')['target_records'],0)
    def test_stale_and_unknown_caches_do_not_count_as_new_contents(self):
        rows=[dict(monotonic_time_us=1500000,cache_stale=v,rid_messages=[{'uas_id':'TEST'}],vendor_content_digest='fixture') for v in [True,None,False,False]]
        result=target_counts(rows,1000000,2000000,'TEST');self.assertEqual(result['target_records'],4);self.assertEqual(result['target_fresh_records'],2);self.assertEqual(result['target_distinct_vendor_contents'],1)
    def test_light_idle_is_not_deep_idle(self):
        self.assertFalse(doze_verified('mState=ACTIVE mLightState=IDLE'));self.assertTrue(doze_verified('mState=IDLE mLightState=OVERRIDE'))
    def test_phase_boundaries_and_invalid_time_are_not_accepted(self):
        self.assertFalse(in_phase(1000001,1000000,2000000));self.assertFalse(in_phase(float('nan'),1000000,2000000));self.assertFalse(in_phase(None,1000000,2000000));self.assertTrue(in_phase(1500000,1000000,2000000))

class DatabasePositionEvidenceTests(unittest.TestCase):
    def test_android_id_and_standalone_fix_stream_survive_snapshot_merge(self):
        import tempfile,sqlite3,json
        import smoke_device_persistence as smoke
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for name,extra in [('before',False),('after',True)]:
                p=root/(name+'-source.sqlite')
                with sqlite3.connect(p) as db:
                    db.execute('CREATE TABLE observations(id INTEGER,raw_json TEXT,text_line TEXT)')
                    db.execute('CREATE TABLE receiver_fixes(id INTEGER,raw_json TEXT)')
                    db.execute('INSERT INTO observations VALUES(1,?,?)',(json.dumps({'monotonic_time_us':100}),'old'))
                    db.execute('INSERT INTO receiver_fixes VALUES(1,?)',(json.dumps({'fix_elapsed_us':100,'provider':'network'}),))
                    if extra:
                        db.execute('INSERT INTO observations VALUES(2,?,?)',(json.dumps({'monotonic_time_us':1500000,'cache_stale':False,'rid_messages':[{'uas_id':'TEST'}]}),'new'))
                        db.execute('INSERT INTO receiver_fixes VALUES(2,?)',(json.dumps({'fix_elapsed_us':1500000,'provider':'network'}),))
                smoke.merge_database_snapshots([('stable-segment-label',p)],root/(name+'.sqlite'))
            result=smoke.analyze_database(root/'before.sqlite',root/'after.sqlite',[dict(name='screen_off',start_us=1000000,end_us=2000000,samples=[dict(foreground_service=True,pss_kib=None)])],target_id='TEST')
            self.assertTrue(result['old_standalone_fixes_unchanged']);self.assertEqual(result['phases'][0]['standalone_fixes_stored'],1);self.assertEqual(result['phases'][0]['target_records'],1)

if __name__=='__main__':unittest.main()
