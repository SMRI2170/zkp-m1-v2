import json
import unittest
from source_labels import classify,validate_rules,text_line
from wifi_scan_capture import observations,parse_scan
from test_wifi_scan_capture import fixture


class SourceLabelsTests(unittest.TestCase):
    def test_same_claimed_id_different_addresses_keep_explicit_labels(self):
        rules=validate_rules([dict(role='drone',label='Drone fixture',uas_id='SAME',bssid='02:00:00:00:00:01'),
                              dict(role='onboard_pi',label='Pi fixture',uas_id='SAME',bssid='02:00:00:00:00:02')])
        self.assertEqual(classify('02:00:00:00:00:01',['SAME'],rules)['role'],'drone')
        self.assertEqual(classify('02:00:00:00:00:02',['SAME'],rules)['role'],'onboard_pi')
        self.assertFalse(classify('02:00:00:00:00:02',['SAME'],rules)['identity_verified'])

    def test_conflicting_rules_are_unknown_not_first_match(self):
        rules=validate_rules([dict(role='drone',label='Drone fixture',uas_id='SAME'),dict(role='onboard_pi',label='Pi fixture',uas_id='SAME')])
        self.assertEqual(classify('02:00:00:00:00:01',['SAME'],rules)['basis'],'conflicting_local_rules')

    def test_marker_is_explicitly_unverified_and_does_not_guess_other_drones(self):
        self.assertEqual(classify('fixture',['PI-RID-LAB'])['basis'],'unverified_test_marker')
        self.assertEqual(classify('fixture',['OTHER'])['role'],'unknown')

    def test_malformed_payload_keeps_raw_text_and_rssi_without_claiming_an_id(self):
        bss,=parse_scan(fixture(bytes.fromhex('fa0bbc0d07')))
        row,=observations(bss,'fixture',1700000000)
        self.assertEqual(row['raw_vendor_ie_hex'],'fa0bbc0d07')
        self.assertEqual(row['claimed_uas_ids'],[])
        self.assertEqual(row['rid_parse_status'],'invalid')
        self.assertIn('raw_vendor_ie_hex="fa0bbc0d07"',text_line(row))
        self.assertIn('rssi_dbm=-61.0',text_line(row))

    def test_specific_rule_overrides_mac_only_fallback(self):
        rules=validate_rules([dict(role='unknown',label='MAC only',bssid='02:00:00:00:00:01'),
                              dict(role='onboard_pi',label='Pi fixture',bssid='02:00:00:00:00:01',uas_id='PI-RID-LAB')])
        self.assertEqual(classify('02:00:00:00:00:01',['PI-RID-LAB'],rules)['basis'],'configured_id_and_bssid')
        self.assertEqual(classify('02:00:00:00:00:01',[],rules)['basis'],'configured_bssid')

    def test_labels_are_single_line_in_text_and_bad_config_rejected(self):
        s=text_line(dict(bssid='fixture',source_annotation={'label':'a\nb'}))
        self.assertNotIn('\n',s)
        with self.assertRaises(ValueError):validate_rules([dict(role='drone',label='No key')])
