from pathlib import Path
import unittest
from start_marker import command
from safe_beacon_tx import test_identity,validate_ie


class MarkerTests(unittest.TestCase):
    def test_basic_id_only_has_no_location_and_no_encoder_dependency(self):
        body=bytes.fromhex('fa0bbc0d')+bytes([1,0xf2,25,1,2])+bytes(24)
        ie=validate_ie((bytes([221,len(body)])+body).hex(),1)
        marker=test_identity(ie,'PI-RID-LAB','02:00:00:00:00:50')
        self.assertEqual(marker[9],1)
        self.assertEqual(len(marker),35)
        c=command(Path('/home/pi/zkp-beacon-observer'),dict(uas_id='PI-RID-LAB',tx_mac='02:00:00:00:00:50'),60)
        self.assertIn('--id-only',c);self.assertNotIn('--lat',c);self.assertNotIn('--encoder',c)
        self.assertIn('--property=RuntimeMaxSec=85',c)
        with self.assertRaises(ValueError):command(Path('/unused'),{},121)
