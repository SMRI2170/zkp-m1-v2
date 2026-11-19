import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from build_quality_manifest import POLICY,build,digest,load_selection,reasons
from analyze_claim_distance_rssi import retained


def row(**changes):
    return dict(dict(node='Pixel',quality='ELIGIBLE_TIME_POSITION',boot_scope='fixture-boot',
                     observed_us=1000000,fix_delta_s=2,accuracy_m=20,
                     claimed_horizontal_distance_m=80,rssi_dbm=-60),**changes)


class QualityManifestTests(unittest.TestCase):
    def test_boundary_and_existing_gate(self):
        for r in [row(),row(accuracy_m=20.01),row(claimed_horizontal_distance_m=79.9),row(rssi_dbm='nan')]:
            self.assertEqual(not reasons(r),retained(r))
        self.assertEqual(reasons(row()),[])

    def test_missing_clock_and_invalid_numeric_fail_closed(self):
        for changes,reason in [({'boot_scope':'unknown-fixture'},'BOOT_UNKNOWN'),
                               ({'observed_us':0},'OBSERVATION_TIME_INVALID'),
                               ({'fix_delta_s':2.00001},'FIX_TIME_DELTA_INVALID'),
                               ({'accuracy_m':-1},'OS_ACCURACY_OUTSIDE_POLICY'),
                               ({'rssi_dbm':float('inf')},'RSSI_INVALID'),
                               ({'accuracy_m':True},'OS_ACCURACY_OUTSIDE_POLICY')]:
            self.assertIn(reason,reasons(row(**changes)))

    def test_association_failure_is_retained_as_reason(self):
        self.assertIn('UPSTREAM_ASSOCIATION_NOT_ELIGIBLE',reasons(row(quality='STALE_WIFI_OBSERVATION')))

    def evidence(self):
        return ({'nodes':{'Pixel':dict(target_rows=2,input_unchanged=True)}},
                {'nodes':{'Pixel':dict(saved_rows=2,input_unchanged=True,observation_keys=2,distinct_pack_contents=1)}},
                {'nodes':{'Pixel':dict(retained_rows=1)}})

    def test_denominators_and_nonexclusive_reasons(self):
        a,b,c=self.evidence();m,n=build([row(),row(accuracy_m=21,rssi_dbm='nan')],a,b,c)
        self.assertEqual([x['selected'] for x in m],[True,False])
        self.assertEqual(sum(n['Pixel']['exclusive_hold_reasons'].values()),1)
        self.assertEqual(sum(n['Pixel']['nonexclusive_hold_reasons'].values()),3)
        self.assertEqual(n['Pixel']['held_rows'],1)

    def test_inconsistent_evidence_is_not_silently_reconciled(self):
        for kind in ['count','changed','gate']:
            a,b,c=self.evidence()
            if kind=='count':b['nodes']['Pixel']['saved_rows']=3
            if kind=='changed':a['nodes']['Pixel']['input_unchanged']=False
            if kind=='gate':c['nodes']['Pixel']['retained_rows']=2
            with self.assertRaises(ValueError):build([row(),row(rssi_dbm='nan')],a,b,c)

    def test_unknown_node_is_rejected(self):
        with self.assertRaises(ValueError):build([row(node='unknown')],*self.evidence())

    def test_private_frozen_mask_rejects_tampering_and_changed_input(self):
        root=Path(__file__).resolve().parents[2]/'captures'
        root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as d:
            p=Path(d)/'input.csv';p.write_text('synthetic fixture\n');p.chmod(0o600)
            m=Path(d)/'mask.json';rows=[row()]
            data=dict(format='week29_quality_mask_v1',policy=POLICY,position_csv_sha256=digest(p),
                      rows=[dict(row_index=0,selected=True,reasons=[])])
            m.write_text(json.dumps(data));m.chmod(0o600)
            self.assertEqual(load_selection(m,p,rows),rows)
            data['rows'][0]['selected']=False;m.write_text(json.dumps(data))
            with self.assertRaises(ValueError):load_selection(m,p,rows)
            p.write_text('changed\n')
            with self.assertRaises(ValueError):load_selection(m,p,rows)

    def test_no_physical_guarantees_enabled_by_selection(self):
        for key in ['independent_truth_verified','cross_device_time_verified',
                    'same_physical_transmission_verified','vertical_reference_verified']:
            self.assertIs(POLICY[key],False)

if __name__=='__main__':unittest.main()
