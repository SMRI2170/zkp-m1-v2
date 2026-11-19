import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import check_publication as checker


class PublicationBoundaryTests(unittest.TestCase):
    def check_fixture(self,name,content):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);subprocess.run(['git','init','-q',str(root)],check=True)
            p=root/'week29'/name;p.parent.mkdir(parents=True);p.write_text(content)
            subprocess.run(['git','-C',str(root),'add','week29'],check=True)
            with patch.object(checker,'ROOT',root),contextlib.redirect_stdout(io.StringIO()):checker.main()

    def test_rejects_accidentally_staged_capture_even_with_synthetic_input(self):
        with self.assertRaisesRegex(ValueError,'Private field artifact'):
            self.check_fixture('captures/synthetic.jsonl','{}\n')

    def test_rejects_nested_geographic_location_fields(self):
        with self.assertRaisesRegex(ValueError,'Private row field'):
            self.check_fixture('results/fixture.json',json.dumps({'items':[{'latitude':1.0}]}))

    def test_rejects_private_columns_even_when_no_data_rows(self):
        with self.assertRaisesRegex(ValueError,'Private row field'):
            self.check_fixture('results/fixture.csv','node,bssid\n')

    def test_accepts_anonymous_aggregate_counts(self):
        self.check_fixture('results/fixture.json',json.dumps({'nodes':{'A':{'rows':3,'receiver_position_present_rows':2}}}))


if __name__=='__main__':unittest.main()
