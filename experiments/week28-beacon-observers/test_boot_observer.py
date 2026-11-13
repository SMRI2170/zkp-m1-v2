from pathlib import Path
import tempfile
import json
import unittest
import argparse
from boot_observer import capacity,unit_text,worker_command,scan_interval,interface_ready
from run_observer import read_config


class BootReceiverTests(unittest.TestCase):
    def test_capacity_reserves_next_segment_without_deleting(self):
        good=[Path('/unused'),300*1024,1024**3,0,0]
        self.assertIsNone(capacity(*good))
        for index,value,reason in [(1,100*1024,'MEMORY_HEADROOM_LOW'),(2,100*1024**2,'DISK_HEADROOM_LOW'),
                                   (3,200*1024**2,'CAPTURE_BUDGET_REACHED'),(4,10000,'CAPTURE_FILE_BUDGET_REACHED')]:
            args=good.copy();args[index]=value;self.assertEqual(capacity(*args),reason)

    def test_receiver_only_service_is_privilege_scoped(self):
        text=unit_text(Path('/home/pi/zkp-beacon-observer/releases/test'),Path('/home/pi/zkp-beacon-observer'),'pi')
        for directive in ['User=pi','UMask=0077','NoNewPrivileges=true','MemoryMax=160M',
                          'RestartPreventExitStatus=78','KillMode=mixed','TimeoutStopSec=95',
                          'WantedBy=multi-user.target','CapabilityBoundingSet=CAP_NET_ADMIN']:
            self.assertIn(directive,text)
        self.assertNotIn('transmit',text.split('ExecStart=')[1])
        self.assertNotIn('sudo',text)
        self.assertNotIn('monitor',text)
        self.assertNotIn('ReadWritePaths=/home/pi\n',text)

    def test_paths_cannot_inject_systemd_directives(self):
        for path in ['/home/pi/zkp-beacon-observer/releases/bad name','/tmp/release','/home/pi/zkp-beacon-observer/%n']:
            with self.assertRaises(ValueError):unit_text(Path(path),Path('/home/pi/zkp-beacon-observer'),'pi')

    def test_half_second_requests_keep_polling_and_config(self):
        cfg=Path('/home/pi/zkp-beacon-observer/config/node.json')
        command=worker_command(cfg,60,0.5)
        self.assertEqual(command[command.index('--scan-interval')+1],'0.5')
        self.assertEqual(command[command.index('--interval')+1],'0.25')
        self.assertEqual(command[command.index('--config')+1],str(cfg))
        self.assertIn('--active-scan',command)
        self.assertNotIn('--frequency',command)

    def test_unbounded_or_invalid_scan_intervals_are_rejected(self):
        for value in ['nan','inf','-1','0','0.1','61']:
            with self.assertRaises(argparse.ArgumentTypeError):scan_interval(value)
        self.assertEqual(scan_interval('0.5'),0.5)

    def test_radio_enabled_does_not_require_management_wifi_association(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.assertFalse(interface_ready(root))
            (root/'flags').write_text('0x1003');self.assertTrue(interface_ready(root))
            (root/'flags').write_text('0x1002');self.assertFalse(interface_ready(root))
            (root/'flags').write_text('bad value');self.assertFalse(interface_ready(root))

    def test_six_node_names_supported_without_coordinates(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'config.json'
            for letter in 'abcdef':
                p.write_text(json.dumps(dict(node_id='observer-'+letter,interface='wlan0')))
                self.assertEqual(read_config(p)['node_id'],'observer-'+letter)
            p.write_text(json.dumps(dict(node_id='observer-unknown',interface='wlan0')))
            with self.assertRaises(ValueError):read_config(p)
