"""Regression checks for missing/partial metrics and cross-host scope."""
import csv,json,tempfile,unittest
from pathlib import Path
from collect import Inputs,normalize,coverage,write_table

class PlotDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records=normalize(Inputs());cls.coverage=coverage(Inputs(),cls.records)
    def test_every_framework_has_a_status_and_failed_proof_is_not_zero(self):
        self.assertEqual(len(self.coverage),18)
        self.assertEqual(len({x['framework'] for x in self.coverage}),18)
        sp1=[r for r in self.records if r['framework']=='SP1' and r['host']=='Mac ARM64']
        self.assertEqual(len(sp1),2)
        for r in sp1:
            self.assertIsNone(r['flow_mean_ms']);self.assertIsNone(r['proof_bytes'])
            self.assertGreater(r['observed_peak_bytes'],0);self.assertIsNone(r['kernel_peak_bytes'])
    def test_partial_and_ivc_are_not_promoted_to_final_proof_metrics(self):
        p=next(r for r in self.records if r['framework']=='Plonky2' and r['host'].startswith('Pi'))
        self.assertEqual(p['samples'],2);self.assertEqual(p['status'],'partial')
        self.assertIsNone(p['kernel_peak_bytes']);self.assertIsNone(p['memory_mean_bytes'])
        self.assertEqual(p['proof_scope'],'proof + public 16B')
        for r in self.records:
            if r['ivc_only']:self.assertIsNone(r['proof_bytes']);self.assertEqual(r['status'],'ivc_only')
    def test_signed_mac_result_does_not_create_a_distance_success(self):
        s=next(x for x in self.coverage if x['framework']=='gnark Groth16')
        self.assertEqual(s['mac_distance'],'not_summarized');self.assertEqual(s['pi_signed'],'verified')
        cohort=next(x for x in self.records if x['cohort']=='pi_affinity1')
        self.assertIsNone(cohort['cpu_quota_percent'])
    def test_csv_missing_metrics_stay_empty(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'x.csv';write_table(path,[{'proof_bytes':None,'samples':0}])
            with path.open() as f:row=list(csv.DictReader(f))[0]
        self.assertEqual(row['proof_bytes'],'');self.assertEqual(row['samples'],'0')

if __name__=='__main__':unittest.main()
