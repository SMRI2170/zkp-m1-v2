import math
from pathlib import Path
import unittest
from start_fast import command


class FastCommandTests(unittest.TestCase):
    def test_privilege_is_scoped_to_timed_service_and_observer_user(self):
        c=command(Path('/home/pi/zkp-beacon-observer'),60,.25,2452,'pi')
        self.assertEqual(c[:2],['sudo','systemd-run'])
        self.assertIn('--uid=pi',c)
        self.assertIn('--property=RuntimeMaxSec=85',c)
        self.assertIn('--property=MemoryMax=128M',c)
        self.assertIn('--property=CapabilityBoundingSet=CAP_NET_ADMIN',c)
        self.assertIn('--wait',c)
        self.assertIn('--collect',c)
        self.assertEqual(c[-2:],['--frequency','2452'])
        self.assertNotIn('monitor',str(c))

    def test_unknown_frequency_does_not_force_a_channel(self):
        c=command(Path('/home/pi/zkp-beacon-observer'),10,1,None,'pi')
        self.assertNotIn('--frequency',c)
        self.assertNotIn('2452',c)

    def test_invalid_limits_rejected_before_sudo(self):
        for duration,interval,frequency in [(0,1,None),(3601,1,None),(10,.1,None),
                                            (10,float('nan'),None),(10,float('inf'),None),
                                            (10,1,1234)]:
            with self.assertRaises(ValueError):
                command(Path('/tmp/not-a-node'),duration,interval,frequency,'pi')
