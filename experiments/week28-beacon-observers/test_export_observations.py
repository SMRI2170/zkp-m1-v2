import csv
import io
import json
from pathlib import Path
import tempfile
import unittest
from export_observations import export


class ExportTests(unittest.TestCase):
    def test_invalid_vendor_raw_and_missing_position_survive_csv_and_json(self):
        row=dict(schema_version='wifi_observation_v1',rid_parse_status='invalid',
                 rid_parse_reason='unsupported version',raw_vendor_ie_hex='fa0bbc0d00ff',
                 receiver_position=None,rssi_dbm=-60,node_id='=UNTRUSTED')
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'input.jsonl';p.write_text(json.dumps(row)+'\n')
            out=io.StringIO();self.assertEqual(export([p],out,'csv'),1)
            r=list(csv.DictReader(io.StringIO(out.getvalue())))[0]
            self.assertEqual(r['rssi_dbm'],'-60');self.assertEqual(r['receiver_position'],'')
            self.assertEqual(r['node_id'],"'=UNTRUSTED");self.assertEqual(json.loads(r['raw_json']),row)
            out=io.StringIO();export([p],out,'json');self.assertEqual(json.loads(out.getvalue()),[row])

    def test_scan_metadata_without_vendor_is_explicitly_opt_in(self):
        import sys
        sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'uav'))
        from wifi_scan_capture import parse_scan,observations
        text='BSS 02:00:00:00:00:01(on wlan0)\n\tsignal: -60 dBm\n\tfreq: 2452\n'
        bss=parse_scan(text)[0];self.assertEqual(list(observations(bss,'fixture',0)),[])
        row=list(observations(bss,'fixture',0,include_unknown=True))[0]
        self.assertEqual(row['rid_parse_reason'],'VENDOR_IE_UNAVAILABLE')
        self.assertEqual(row['vendor_format'],'unclassified_wifi_candidate')


if __name__=='__main__':unittest.main()
