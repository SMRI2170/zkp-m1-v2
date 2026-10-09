import contextlib
import csv
import hashlib
import io
import json
import math
import os
import tempfile
import unittest
from pathlib import Path

from evaluate_rssi import (
    build_parser,
    evaluate,
    fit_path_loss_model,
    fit_path_loss_models,
    local_distance_m,
    main,
    validate_holdout_separation,
)


def calibration_rows(observer_id="observer-01", profile_id="1"):
    # RSSI = -40 dBm at 1 m, with a log-distance exponent of 2.
    return [
        {"sample_id": "{}-cal-1".format(observer_id), "run_id": "cal-run-01", "observer_id": observer_id, "calibration_profile_id": profile_id,
         "true_range_m": "1", "rssi_dbm_median": "-40"},
        {"sample_id": "{}-cal-2".format(observer_id), "run_id": "cal-run-01", "observer_id": observer_id, "calibration_profile_id": profile_id,
         "true_range_m": "2", "rssi_dbm_median": str(-40 - 20 * math.log10(2))},
        {"sample_id": "{}-cal-3".format(observer_id), "run_id": "cal-run-02", "observer_id": observer_id, "calibration_profile_id": profile_id,
         "true_range_m": "4", "rssi_dbm_median": str(-40 - 20 * math.log10(4))},
        {"sample_id": "{}-cal-4".format(observer_id), "run_id": "cal-run-02", "observer_id": observer_id, "calibration_profile_id": profile_id,
         "true_range_m": "8", "rssi_dbm_median": str(-40 - 20 * math.log10(8))},
    ]


def evaluation_row(
    sample_id,
    advertised_east_m,
    truth_east_m,
    rssi_dbm,
    advertised_north_m=0,
    truth_north_m=0,
    observer_id="observer-01",
    profile_id="1",
    run_id="run-01",
    decision_window_id=None,
):
    observer = (35.0, 139.0, 0.0)
    return {
        "sample_id": sample_id,
        "decision_window_id": decision_window_id or sample_id,
        "run_id": run_id,
        "observer_id": observer_id,
        "calibration_profile_id": profile_id,
        "observer_lat_deg": str(observer[0]),
        "observer_lon_deg": str(observer[1]),
        "observer_alt_m": "0",
        "advertised_lat_deg": str(observer[0] + advertised_north_m / 111_320.0),
        "advertised_lon_deg": str(observer[1] + advertised_east_m / 91_288.0),
        "advertised_alt_m": "0",
        "truth_lat_deg": str(observer[0] + truth_north_m / 111_320.0),
        "truth_lon_deg": str(observer[1] + truth_east_m / 91_288.0),
        "truth_alt_m": "0",
        "rssi_dbm_median": str(rssi_dbm),
        "time_uncertainty_ms": "10",
        "window_duration_ms": "1000",
        "capture_observation_count": "3",
        "location_packet_count": "2",
    }


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(target, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    os.chmod(path, 0o600)


def preregistration_document(
    calibration_run_ids=None,
    evaluation_run_ids=None,
    **overrides,
):
    document = {
        "schema": "signal.rssi-study-preregistration.v1",
        "study_id": "study-pilot-01",
        "calibration_run_ids": calibration_run_ids or ["cal-run-01", "cal-run-02"],
        "evaluation_run_ids": evaluation_run_ids or ["heldout-run-01"],
        "position_error_threshold_m": 30,
        "max_time_uncertainty_ms": 50,
        "tolerance_ratio": 0.9,
        "minimum_quorum": 2,
        "minimum_independent_runs_per_class": 1,
        "maximum_95_false_rate_ci_width": 1.0,
    }
    document.update(overrides)
    return document


def write_preregistration(path, document=None):
    path.write_text(json.dumps(document or preregistration_document()) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)


class PathLossModelTests(unittest.TestCase):
    def test_recovers_log_distance_parameters(self):
        model = fit_path_loss_model(calibration_rows())
        self.assertAlmostEqual(model.rssi_at_1m_dbm, -40.0, places=10)
        self.assertAlmostEqual(model.path_loss_exponent, 2.0, places=10)
        self.assertAlmostEqual(model.calibration_rmse_db, 0.0, places=10)
        self.assertEqual(model.calibration_run_count, 2)

    def test_requires_multiple_ranges_and_independent_windows(self):
        rows = calibration_rows()[:3]
        rows[1] = {**rows[1], "true_range_m": "1"}
        rows[2] = {**rows[2], "true_range_m": "1"}
        with self.assertRaisesRegex(ValueError, "2 distinct known distances"):
            fit_path_loss_model(rows)

    def test_rejects_duplicate_sample_ids(self):
        rows = calibration_rows()
        rows[1] = {**rows[1], "sample_id": rows[0]["sample_id"]}
        with self.assertRaisesRegex(ValueError, "duplicate sample_id"):
            fit_path_loss_model(rows)

    def test_requires_multiple_independent_calibration_runs(self):
        rows = [{**row, "run_id": "one-run"} for row in calibration_rows()]
        with self.assertRaisesRegex(ValueError, "at least 2 independent run_id"):
            fit_path_loss_model(rows)


class EvaluationTests(unittest.TestCase):
    def test_rejects_calibration_evaluation_run_or_sample_overlap(self):
        calibration = calibration_rows()
        evaluation = [evaluation_row("heldout-sample", 100, 100, -80, run_id="eval-run")]
        validate_holdout_separation(calibration, evaluation)

        with self.assertRaisesRegex(ValueError, "share 1 run_id"):
            validate_holdout_separation(
                calibration,
                [evaluation_row("heldout-sample", 100, 100, -80, run_id="cal-run-01")],
            )
        with self.assertRaisesRegex(ValueError, "share 1 sample_id"):
            validate_holdout_separation(
                calibration,
                [evaluation_row("observer-01-cal-1", 100, 100, -80, run_id="eval-run")],
            )

    def test_reports_false_positive_and_false_negative_against_independent_truth(self):
        models = fit_path_loss_models(calibration_rows() + calibration_rows("observer-02", "2"))
        rows = [
            evaluation_row("legitimate-match", 100, 100, -80, run_id="run-01"),
            evaluation_row("legitimate-rssi-outlier", 100, 100, -70, run_id="run-02"),
            evaluation_row("spoof-detected", 300, 100, -80, observer_id="observer-02", profile_id="2", run_id="run-01"),
            # A lateral displacement preserves radial distance: RSSI alone misses it.
            evaluation_row("spoof-same-radius", 100, 0, -80, truth_north_m=100,
                           observer_id="observer-02", profile_id="2", run_id="run-02"),
        ]
        report = evaluate(rows, models, position_error_threshold_m=30,
                          max_time_uncertainty_ms=50, include_samples=True)
        self.assertEqual(report["confusion_matrix"], {
            "true_positive": 1,
            "false_positive": 1,
            "true_negative": 1,
            "false_negative": 1,
        })
        self.assertEqual(report["ground_truth_label_coverage"], {
            "position_mismatch": {"samples": 2, "independent_runs": 2},
            "position_consistent": {"samples": 2, "independent_runs": 2},
        })
        self.assertAlmostEqual(report["metrics"]["false_positive_rate"], 0.5)
        self.assertAlmostEqual(report["metrics"]["false_negative_rate"], 0.5)
        self.assertEqual(len(report["samples"]), 4)
        self.assertEqual(report["per_observer"]["observer-02"]["sample_count"], 2)
        self.assertEqual(len(report["calibration_models"]), 2)
        self.assertEqual(report["independent_run_count"], 2)
        bootstrap = report["false_rate_confidence_intervals_95"]
        self.assertEqual(bootstrap["valid_replicates"], {
            "false_positive_rate": 1000,
            "false_negative_rate": 1000,
        })
        fpr_ci = report["false_rate_confidence_intervals_95"]["false_positive_rate"]
        fnr_ci = report["false_rate_confidence_intervals_95"]["false_negative_rate"]
        self.assertLessEqual(fpr_ci["low"], report["metrics"]["false_positive_rate"])
        self.assertGreaterEqual(fpr_ci["high"], report["metrics"]["false_positive_rate"])
        self.assertLessEqual(fnr_ci["low"], report["metrics"]["false_negative_rate"])
        self.assertGreaterEqual(fnr_ci["high"], report["metrics"]["false_negative_rate"])
        self.assertIn("does not prove sensor honesty", " ".join(report["limitations"]))

    def test_reports_multi_observer_quorum_false_positive_and_false_negative_rates(self):
        models = fit_path_loss_models(
            calibration_rows()
            + calibration_rows("observer-02", "2")
            + calibration_rows("observer-03", "3")
        )
        rows = []
        groups = [
            # True negative: consistent truth and three RSSI-consistent observers.
            ("clean", 100, 100, -80),
            # False positive: truth agrees, but RSSI estimates conflict with the claim.
            ("false-positive", 300, 300, -80),
            # True positive: the same mismatch is independently present in truth.
            ("true-positive", 300, 100, -80),
            # False negative: the position is wrong but retains the same radial range.
            ("false-negative", 100, 0, -80),
        ]
        for decision_id, claimed_east, truth_east, rssi in groups:
            run_id = "eval-{}".format(decision_id)
            for observer_id, profile_id in (
                ("observer-01", "1"),
                ("observer-02", "2"),
                ("observer-03", "3"),
            ):
                rows.append(evaluation_row(
                    "{}-{}".format(decision_id, observer_id),
                    claimed_east,
                    truth_east,
                    rssi,
                    observer_id=observer_id,
                    profile_id=profile_id,
                    run_id=run_id,
                    decision_window_id=decision_id,
                ))

        report = evaluate(
            rows,
            models,
            position_error_threshold_m=30,
            max_time_uncertainty_ms=50,
            include_samples=True,
            minimum_quorum=2,
            minimum_independent_runs_per_class=2,
            maximum_95_false_rate_ci_width=1.0,
        )
        aggregate = report["multi_observer"]
        self.assertEqual(aggregate["decision_window_count"], 4)
        self.assertEqual(aggregate["finalized_count"], 4)
        self.assertEqual(aggregate["expected_observer_count"], 3)
        self.assertEqual(aggregate["status_counts"], {
            "no_inconsistency_observed": 2,
            "position_inconsistency_suspected": 2,
            "insufficient_evidence": 0,
            "conflicting_counts": 0,
            "unsupported_observer_count": 0,
        })
        self.assertEqual(aggregate["confusion_matrix"], {
            "true_positive": 1,
            "false_positive": 1,
            "true_negative": 1,
            "false_negative": 1,
        })
        self.assertAlmostEqual(aggregate["metrics"]["false_positive_rate"], 0.5)
        self.assertAlmostEqual(aggregate["metrics"]["false_negative_rate"], 0.5)
        self.assertEqual(aggregate["ground_truth_label_coverage"], {
            "position_mismatch": {"decision_windows": 2, "independent_runs": 2},
            "position_consistent": {"decision_windows": 2, "independent_runs": 2},
        })
        self.assertEqual(aggregate["finalized_truth_class_coverage"], {
            "position_mismatch": {"decision_windows": 2, "independent_runs": 2},
            "position_consistent": {"decision_windows": 2, "independent_runs": 2},
        })
        self.assertEqual(aggregate["preregistered_run_count_adequacy"]["status"], "meets_minimum")
        self.assertTrue(all("aggregate_final_status" in sample for sample in report["samples"]))

    def test_multi_observer_summary_keeps_insufficient_and_conflicting_groups_out_of_error_rates(self):
        models = fit_path_loss_models(
            calibration_rows()
            + calibration_rows("observer-02", "2")
            + calibration_rows("observer-03", "3")
            + calibration_rows("observer-04", "4")
        )
        fewer_than_topology = [
            evaluation_row(
                "only-one", 100, 100, -80, decision_window_id="needs-quorum"
            ),
            evaluation_row(
                "only-two", 100, 100, -80, observer_id="observer-02", profile_id="2",
                decision_window_id="needs-quorum",
            ),
        ]
        insufficient = evaluate(
            fewer_than_topology, models, 30, 50, minimum_quorum=2
        )["multi_observer"]
        self.assertEqual(insufficient["status_counts"]["insufficient_evidence"], 1)
        self.assertEqual(insufficient["finalized_count"], 0)
        self.assertIsNone(insufficient["metrics"]["false_positive_rate"])

        unsupported = evaluate(
            [
                evaluation_row(
                    "wide-1", 100, 100, -80, decision_window_id="wide-window"
                ),
                evaluation_row(
                    "wide-2", 100, 100, -80, observer_id="observer-02", profile_id="2",
                    decision_window_id="wide-window",
                ),
                evaluation_row(
                    "wide-3", 100, 100, -80, observer_id="observer-03", profile_id="3",
                    decision_window_id="wide-window",
                ),
                evaluation_row(
                    "wide-4", 100, 100, -80, observer_id="observer-04", profile_id="4",
                    decision_window_id="wide-window",
                ),
            ],
            models,
            30,
            50,
            minimum_quorum=2,
        )["multi_observer"]
        self.assertEqual(unsupported["status_counts"]["unsupported_observer_count"], 1)
        self.assertEqual(unsupported["finalized_count"], 0)

        conflicting_rows = [
            evaluation_row("consistent-vote", 300, 300, -40 - 20 * math.log10(300),
                           observer_id="observer-01", profile_id="1",
                           run_id="conflict-run", decision_window_id="conflict-window"),
            evaluation_row("suspicious-vote", 300, 300, -80,
                           observer_id="observer-02", profile_id="2",
                           run_id="conflict-run", decision_window_id="conflict-window"),
            evaluation_row("consistent-vote-2", 300, 300, -40 - 20 * math.log10(300),
                           observer_id="observer-03", profile_id="3",
                           run_id="conflict-run", decision_window_id="conflict-window"),
        ]
        conflicting = evaluate(
            conflicting_rows, models, 30, 50, minimum_quorum=1,
            minimum_independent_runs_per_class=1,
            maximum_95_false_rate_ci_width=1.0,
        )["multi_observer"]
        self.assertEqual(conflicting["status_counts"]["conflicting_counts"], 1)
        self.assertEqual(conflicting["finalized_count"], 0)
        self.assertEqual(conflicting["ground_truth_label_coverage"]["position_consistent"]["independent_runs"], 1)
        self.assertEqual(conflicting["finalized_truth_class_coverage"]["position_consistent"]["independent_runs"], 0)
        self.assertEqual(conflicting["preregistered_run_count_adequacy"]["status"], "below_preregistered_minimum")
        self.assertEqual(
            conflicting["preregistered_interval_precision_adequacy"]["status"],
            "target_not_met_or_interval_unavailable",
        )

    def test_preregistered_run_and_interval_targets_can_be_met(self):
        models = fit_path_loss_models(
            calibration_rows()
            + calibration_rows("observer-02", "2")
            + calibration_rows("observer-03", "3")
        )
        rows = []
        observers = (("observer-01", "1"), ("observer-02", "2"), ("observer-03", "3"))
        for class_name, advertised, truth in (("consistent", 100, 100), ("mismatch", 300, 100)):
            for run_index in range(6):
                run_id = "{}-run-{:02d}".format(class_name, run_index)
                decision_id = "{}-window-{:02d}".format(class_name, run_index)
                for observer_id, profile_id in observers:
                    rows.append(evaluation_row(
                        "{}-{}".format(decision_id, observer_id), advertised, truth, -80,
                        observer_id=observer_id, profile_id=profile_id,
                        run_id=run_id, decision_window_id=decision_id,
                    ))

        report = evaluate(
            rows,
            models,
            position_error_threshold_m=30,
            max_time_uncertainty_ms=50,
            minimum_quorum=2,
            minimum_independent_runs_per_class=6,
            maximum_95_false_rate_ci_width=0.1,
        )
        aggregate = report["multi_observer"]
        self.assertEqual(aggregate["preregistered_run_count_adequacy"]["status"], "meets_minimum")
        precision = aggregate["preregistered_interval_precision_adequacy"]
        self.assertEqual(precision["status"], "meets_target")
        self.assertEqual(precision["rates"]["false_positive_rate"]["observed_width"], 0.0)
        self.assertEqual(precision["rates"]["false_negative_rate"]["observed_width"], 0.0)

    def test_multi_observer_groups_reject_duplicate_observers_and_truth_label_disagreement(self):
        models = fit_path_loss_models(calibration_rows() + calibration_rows("observer-02", "2"))
        duplicate = [
            evaluation_row("same-node-1", 100, 100, -80, decision_window_id="dup-window"),
            evaluation_row("same-node-2", 100, 100, -80, decision_window_id="dup-window"),
        ]
        with self.assertRaisesRegex(ValueError, "duplicate observer"):
            evaluate(duplicate, models, 30, 50)

        inconsistent_truth = [
            evaluation_row("truth-mismatch", 300, 100, -80,
                           observer_id="observer-01", profile_id="1",
                           run_id="truth-run", decision_window_id="truth-window"),
            evaluation_row("truth-consistent", 100, 100, -80,
                           observer_id="observer-02", profile_id="2",
                           run_id="truth-run", decision_window_id="truth-window"),
        ]
        with self.assertRaisesRegex(ValueError, "inconsistent independent-truth mismatch labels"):
            evaluate(inconsistent_truth, models, 30, 50)

    def test_omits_bootstrap_interval_when_too_many_resamples_lack_a_truth_class(self):
        models = fit_path_loss_models(calibration_rows())
        rows = [
            evaluation_row("clean-window", 100, 100, -80, run_id="clean-run"),
            evaluation_row("mismatch-window", 300, 100, -80, run_id="mismatch-run"),
        ]
        report = evaluate(rows, models, position_error_threshold_m=30,
                          max_time_uncertainty_ms=50)
        self.assertEqual(report["ground_truth_label_coverage"], {
            "position_mismatch": {"samples": 1, "independent_runs": 1},
            "position_consistent": {"samples": 1, "independent_runs": 1},
        })
        bootstrap = report["false_rate_confidence_intervals_95"]
        self.assertIsNone(bootstrap["false_positive_rate"])
        self.assertIsNone(bootstrap["false_negative_rate"])
        self.assertLess(bootstrap["valid_replicates"]["false_positive_rate"], 950)
        self.assertLess(bootstrap["valid_replicates"]["false_negative_rate"], 950)
        self.assertGreater(bootstrap["undefined_replicates"]["false_positive_rate"], 0)
        self.assertGreater(bootstrap["undefined_replicates"]["false_negative_rate"], 0)

    def test_reports_capture_timing_and_receive_quality_metadata(self):
        models = fit_path_loss_models(calibration_rows())
        rows = [
            {
                **evaluation_row("quality-01", 100, 100, -80, run_id="quality-run-01"),
                "time_uncertainty_ms": "10",
                "window_duration_ms": "1000",
                "capture_observation_count": "3",
                "location_packet_count": "2",
            },
            {
                **evaluation_row("quality-02", 100, 100, -80, run_id="quality-run-02"),
                "time_uncertainty_ms": "30",
                "window_duration_ms": "2000",
                "capture_observation_count": "9",
                "location_packet_count": "1",
            },
        ]
        report = evaluate(rows, models, position_error_threshold_m=30,
                          max_time_uncertainty_ms=30)
        self.assertEqual(report["capture_quality"], {
            "sample_count": 2,
            "time_uncertainty_ms": {"min": 10.0, "median": 20.0, "max": 30.0},
            "window_duration_ms": {"min": 1000.0, "median": 1500.0, "max": 2000.0},
            "capture_observation_count": {"min": 3, "median": 6.0, "max": 9},
            "location_packet_count": {"min": 1, "median": 1.5, "max": 2},
        })
        with self.assertRaisesRegex(ValueError, "metadata must be complete"):
            evaluate([{**rows[0], "capture_observation_count": ""}], models, 30, 30)
        with self.assertRaisesRegex(ValueError, "smaller than a positive window"):
            evaluate([{**rows[0], "time_uncertainty_ms": "1000"}], models, 30, 30)
        with self.assertRaisesRegex(ValueError, "exceeds the pre-registered maximum"):
            evaluate([{**rows[0], "time_uncertainty_ms": "31"}], models, 30, 30)
        with self.assertRaisesRegex(ValueError, "metadata must be complete"):
            evaluate([{**rows[0], "time_uncertainty_ms": ""}], models, 30, 30)

    def test_altitude_is_included_in_3d_distance(self):
        distance = local_distance_m((35, 139, 0), (35, 139, 30))
        self.assertAlmostEqual(distance, 30)

    def test_rejects_invalid_threshold_and_duplicate_eval_windows(self):
        models = fit_path_loss_models(calibration_rows())
        row = evaluation_row("same", 100, 100, -80)
        with self.assertRaisesRegex(ValueError, "must be positive"):
            evaluate([row], models, position_error_threshold_m=0,
                     max_time_uncertainty_ms=50)
        with self.assertRaisesRegex(ValueError, "minimum_independent_runs_per_class must be a positive integer"):
            evaluate([row], models, position_error_threshold_m=30,
                     max_time_uncertainty_ms=50, minimum_independent_runs_per_class=0)
        with self.assertRaisesRegex(ValueError, "maximum_95_false_rate_ci_width must be finite and in \[0, 1\]"):
            evaluate([row], models, position_error_threshold_m=30,
                     max_time_uncertainty_ms=50, maximum_95_false_rate_ci_width=1.1)
        with self.assertRaisesRegex(ValueError, "duplicate sample_id"):
            evaluate([row, row], models, position_error_threshold_m=30,
                     max_time_uncertainty_ms=50)

    def test_zero_class_denominators_are_null(self):
        models = fit_path_loss_models(calibration_rows())
        report = evaluate([evaluation_row("one", 100, 100, -80)], models, 30,
                          max_time_uncertainty_ms=50)
        self.assertIsNone(report["metrics"]["recall_sensitivity"])
        self.assertIsNone(report["metrics"]["false_negative_rate"])
        self.assertIsNone(report["false_rate_confidence_intervals_95"])

    def test_cli_reads_separate_csvs_and_emits_a_machine_readable_report(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            calibration_path = Path(temp_dir) / "calibration.csv"
            evaluation_path = Path(temp_dir) / "evaluation.csv"
            preregistration_path = Path(temp_dir) / "preregistration.json"
            rows = calibration_rows()
            write_csv(calibration_path, rows)
            row = evaluation_row("window-1", 100, 100, -80, run_id="heldout-run-01")
            write_csv(evaluation_path, [row])
            write_preregistration(preregistration_path)

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exit_code = main([
                    "--preregistration", str(preregistration_path),
                    "--calibration", str(calibration_path),
                    "--evaluation", str(evaluation_path),
                ])
            self.assertEqual(exit_code, 0)
            report = json.loads(output.getvalue())
            self.assertEqual(report["study_id"], "study-pilot-01")
            self.assertEqual(report["calibration_models"][0]["calibration_profile_id"], 1)
            self.assertEqual(
                report["multi_observer"]["preregistered_run_count_adequacy"]["status"],
                "below_preregistered_minimum",
            )
            self.assertEqual(
                report["multi_observer"]["preregistered_run_count_adequacy"][
                    "declared_minimum_independent_runs_per_class"
                ],
                1,
            )
            self.assertEqual(
                report["multi_observer"]["preregistered_interval_precision_adequacy"]["status"],
                "target_not_met_or_interval_unavailable",
            )
            self.assertEqual(
                report["input_artifacts"]["preregistration"]["sha256"],
                hashlib.sha256(preregistration_path.read_bytes()).hexdigest(),
            )
            self.assertEqual(
                report["input_artifacts"]["calibration"]["sha256"],
                hashlib.sha256(calibration_path.read_bytes()).hexdigest(),
            )
            self.assertEqual(
                report["input_artifacts"]["evaluation"]["bytes"],
                evaluation_path.stat().st_size,
            )
            self.assertIn("do not prove when", report["input_artifacts"]["meaning"])
            self.assertIn("sensor honesty", report["input_artifacts"]["meaning"])

    def test_cli_requires_machine_readable_preregistration(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                build_parser().parse_args([
                    "--calibration", "calibration.csv",
                    "--evaluation", "evaluation.csv",
                ])
        self.assertEqual(raised.exception.code, 2)

    def test_cli_help_renders_preregistration_option(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            with self.assertRaises(SystemExit) as raised:
                build_parser().parse_args(["--help"])
        self.assertEqual(raised.exception.code, 0)
        self.assertIn("--preregistration", output.getvalue())

    def test_cli_report_file_is_private_and_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            calibration_path = Path(temp_dir) / "calibration.csv"
            evaluation_path = Path(temp_dir) / "evaluation.csv"
            preregistration_path = Path(temp_dir) / "preregistration.json"
            report_path = Path(temp_dir) / "report.json"
            rows = calibration_rows()
            write_csv(calibration_path, rows)
            row = evaluation_row("window-1", 100, 100, -80, run_id="heldout-run-01")
            write_csv(evaluation_path, [row])
            write_preregistration(preregistration_path)

            arguments = [
                "--preregistration", str(preregistration_path),
                "--calibration", str(calibration_path),
                "--evaluation", str(evaluation_path),
                "--output", str(report_path),
            ]
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(arguments), 0)
            self.assertEqual(report_path.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(SystemExit) as raised, contextlib.redirect_stderr(io.StringIO()):
                main(arguments)
            self.assertEqual(raised.exception.code, 2)

    def test_cli_rejects_any_evaluation_run_set_mismatch_with_preregistration(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            calibration_path = directory / "calibration.csv"
            evaluation_path = directory / "evaluation.csv"
            preregistration_path = directory / "preregistration.json"
            write_csv(calibration_path, calibration_rows())
            write_csv(evaluation_path, [evaluation_row(
                "window-1", 100, 100, -80, run_id="unregistered-eval-run"
            )])
            write_preregistration(preregistration_path)
            arguments = [
                "--preregistration", str(preregistration_path),
                "--calibration", str(calibration_path),
                "--evaluation", str(evaluation_path),
            ]
            error = io.StringIO()
            with contextlib.redirect_stderr(error):
                with self.assertRaises(SystemExit) as raised:
                    main(arguments)
            self.assertEqual(raised.exception.code, 2)
            self.assertIn("evaluation CSV run_id set differs from preregistration", error.getvalue())

    def test_cli_rejects_any_calibration_run_set_mismatch_with_preregistration(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            calibration_path = directory / "calibration.csv"
            evaluation_path = directory / "evaluation.csv"
            preregistration_path = directory / "preregistration.json"
            write_csv(calibration_path, [
                {**row, "run_id": "unregistered-cal-run"} for row in calibration_rows()
            ])
            write_csv(evaluation_path, [evaluation_row(
                "window-1", 100, 100, -80, run_id="heldout-run-01"
            )])
            write_preregistration(preregistration_path)
            error = io.StringIO()
            with contextlib.redirect_stderr(error):
                with self.assertRaises(SystemExit) as raised:
                    main([
                        "--preregistration", str(preregistration_path),
                        "--calibration", str(calibration_path),
                        "--evaluation", str(evaluation_path),
                    ])
            self.assertEqual(raised.exception.code, 2)
            self.assertIn("calibration CSV run_id set differs from preregistration", error.getvalue())

    def test_cli_rejects_duplicate_json_keys_in_preregistration(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            calibration_path = directory / "calibration.csv"
            evaluation_path = directory / "evaluation.csv"
            preregistration_path = directory / "preregistration.json"
            write_csv(calibration_path, calibration_rows())
            write_csv(evaluation_path, [evaluation_row(
                "window-1", 100, 100, -80, run_id="heldout-run-01"
            )])
            preregistration_path.write_text(
                '{"schema":"signal.rssi-study-preregistration.v1",'
                '"schema":"signal.rssi-study-preregistration.v1"}\n',
                encoding="utf-8",
            )
            os.chmod(preregistration_path, 0o600)
            error = io.StringIO()
            with contextlib.redirect_stderr(error):
                with self.assertRaises(SystemExit) as raised:
                    main([
                        "--preregistration", str(preregistration_path),
                        "--calibration", str(calibration_path),
                        "--evaluation", str(evaluation_path),
                    ])
            self.assertEqual(raised.exception.code, 2)
            self.assertIn("duplicate key", error.getvalue())

    def test_cli_requires_owner_private_non_symlink_preregistration(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            calibration_path = directory / "calibration.csv"
            evaluation_path = directory / "evaluation.csv"
            preregistration_path = directory / "preregistration.json"
            write_csv(calibration_path, calibration_rows())
            write_csv(evaluation_path, [evaluation_row(
                "window-1", 100, 100, -80, run_id="heldout-run-01"
            )])
            write_preregistration(preregistration_path)
            arguments = [
                "--preregistration", str(preregistration_path),
                "--calibration", str(calibration_path),
                "--evaluation", str(evaluation_path),
            ]

            os.chmod(preregistration_path, 0o644)
            error = io.StringIO()
            with contextlib.redirect_stderr(error):
                with self.assertRaises(SystemExit) as raised:
                    main(arguments)
            self.assertEqual(raised.exception.code, 2)
            self.assertIn("no broader than mode 0600", error.getvalue())
            os.chmod(preregistration_path, 0o600)

            linked_path = directory / "preregistration-link.json"
            linked_path.symlink_to(preregistration_path)
            linked_arguments = list(arguments)
            linked_arguments[1] = str(linked_path)
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as raised:
                    main(linked_arguments)
            self.assertEqual(raised.exception.code, 2)

    def test_cli_rejects_world_readable_and_symlinked_measurement_csvs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            calibration_path = directory / "calibration.csv"
            evaluation_path = directory / "evaluation.csv"
            preregistration_path = directory / "preregistration.json"
            write_csv(calibration_path, calibration_rows())
            write_csv(evaluation_path, [evaluation_row(
                "window-1", 100, 100, -80, run_id="heldout-run-01"
            )])
            write_preregistration(preregistration_path)
            arguments = [
                "--preregistration", str(preregistration_path),
                "--calibration", str(calibration_path),
                "--evaluation", str(evaluation_path),
            ]

            os.chmod(calibration_path, 0o644)
            with self.assertRaises(SystemExit) as raised, contextlib.redirect_stderr(io.StringIO()):
                main(arguments)
            self.assertEqual(raised.exception.code, 2)
            os.chmod(calibration_path, 0o600)

            linked_path = directory / "calibration-link.csv"
            linked_path.symlink_to(calibration_path)
            linked_arguments = list(arguments)
            linked_arguments[1] = str(linked_path)
            with self.assertRaises(SystemExit) as raised, contextlib.redirect_stderr(io.StringIO()):
                main(linked_arguments)
            self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
