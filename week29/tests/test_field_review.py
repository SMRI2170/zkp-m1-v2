import copy,json,math,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from audit_frozen_field_rows import row_consistency,raw_gate,same_number
from audit_android_position import fix_key,horizontal_distance
from diagnose_frozen_proxy import transitions,merge_small_blocks,selection_sensitivity
from render_field_review import synthetic_explanation,private_view


def fixture():
    fix=dict(latitude=0.,longitude=0.,accuracy_m=1.,fix_elapsed_us=1000000,provider='network',mock=False)
    raw=dict(receiver_position={**fix,'match_status':'MATCHED','scan_delta_us':0},cache_stale=False,boot_scope='b1',monotonic_time_us=1000000,delivered_elapsed_us=1100000,rssi_dbm=-60)
    ref=dict(location_valid=True,claimed_latitude=0.,claimed_longitude=.0001)
    row=dict(node='fixture',quality='ELIGIBLE_TIME_POSITION',boot_scope='b1',observed_us='1000000',fix_delta_s='0',accuracy_m='1',claimed_horizontal_distance_m=str(horizontal_distance(0,0,0,.0001)),receiver_latitude='0',receiver_longitude='0',claimed_latitude='0',claimed_longitude='.0001',rssi_dbm='-60')
    index={fix_key('b1',fix):[fix]}
    return row,raw,ref,index

class RawEvidenceTests(unittest.TestCase):
    def test_join_requires_independent_standalone_fix_agreement(self):
        row,raw,ref,index=fixture();self.assertEqual(row_consistency(row,raw,ref,index),'ELIGIBLE_TIME_POSITION')
        bad=copy.deepcopy(index);next(iter(bad.values()))[0]['accuracy_m']=2
        with self.assertRaises(ValueError):row_consistency(row,raw,ref,bad)
    def test_csv_claim_or_rssi_tamper_stops_audit(self):
        row,raw,ref,index=fixture()
        for key,value in [('claimed_longitude','.0002'),('rssi_dbm','-40')]:
            with self.assertRaises(ValueError):row_consistency({**row,key:value},raw,ref,index)
    def test_raw_mock_unknown_freshness_and_future_delivery_are_rejected(self):
        row,raw,ref,index=fixture()
        self.assertEqual(raw_gate(row,raw,'ELIGIBLE_TIME_POSITION'),[])
        for stale in (True,None):self.assertIn('RAW_FRESHNESS_NOT_CONFIRMED',raw_gate(row,{**raw,'cache_stale':stale},'ELIGIBLE_TIME_POSITION'))
        self.assertIn('RAW_MOCK_OR_UNKNOWN',raw_gate(row,{**raw,'receiver_position':{**raw['receiver_position'],'mock':True}},'ELIGIBLE_TIME_POSITION'))
        self.assertIn('RAW_DELIVERY_TIME_INVALID',raw_gate(row,{**raw,'delivered_elapsed_us':999999},'ELIGIBLE_TIME_POSITION'))
    def test_nonfinite_and_boolean_are_not_numbers(self):
        self.assertFalse(same_number('nan',1));self.assertFalse(same_number(True,1));self.assertTrue(same_number('1',1))

class ProxyDiagnosisTests(unittest.TestCase):
    def test_paired_transition_denominators_do_not_call_old_alarms_new_detections(self):
        r=transitions([(0,0),(0,4),(4,0),(4,4)],3)
        self.assertEqual([r[x] for x in ('quiet_to_quiet','quiet_to_alarm','alarm_to_quiet','alarm_to_alarm')],[1,1,1,1]);self.assertEqual(r['n'],4)
    def test_exact_threshold_does_not_trigger_alarm(self):self.assertEqual(transitions([(3,3)],3)['quiet_to_quiet'],1)
    def test_small_tail_blocks_are_merged_without_discarding_rows(self):
        data=[dict(time=i*31) for i in range(11)];g=merge_small_blocks(data);self.assertEqual([len(x) for x in g],[5,6]);self.assertEqual(sum(map(len,g)),11)
    def test_too_few_rows_do_not_publish_a_single_event_block(self):self.assertEqual(merge_small_blocks([dict(time=0),dict(time=100)]),[])
    def test_claim_dependent_gate_changes_are_reported_without_mutating_selection(self):
        row,*_=fixture();row['claimed_horizontal_distance_m']='2';before=copy.deepcopy(row)
        result=selection_sensitivity([row],(20,))[0];self.assertEqual(result['baseline_selected'],0);self.assertEqual(result['newly_admitted'],1);self.assertEqual(row,before)
    def test_matched_power_explanation_has_the_correct_sign_and_scope(self):
        x=synthetic_explanation();self.assertAlmostEqual(x['delta_power'],-12.041199826559248);self.assertAlmostEqual(x['claim_only_score'],12.041199826559248);self.assertAlmostEqual(x['compensated_score'],0);self.assertIn('synthetic',x['source'])
    def test_single_rssi_two_physical_worlds_are_identical(self):
        # 10m at reference power and 40m at +12.0412dB are observationally equal.
        r1=-40-20*math.log10(10);r2=-40+12.041199826559248-20*math.log10(40)
        self.assertAlmostEqual(r1,r2)

class ViewerPrivacyTests(unittest.TestCase):
    def test_embedded_private_event_cannot_break_out_of_script(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'private.html';private_view([{'ordinal':0,'truth':'</script><img src=x onerror=alert(1)>'}],{'frozen_model':{'threshold_db':3}},p)
            text=p.read_text();self.assertNotIn('</script><img',text);self.assertIn('\\u003c/script>',text);self.assertEqual(p.stat().st_mode&0o777,0o600)

class FigureEvidenceTests(unittest.TestCase):
    def test_non_native_artist_numbers_are_serializable(self):
        from decimal import Decimal
        from render_field_review import serializable_series
        r=serializable_series([dict(name='fixture',drawn=[Decimal('13'),Decimal('14')])]);self.assertEqual(json.loads(json.dumps(r))[0]['drawn'],[13.,14.])
    def test_nonfinite_artist_values_stop_publication(self):
        from render_field_review import serializable_series
        with self.assertRaises(ValueError):serializable_series([dict(name='fixture',drawn=[float('nan')])])
    def test_public_chart_artists_match_aggregates_and_denominators(self):
        from validate_field_review import validate
        result=validate(Path(__file__).resolve().parents[1]/'results/research-review-20261119-f')
        self.assertEqual(result['figure_series_checked'],7);self.assertEqual(result['paired_conditions_checked'],81)
    def test_changed_bar_height_is_detected(self):
        import shutil
        from validate_field_review import validate
        with tempfile.TemporaryDirectory() as d:
            dest=Path(d)/'results';shutil.copytree(Path(__file__).resolve().parents[1]/'results/research-review-20261119-f',dest)
            p=dest/'figure-series.json';s=json.loads(p.read_text());s[0]['drawn'][0]+=1;p.write_text(json.dumps(s))
            with self.assertRaisesRegex(ValueError,'Figure differs'):validate(dest)

if __name__=='__main__':unittest.main()
