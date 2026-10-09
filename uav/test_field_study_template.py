import csv
import unittest
from pathlib import Path

from prepare_rssi_dataset import WINDOW_FIELDS


TEMPLATE_DIR = Path(__file__).resolve().parent / "field-study-template"


class FieldStudyTemplateTests(unittest.TestCase):
    def test_calibration_and_evaluation_truth_templates_match_normalizer_schema(self):
        for filename in (
            "calibration-truth-windows.csv.example",
            "evaluation-truth-windows.csv.example",
        ):
            with self.subTest(filename=filename):
                with (TEMPLATE_DIR / filename).open(encoding="utf-8", newline="") as source:
                    rows = list(csv.reader(source))
                self.assertEqual(rows, [list(WINDOW_FIELDS)])


if __name__ == "__main__":
    unittest.main()
