import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from unittest.mock import MagicMock

from audit_receivers import GIB,RESERVE,Transport,capacity,cycle,private_path,rate,sample_state,settings


class ReceiverAuditTests(unittest.TestCase):
    def sample(self,**changes):
        s=dict(node_id='observer-b',hostname='observer-b',boot_id='synthetic-boot',remote_monotonic_s=10,
            service_query_ok=True,service=dict(ActiveState='active'),disk_free_bytes=5*GIB,
            config_sha256={'node.json':'fixture'},meminfo={'MemAvailable':256*1024**2},
            storage_status=dict(session_id='synthetic-session',boot_id='synthetic-boot',state='CAPTURE_ACTIVE',
                updated_monotonic_s=10,records_written=1,session_bytes=100,byte_budget=GIB))
        s.update(changes);return s

    def test_waiting_is_not_rf_reception_and_stop_is_not_link_loss(self):
        s=self.sample();self.assertEqual(sample_state(s,'observer-b'),'RECORDER_ACTIVE')
        s['storage_status']['records_written']=0
        self.assertEqual(sample_state(s,'observer-b'),'WAITING_FOR_OBSERVATIONS')
        s['storage_status']['state']='SESSION_BUDGET_REACHED'
        self.assertEqual(sample_state(s,'observer-b'),'STORAGE_STOPPED')

    def test_identity_old_boot_stale_and_malformed_heartbeat(self):
        self.assertEqual(sample_state(self.sample(hostname='wrong'),'observer-b'),'IDENTITY_MISMATCH')
        self.assertEqual(sample_state(self.sample(boot_id='new'),'observer-b'),'PREVIOUS_BOOT_HEARTBEAT')
        self.assertEqual(sample_state(self.sample(remote_monotonic_s=131),'observer-b'),'STORAGE_HEARTBEAT_STALE')
        self.assertEqual(sample_state(self.sample(remote_monotonic_s=None),'observer-b'),'STORAGE_HEARTBEAT_INVALID')
        s=self.sample();s['storage_status']['records_written']='bad'
        self.assertEqual(sample_state(s,'observer-b'),'STORAGE_COUNTER_INVALID')

    def test_no_rate_across_boot_session_counter_reset(self):
        a=self.sample();b=self.sample(remote_monotonic_s=20)
        b['storage_status'].update(session_bytes=1100,updated_monotonic_s=20)
        self.assertEqual(rate(a,b),(100,'OBSERVED_SESSION_COUNTER_RATE'))
        self.assertIsNone(rate(None,b)[0])
        self.assertEqual(rate(a,dict(b,boot_id='other'))[1],'BOOT_CHANGED')
        b['storage_status']['session_id']='other'
        self.assertEqual(rate(a,b)[1],'SESSION_CHANGED')
        b['storage_status'].update(session_id='synthetic-session',session_bytes=1)
        self.assertEqual(rate(a,b)[1],'COUNTER_OR_TIME_INVALID')

    def test_capacity_preserves_session_and_disk_reserves(self):
        s=self.sample()
        self.assertEqual(capacity(s,None)['state'],'NOT_EVALUABLE_NO_VALID_RATE')
        self.assertEqual(capacity(s,100)['state'],'ESTIMATE_FITS_OBSERVED_RATE')
        self.assertEqual(capacity(s,100000)['state'],'ESTIMATE_EXCEEDS_AVAILABLE_BUDGET')
        s['disk_free_bytes']=GIB-1
        self.assertEqual(capacity(s,0)['state'],'ESTIMATE_EXCEEDS_AVAILABLE_BUDGET')
        s['disk_free_bytes']=GIB+RESERVE-1
        self.assertEqual(capacity(s,0)['state'],'ESTIMATE_EXCEEDS_AVAILABLE_BUDGET')
        s['disk_free_bytes']=GIB+RESERVE;s['storage_status']['session_bytes']=GIB-RESERVE
        self.assertEqual(capacity(s,0)['state'],'ESTIMATE_FITS_OBSERVED_RATE')
        self.assertFalse(capacity(s,0)['measured_four_hour_test'])

    def test_failure_still_receipted_and_next_node_audited(self):
        class Fake:
            def __init__(self):self.calls=[]
            def probe(self,node):
                self.calls.append(node['node_id']);return {'state':'CONNECTION_NOT_ESTABLISHED','attempts':[]}
        f=Fake();previous={'B':self.sample()}
        with tempfile.TemporaryDirectory() as d:
            rows=cycle([dict(node_id='observer-b'),dict(node_id='observer-c')],f,Path(d),previous,0)
            self.assertEqual(f.calls,['observer-b','observer-c'])
            self.assertEqual(len(list(Path(d).glob('*-private.json'))),2)
            self.assertEqual(len(rows),2);self.assertNotIn('B',previous)
            self.assertEqual(rows[0]['rate_reason'],'SSH_GAP')

    def test_config_change_does_not_produce_capacity_forecast(self):
        a=self.sample();b=self.sample(remote_monotonic_s=20,config_sha256={'node.json':'changed'})
        b['storage_status'].update(session_bytes=1000,updated_monotonic_s=20)
        class Fake:
            def probe(self,node):return {'state':'PROBE_RECEIVED','sample':b}
        with tempfile.TemporaryDirectory() as d:
            rows=cycle([dict(node_id='observer-b')],Fake(),Path(d),{'B':a},1)
            self.assertEqual(rows[0]['rate_reason'],'CONFIGURATION_CHANGED')
            self.assertIsNone(rows[0]['bytes_per_s'])

    def test_private_path_rejects_escape_and_symlink(self):
        with tempfile.TemporaryDirectory() as d,patch('audit_receivers.ROOT',Path(d).resolve()):
            p=Path(d).resolve()/'captures';p.mkdir()
            self.assertEqual(private_path(p/'new'),p/'new')
            with self.assertRaises(ValueError):private_path(Path(d)/'outside')
            (p/'link').symlink_to(p,target_is_directory=True)
            with self.assertRaises(ValueError):private_path(p/'link'/'new')

    def test_settings_reject_identity_duplicates_and_embedded_passwords(self):
        with tempfile.TemporaryDirectory() as d,patch('audit_receivers.ROOT',Path(d).resolve()):
            p=Path(d).resolve()/'captures';p.mkdir();known=p/'known';known.write_text('fixture')
            config=p/'config.json'
            b=dict(node_id='observer-b',known_hosts=str(known),targets=[dict(host='example.invalid',host_key_alias='example.invalid')])
            def save(nodes):config.write_text(json.dumps({'nodes':nodes}));config.chmod(0o600)
            save([b]);self.assertEqual(len(settings(config)),1)
            for nodes in [[b,b],[dict(b,node_id='observer-a')],[dict(b,password='synthetic-not-a-secret')]]:
                save(nodes)
                with self.assertRaises(ValueError):settings(config)

    def test_failed_ssh_is_receipted_without_invoking_installer(self):
        node=dict(known_hosts='fixture',targets=[dict(host='example.invalid',host_key_alias='example.invalid')])
        with patch('audit_receivers.subprocess.run',side_effect=[MagicMock(returncode=0),MagicMock(returncode=255,stderr=b'synthetic failure')]) as run:
            result=Transport({}).probe(node)
        self.assertEqual(result['state'],'CONNECTION_NOT_ESTABLISHED')
        self.assertEqual(result['attempts'][0]['state'],'SSH_OR_PROBE_FAILED')
        self.assertEqual(run.call_args_list[-1].args[0][0],'ssh')
        self.assertNotIn('install_pi.py',run.call_args_list[-1].args[0])

    def test_saved_host_key_and_strict_checking_are_not_bypassed(self):
        node=dict(known_hosts='fixture',targets=[dict(host='example.invalid',host_key_alias='saved.invalid')])
        response=MagicMock(returncode=0,stdout=json.dumps(self.sample()).encode(),stderr=b'')
        with patch('socket.create_connection',side_effect=OSError),patch('audit_receivers.subprocess.run',side_effect=[MagicMock(returncode=0),response]) as run:
            result=Transport({}).probe(node)
        self.assertEqual(result['state'],'PROBE_RECEIVED')
        argv=run.call_args_list[-1].args[0]
        self.assertIn('StrictHostKeyChecking=yes',argv);self.assertIn('HostKeyAlias=saved.invalid',argv)
        self.assertIn('BatchMode=yes',argv)


if __name__=='__main__':unittest.main()
