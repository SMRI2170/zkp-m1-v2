import csv
import contextlib
import hashlib
import io
import json
import math
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evaluate_rssi import main as evaluate_main
from prepare_rssi_dataset import (
    TruthWindow,
    load_captures,
    main,
    prepare_rows,
    read_truth_windows,
    write_private_csv,
)


TAG = "0123456789abcdef01234567"
IDENTITY = {
    "run_id": "run-heldout-01",
    "observer_id": "observer-pi-01",
    "calibration_profile_id": 4,
    "uas_id_tag_scope": "shared_session_key_and_run_id",
}


def window(sample_id="sample-01", start=1000, end=2000):
    return TruthWindow(
        sample_id=sample_id,
        decision_window_id=sample_id,
        run_id=IDENTITY["run_id"],
        observer_id=IDENTITY["observer_id"],
        profile_id=4,
        uas_id_tag=TAG,
        start_ms=start,
        end_ms=end,
        time_uncertainty_ms=10.0,
        observer=(35.0, 139.0, 0.0),
        truth=(35.0, 139.0 + 100.0 / 91_288.0, 0.0),
    )


def observation(timestamp, rssi, message_type="basic_id", **extra):
    return {
        **IDENTITY,
        "schema": "signal.observer-capture.v1",
        "record_type": "observation",
        "captured_at_unix_ms": timestamp,
        "rssi_dbm": rssi,
        "uas_id_tag": TAG,
        "message_type": message_type,
        **extra,
    }


def write_capture(path, rows=None, *, declared_count=None, include_end=True, identity=IDENTITY):
    rows = rows or [
        observation(1050, -55),
        observation(1100, -57, "location", latitude_deg=35.0001,
                    longitude_deg=139.0001, altitude_geo_m=12.0),
        observation(1200, -53, "location", latitude_deg=35.0003,
                    longitude_deg=139.0003, altitude_geo_m=14.0),
    ]
    records = [{
        **identity,
        "schema": "signal.observer-capture.v1",
        "record_type": "capture_start",
    }, *rows]
    if include_end:
        end_record = {
            **identity,
            "schema": "signal.observer-capture.v1",
            "record_type": "capture_end",
            "captured": len(rows) if declared_count is None else declared_count,
        }
        if rows and all("capture_event_seq" in row for row in rows):
            end_record["capture_event_count"] = len({row["capture_event_seq"] for row in rows})
        records.append(end_record)
    path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
    os.chmod(path, 0o600)


def write_truth(path, rows=None):
    rows = rows or [{
        "sample_id": "sample-01",
        "run_id": IDENTITY["run_id"],
        "observer_id": IDENTITY["observer_id"],
        "calibration_profile_id": "4",
        "uas_id_tag": TAG,
        "window_start_unix_ms": "1000",
        "window_end_unix_ms": "2000",
        "time_uncertainty_ms": "10",
        "observer_lat_deg": "35.0",
        "observer_lon_deg": "139.0",
        "observer_alt_m": "0",
        "truth_lat_deg": "35.0",
        "truth_lon_deg": str(139.0 + 100.0 / 91_288.0),
        "truth_alt_m": "0",
    }]
    rows = [
        {"decision_window_id": row.get("decision_window_id", row["sample_id"]), **row}
        for row in rows
    ]
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    os.chmod(path, 0o600)


def truth_row(sample_id, run_id, tag, start_ms, *, truth_east_m, truth_north_m=0.0):
    return {
        "sample_id": sample_id,
        "run_id": run_id,
        "observer_id": IDENTITY["observer_id"],
        "calibration_profile_id": "4",
        "uas_id_tag": tag,
        "window_start_unix_ms": str(start_ms),
        "window_end_unix_ms": str(start_ms + 1000),
        "time_uncertainty_ms": "10",
        "observer_lat_deg": "35.0",
        "observer_lon_deg": "139.0",
        "observer_alt_m": "0",
        "truth_lat_deg": str(35.0 + truth_north_m / 111_320.0),
        "truth_lon_deg": str(139.0 + truth_east_m / 91_288.0),
        "truth_alt_m": "0",
    }


def observation_for(identity, tag, timestamp, rssi, *, east_m, north_m=0.0):
    return {
        **identity,
        "schema": "signal.observer-capture.v1",
        "record_type": "observation",
        "captured_at_unix_ms": timestamp,
        "rssi_dbm": int(round(rssi)),
        "uas_id_tag": tag,
        "message_type": "location",
        "latitude_deg": 35.0 + north_m / 111_320.0,
        "longitude_deg": 139.0 + east_m / 91_288.0,
        "altitude_geo_m": 0.0,
    }


class PrepareRssiDatasetTests(unittest.TestCase):
    def test_builds_calibration_and_evaluation_rows_from_logs_and_external_truth(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            capture_path = Path(temp_dir) / "capture.jsonl"
            write_capture(capture_path)
            captures = load_captures([capture_path])

            calibration = prepare_rows([window()], captures, "calibration")[0]
            self.assertAlmostEqual(calibration["true_range_m"], 100.0, places=4)
            self.assertEqual(calibration["rssi_dbm_median"], -55.0)
            self.assertEqual(calibration["capture_observation_count"], 3)
            self.assertEqual(calibration["location_packet_count"], 2)

            evaluation = prepare_rows([window()], captures, "evaluation")[0]
            self.assertEqual(evaluation["decision_window_id"], "sample-01")
            self.assertAlmostEqual(evaluation["advertised_lat_deg"], 35.0002)
            self.assertAlmostEqual(evaluation["advertised_lon_deg"], 139.0002)
            self.assertAlmostEqual(evaluation["advertised_alt_m"], 13.0)
            self.assertEqual(evaluation["truth_lat_deg"], window().truth[0])
            self.assertEqual(evaluation["time_uncertainty_ms"], 10.0)

    def test_message_pack_rows_count_one_rssi_sample_per_radio_event(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            capture_path = Path(temp_dir) / "capture.jsonl"
            rows = [
                observation(1050, -80, capture_event_seq=1, advertiser_tag="adv-1"),
                observation(1050, -80, "location", latitude_deg=35.0001,
                            longitude_deg=139.0001, altitude_geo_m=12.0,
                            capture_event_seq=1, advertiser_tag="adv-1"),
                observation(1100, -60, capture_event_seq=2, advertiser_tag="adv-1"),
                observation(1100, -60, "location", latitude_deg=35.0003,
                            longitude_deg=139.0003, altitude_geo_m=14.0,
                            capture_event_seq=2, advertiser_tag="adv-1"),
            ]
            write_capture(capture_path, rows)
            captures = load_captures([capture_path])
            result = prepare_rows([window()], captures, "calibration")[0]
            self.assertEqual(result["rssi_dbm_median"], -70.0)
            self.assertEqual(result["capture_observation_count"], 2)
            self.assertEqual(result["location_packet_count"], 2)

    def test_rejects_inconsistent_records_for_one_capture_event(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            capture_path = Path(temp_dir) / "capture.jsonl"
            rows = [
                observation(1050, -55, capture_event_seq=1, advertiser_tag="adv-1"),
                observation(1050, -57, "location", latitude_deg=35.0,
                            longitude_deg=139.0, altitude_geo_m=12.0,
                            capture_event_seq=1, advertiser_tag="adv-1"),
            ]
            write_capture(capture_path, rows)
            with self.assertRaisesRegex(ValueError, "capture event has inconsistent"):
                load_captures([capture_path])

    def test_reads_truth_windows_and_rejects_overlapping_windows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "truth.csv"
            write_truth(path)
            self.assertEqual(read_truth_windows(path)[0][0].sample_id, "sample-01")

            second = {
                "sample_id": "sample-02",
                "run_id": IDENTITY["run_id"],
                "observer_id": IDENTITY["observer_id"],
                "calibration_profile_id": "4",
                "uas_id_tag": TAG,
                "window_start_unix_ms": "1500",
                "window_end_unix_ms": "2500",
                "time_uncertainty_ms": "10",
                "observer_lat_deg": "35.0",
                "observer_lon_deg": "139.0",
                "observer_alt_m": "0",
                "truth_lat_deg": "35.0",
                "truth_lon_deg": "139.001",
                "truth_alt_m": "0",
            }
            write_truth(path, [
                {key: value for key, value in {
                    "sample_id": "sample-01",
                    "run_id": IDENTITY["run_id"],
                    "observer_id": IDENTITY["observer_id"],
                    "calibration_profile_id": "4",
                    "uas_id_tag": TAG,
                    "window_start_unix_ms": "1000",
                    "window_end_unix_ms": "2000",
                    "time_uncertainty_ms": "10",
                    "observer_lat_deg": "35.0",
                    "observer_lon_deg": "139.0",
                    "observer_alt_m": "0",
                    "truth_lat_deg": "35.0",
                    "truth_lon_deg": "139.001",
                    "truth_alt_m": "0",
                }.items()}, second,
            ])
            with self.assertRaisesRegex(ValueError, "overlap"):
                read_truth_windows(path)

    def test_decision_window_group_requires_same_target_overlapping_time_and_unique_observer(self):
        first = truth_row("sample-01", IDENTITY["run_id"], TAG, 1000, truth_east_m=100.0)
        first["decision_window_id"] = "shared-window"
        second = {
            **truth_row("sample-02", IDENTITY["run_id"], TAG, 1200, truth_east_m=100.0),
            "observer_id": "observer-pi-02",
            "decision_window_id": "shared-window",
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "truth.csv"
            write_truth(path, [first, second])
            self.assertEqual(len(read_truth_windows(path)[0]), 2)

            wrong_target = {**second, "uas_id_tag": "fedcba9876543210fedcba98"}
            write_truth(path, [first, wrong_target])
            with self.assertRaisesRegex(ValueError, "different uas_id_tag"):
                read_truth_windows(path)

            disjoint_time = {
                **second,
                "window_start_unix_ms": "3000",
                "window_end_unix_ms": "4000",
            }
            write_truth(path, [first, disjoint_time])
            with self.assertRaisesRegex(ValueError, "no common time overlap"):
                read_truth_windows(path)

            duplicate_observer = {**second, "observer_id": first["observer_id"]}
            write_truth(path, [first, duplicate_observer])
            with self.assertRaisesRegex(ValueError, "repeats observer"):
                read_truth_windows(path)

    def test_rejects_time_uncertainty_that_is_not_small_compared_with_window(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "truth.csv"
            write_truth(path)
            with path.open("r", newline="", encoding="utf-8") as source:
                rows = list(csv.DictReader(source))
            rows[0]["time_uncertainty_ms"] = rows[0]["window_end_unix_ms"]
            write_truth(path, rows)
            with self.assertRaisesRegex(ValueError, "uncertainty must be smaller"):
                read_truth_windows(path)

    def test_requires_complete_capture_and_matching_location_and_tag(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            capture_path = Path(temp_dir) / "capture.jsonl"
            write_capture(capture_path, include_end=False)
            with self.assertRaisesRegex(ValueError, "capture_start and capture_end"):
                load_captures([capture_path])

            rows = [observation(1050, -55, "basic_id")]
            write_capture(capture_path, rows)
            captures = load_captures([capture_path])
            with self.assertRaisesRegex(ValueError, "no matching Remote ID Location"):
                prepare_rows([window()], captures, "evaluation")

            rows = [observation(1050, -55, uas_id_tag="fedcba9876543210fedcba98")]
            write_capture(capture_path, rows)
            captures = load_captures([capture_path])
            with self.assertRaisesRegex(ValueError, "no matching tagged RSSI"):
                prepare_rows([window()], captures, "evaluation")

    def test_rejects_closed_capture_with_known_ble_acquisition_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            capture_path = Path(temp_dir) / "capture.jsonl"
            write_capture(capture_path)
            records = [
                json.loads(line)
                for line in capture_path.read_text(encoding="utf-8").splitlines()
            ]
            records.insert(-1, {
                **IDENTITY,
                "schema": "signal.observer-capture.v1",
                "record_type": "capture_error",
                "failure_source": "ble_scan_start",
                "error_type": "StateError",
                "message": "BLE acquisition failed; this capture must not be used.",
            })
            capture_path.write_text(
                "".join(json.dumps(record) + "\n" for record in records),
                encoding="utf-8",
            )
            os.chmod(capture_path, 0o600)

            with self.assertRaisesRegex(ValueError, "capture contains capture_error"):
                load_captures([capture_path])

    def test_rejects_mismatched_capture_identity_and_inconsistent_end_count(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            capture_path = Path(temp_dir) / "capture.jsonl"
            rows = [observation(1050, -55), observation(1100, -57, "location",
                    latitude_deg=35.0, longitude_deg=139.0, altitude_geo_m=0)]
            rows[1]["observer_id"] = "observer-other"
            write_capture(capture_path, rows)
            with self.assertRaisesRegex(ValueError, "identity changes"):
                load_captures([capture_path])

            write_capture(capture_path, declared_count=99)
            with self.assertRaisesRegex(ValueError, "count does not match"):
                load_captures([capture_path])

            write_capture(capture_path)
            captures = load_captures([capture_path])
            wrong_profile_window = TruthWindow(**{**window().__dict__, "profile_id": 5})
            with self.assertRaisesRegex(ValueError, "profile does not match"):
                prepare_rows([wrong_profile_window], captures, "evaluation")

    def test_output_is_private_and_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "normalized.csv"
            write_private_csv(output, [{"sample_id": "sample-01", "rssi_dbm_median": -55}],
                              ("sample_id", "rssi_dbm_median"))
            self.assertEqual(os.stat(output).st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                write_private_csv(output, [], ("sample_id", "rssi_dbm_median"))
            self.assertIn("sample-01", output.read_text(encoding="utf-8"))

    def test_cli_creates_a_private_csv_accepted_by_the_existing_evaluator_schema(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            capture_path = Path(temp_dir) / "capture.jsonl"
            truth_path = Path(temp_dir) / "truth.csv"
            output_path = Path(temp_dir) / "evaluation.csv"
            write_capture(capture_path)
            write_truth(truth_path)

            exit_code = main([
                "--captures", str(capture_path),
                "--truth-windows", str(truth_path),
                "--mode", "evaluation",
                "--output", str(output_path),
            ])
            self.assertEqual(exit_code, 0)
            self.assertEqual(os.stat(output_path).st_mode & 0o777, 0o600)
            with output_path.open("r", newline="", encoding="utf-8") as source:
                reader = csv.DictReader(source)
                row = next(reader)
            self.assertEqual(row["sample_id"], "sample-01")
            self.assertEqual(row["rssi_dbm_median"], "-55.0")
            self.assertEqual(row["location_packet_count"], "2")
            self.assertEqual(row["time_uncertainty_ms"], "10.0")
            capture_file_digest = hashlib.sha256(capture_path.read_bytes()).hexdigest()
            expected_set_digest = hashlib.sha256(
                b"signal.observer-capture-set.v1\x00" + json.dumps(
                    [capture_file_digest], separators=(",", ":")
                ).encode("ascii")
            ).hexdigest()
            self.assertEqual(row["capture_set_sha256"], expected_set_digest)
            self.assertEqual(
                row["truth_windows_sha256"],
                hashlib.sha256(truth_path.read_bytes()).hexdigest(),
            )
            self.assertNotIn(TAG, output_path.read_text(encoding="utf-8"))

    def test_capture_to_holdout_evaluation_pipeline_reports_expected_errors(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            calibration_captures = []
            calibration_truth = []
            for run_number in (1, 2):
                run_id = "cal-run-{:02d}".format(run_number)
                tag = "{:024x}".format(run_number)
                identity = {**IDENTITY, "run_id": run_id}
                capture_rows = []
                for index, distance_m in enumerate((1.0, 2.0, 4.0, 8.0)):
                    timestamp = 1000 + index * 2000
                    rssi = -40.0 - 20.0 * math.log10(distance_m)
                    capture_rows.append(observation_for(
                        identity, tag, timestamp + 100, rssi, east_m=distance_m
                    ))
                    calibration_truth.append(truth_row(
                        "cal-{}-{}".format(run_number, index), run_id, tag,
                        timestamp, truth_east_m=distance_m,
                    ))
                capture_path = root / "cal-{}.jsonl".format(run_number)
                write_capture(capture_path, capture_rows, identity=identity)
                calibration_captures.append(str(capture_path))

            calibration_windows_path = root / "cal-truth.csv"
            write_truth(calibration_windows_path, calibration_truth)
            calibration_path = root / "calibration.csv"
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main([
                    "--captures", *calibration_captures,
                    "--truth-windows", str(calibration_windows_path),
                    "--mode", "calibration",
                    "--output", str(calibration_path),
                ]), 0)

            evaluation_captures = []
            evaluation_truth = []
            cases = (
                # Normal: truthful advertised range and position.
                (100.0, 0.0, 100.0, 0.0, -80.0),
                # True positive: claimed range exceeds calibrated RSSI range.
                (200.0, 0.0, 100.0, 0.0, -80.0),
                # False positive: truthful position, but RSSI is an outlier.
                (100.0, 0.0, 100.0, 0.0, -70.0),
                # False negative: lateral displacement keeps the same radius.
                (100.0, 0.0, 0.0, 100.0, -80.0),
            )
            for index, (advertised_east, advertised_north, truth_east,
                        truth_north, rssi) in enumerate(cases, start=1):
                run_id = "eval-run-{:02d}".format(index)
                tag = "{:024x}".format(100 + index)
                identity = {**IDENTITY, "run_id": run_id}
                capture_path = root / "eval-{}.jsonl".format(index)
                write_capture(capture_path, [observation_for(
                    identity, tag, 1100, rssi,
                    east_m=advertised_east, north_m=advertised_north,
                )], identity=identity)
                evaluation_captures.append(str(capture_path))
                evaluation_truth.append(truth_row(
                    "eval-{}".format(index), run_id, tag, 1000,
                    truth_east_m=truth_east, truth_north_m=truth_north,
                ))

            evaluation_windows_path = root / "eval-truth.csv"
            write_truth(evaluation_windows_path, evaluation_truth)
            evaluation_path = root / "evaluation.csv"
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main([
                    "--captures", *evaluation_captures,
                    "--truth-windows", str(evaluation_windows_path),
                    "--mode", "evaluation",
                    "--output", str(evaluation_path),
                ]), 0)

            preregistration_path = root / "study-preregistration.json"
            preregistration_path.write_text(json.dumps({
                "schema": "signal.rssi-study-preregistration.v1",
                "study_id": "capture-pipeline-test",
                "calibration_run_ids": ["cal-run-01", "cal-run-02"],
                "evaluation_run_ids": ["eval-run-01", "eval-run-02", "eval-run-03", "eval-run-04"],
                "position_error_threshold_m": 30,
                "max_time_uncertainty_ms": 50,
                "tolerance_ratio": 0.9,
                "minimum_quorum": 2,
                "minimum_independent_runs_per_class": 1,
                "maximum_95_false_rate_ci_width": 1,
            }) + "\n", encoding="utf-8")
            os.chmod(preregistration_path, 0o600)
            report_output = io.StringIO()
            with contextlib.redirect_stdout(report_output):
                self.assertEqual(evaluate_main([
                    "--preregistration", str(preregistration_path),
                    "--calibration", str(calibration_path),
                    "--evaluation", str(evaluation_path),
                ]), 0)
            report = json.loads(report_output.getvalue())
            self.assertEqual(report["confusion_matrix"], {
                "true_positive": 1,
                "false_positive": 1,
                "true_negative": 1,
                "false_negative": 1,
            })
            self.assertEqual(report["capture_quality"], {
                "sample_count": 4,
                "time_uncertainty_ms": {"min": 10.0, "median": 10.0, "max": 10.0},
                "window_duration_ms": {"min": 1000.0, "median": 1000.0, "max": 1000.0},
                "capture_observation_count": {"min": 1, "median": 1.0, "max": 1},
                "location_packet_count": {"min": 1, "median": 1.0, "max": 1},
            })
            self.assertEqual(report["multi_observer"]["status_counts"]["insufficient_evidence"], 4)


if __name__ == "__main__":
    unittest.main()
