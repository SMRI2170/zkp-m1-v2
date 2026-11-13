import unittest
from pathlib import Path
from unittest.mock import patch
from run_rf_matrix import plan,Runner


class MatrixTests(unittest.TestCase):
    def test_balanced_bounded_matrix_and_both_transmitters(self):
        rows=plan()
        self.assertEqual(len(rows),26)
        matrix=[r for r in rows if r['kind']=='matrix']
        for tx in ['a','b']:
            for scope in ['target','all']:
                for spacing in [.25,1]:
                    self.assertEqual(sum(r['transmitter']==tx and r['scope']==scope and r['spacing_s']==spacing for r in matrix),3)
        self.assertTrue(all(r['duration_s']+15<=120 for r in rows))
        self.assertEqual([r['transmitter'] for r in rows[-2:]],['a','b'])

    def test_repetition_order_is_explicitly_reversed(self):
        rows=plan()
        self.assertEqual((rows[0]['scope'],rows[0]['spacing_s'],rows[0]['transmitter']),('target',.25,'a'))
        self.assertEqual((rows[8]['scope'],rows[8]['spacing_s'],rows[8]['transmitter']),('all',1,'b'))

    def test_unbounded_or_too_long_plan_rejected(self):
        for args in [(4,15,90),(3,31,90),(3,15,121),(0,15,90)]:
            with self.assertRaises(ValueError):plan(*args)

    def test_missing_control_socket_cannot_start_new_ssh_authentication(self):
        nodes={n:dict(host='pi@example.local',socket='/nonexistent/control-socket') for n in 'abc'}
        with self.assertRaises(ValueError):Runner(dict(nodes=nodes),Path('/unused'),'not-a-real-password')

    def test_scope_and_capability_of_receiver_unit(self):
        r=object.__new__(Runner);r.created=[];r.ssh=lambda *a,**k: setattr(r,'call',(a,k))
        r.launch('c','zkp-scan-synthetic',['/home/pi/zkp-beacon-observer/run'],15,receiver=True)
        args,kwargs=r.call
        self.assertEqual(r.created,[('c','zkp-scan-synthetic')])
        self.assertIn('--property=MemoryMax=128M',args[1])
        self.assertIn('--property=RuntimeMaxSec=45',args[1])
        self.assertIn('--uid=pi',args[1])
        self.assertIn('--property=CapabilityBoundingSet=CAP_NET_ADMIN',args[1])
        self.assertTrue(kwargs['root'])

    def test_already_unloaded_receiver_is_confirmed_stopped(self):
        r=object.__new__(Runner);calls=[]
        def ssh(*a,**kw):
            calls.append(a)
            return 'LoadState=not-found\nActiveState=inactive\n'
        r.ssh=ssh;r.stop('b','zkp-scan-test')
        self.assertEqual(len(calls),1)
        self.assertNotIn('stop',calls[0][1])

    def test_unknown_cleanup_state_is_not_silently_accepted(self):
        r=object.__new__(Runner);r.ssh=lambda *a,**kw:''
        with self.assertRaises(RuntimeError):r.stop('b','zkp-scan-test')

    def test_all_channel_sustain_only_remains_two_bounded_runs(self):
        rows=plan(mode='sustain-only',sustain_scope='all')
        self.assertEqual(len(rows),2)
        self.assertTrue(all(r['scope']=='all' and r['duration_s']==90 and r['kind']=='sustain' for r in rows))
