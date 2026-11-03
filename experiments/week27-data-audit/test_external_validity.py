import unittest
import numpy as np
from audit_loraiq import group_audit
from cluster_uncertainty import condition_matrix,resample,VARIANTS

class ExternalValidityTests(unittest.TestCase):
    def frame(self,receiver='1',**changes):
        row=dict(name='flight',transmission_idx='1',rrh_idx=receiver,latitude='1',longitude='2',
                 payload_base64='abc',sf='10',cr='1',fc='862500000',bandwidth='250000',area='uav',
                 area_type='drone_los',rx_timestamp_full='100',rx_timestamp_frac='.1')
        row.update(changes);return row
    def test_missing_or_conflicting_position_not_strictly_admitted(self):
        result=group_audit([self.frame(),self.frame('2',latitude='')])
        self.assertEqual(result['complete_consistent_multi_receiver_groups'],0)
        self.assertEqual(result['inconsistent_identity_or_position_groups'],1)
        result=group_audit([self.frame(),self.frame('2',payload_base64='wrong')])
        self.assertEqual(result['field_conflict_groups']['payload_base64'],1)
    def test_session_scopes_frame_id_and_duplicate_receiver_is_visible(self):
        result=group_audit([self.frame(),self.frame(),self.frame(name='another')])
        self.assertEqual(result['transmissions'],2);self.assertEqual(result['duplicate_receiver_groups'],1)
    def test_valid_multi_receiver_group(self):
        result=group_audit([self.frame(),self.frame('2',rx_timestamp_frac='.101')])
        self.assertEqual(result['complete_consistent_multi_receiver_groups'],1)
        self.assertAlmostEqual(result['receive_timestamp_spread_max_s'],.001)
    def paired_rows(self):
        return [dict(direction='outward',claim_horizontal_shift_m='100',condition=c,variant=v,
                     evaluation_run=str(run),alarm_rate=str(.1 if v in ('normal','exact_compensation') else .5))
                for c in ['a','b'] for v in VARIANTS for run in range(3)]
    def test_resample_keeps_variants_paired_and_constant_endpoint(self):
        _,matrix=condition_matrix(self.paired_rows());b=resample(matrix,replicates=100)
        np.testing.assert_array_equal(b[:,0],b[:,2]);np.testing.assert_allclose(b[:,1],.5)
        np.testing.assert_array_equal(b,resample(matrix,replicates=100))
    def test_duplicate_or_missing_eval_run_fails(self):
        rows=self.paired_rows()
        with self.assertRaises(ValueError):condition_matrix(rows+rows[:1])
        with self.assertRaises(ValueError):condition_matrix(rows[1:])

if __name__=='__main__':unittest.main()
