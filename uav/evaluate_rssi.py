#!/usr/bin/env python3
"""Evaluate an RSSI-to-range model against independent Remote ID ground truth.

The input CSVs are normalized, one-row-per-decision-window datasets. This tool
does not infer trust from Remote ID, attest an observer, or establish that RSSI
was sampled honestly. It reports the performance of the stated calibration and
decision rule only.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import random
import re
import stat
import statistics
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


# Match the current V2 circuit's local planar projection (about 35 degrees N).
# Changing these values requires a new calibration profile and circuit review.
METERS_PER_LATITUDE_DEGREE = 111_320.0
METERS_PER_LONGITUDE_DEGREE = 91_288.0
BOOTSTRAP_SEED = 20_261_004
BOOTSTRAP_REPLICATES = 1_000
V2_FIXED_OBSERVER_COUNT = 3
OPAQUE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
PREREGISTRATION_SCHEMA = "signal.rssi-study-preregistration.v1"
PREREGISTRATION_FIELDS = {
    "schema",
    "study_id",
    "calibration_run_ids",
    "evaluation_run_ids",
    "position_error_threshold_m",
    "max_time_uncertainty_ms",
    "tolerance_ratio",
    "minimum_quorum",
    "minimum_independent_runs_per_class",
    "maximum_95_false_rate_ci_width",
}

CALIBRATION_FIELDS = (
    "sample_id",
    "run_id",
    "observer_id",
    "calibration_profile_id",
    "true_range_m",
    "rssi_dbm_median",
)
EVALUATION_FIELDS = (
    "sample_id",
    "decision_window_id",
    "run_id",
    "observer_id",
    "calibration_profile_id",
    "observer_lat_deg",
    "observer_lon_deg",
    "observer_alt_m",
    "advertised_lat_deg",
    "advertised_lon_deg",
    "advertised_alt_m",
    "truth_lat_deg",
    "truth_lon_deg",
    "truth_alt_m",
    "rssi_dbm_median",
    "time_uncertainty_ms",
    "window_duration_ms",
    "capture_observation_count",
    "location_packet_count",
)


@dataclass(frozen=True)
class PathLossModel:
    """Log-distance model: RSSI(d) = rssi_at_1m - 10*n*log10(d)."""

    rssi_at_1m_dbm: float
    path_loss_exponent: float
    calibration_rmse_db: float
    calibration_samples: int
    calibration_run_count: int
    distinct_calibration_distances: int


def _finite_number(row: Mapping[str, str], field: str, row_number: int) -> float:
    raw = row.get(field)
    if raw is None or not raw.strip():
        raise ValueError("row {}: missing {}".format(row_number, field))
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("row {}: {} must be a number".format(row_number, field)) from exc
    if not math.isfinite(value):
        raise ValueError("row {}: {} must be finite".format(row_number, field))
    return value


def _validate_rssi(row: Mapping[str, str], row_number: int) -> float:
    value = _finite_number(row, "rssi_dbm_median", row_number)
    if not -200.0 <= value <= 50.0:
        raise ValueError("row {}: rssi_dbm_median is outside -200..50 dBm".format(row_number))
    return value


def _read_csv(path: Path, required_fields: Sequence[str]) -> Tuple[List[Dict[str, str]], Dict[str, Any]]:
    nofollow = getattr(os, "O_NOFOLLOW", None)
    if nofollow is None:
        raise ValueError("platform cannot safely reject symlinked CSV inputs")
    try:
        fd = os.open(str(path), os.O_RDONLY | nofollow)
    except OSError as exc:
        raise ValueError("cannot safely open CSV {}: {}".format(path, exc)) from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("CSV input must be a regular file")
        if hasattr(os, "geteuid") and info.st_uid != os.geteuid():
            raise ValueError("CSV input must be owned by the current user")
        mode = info.st_mode & 0o777
        if mode & 0o077 or not mode & 0o400:
            raise ValueError("CSV input must be owner-readable and no broader than mode 0600")
        with os.fdopen(fd, "rb") as source:
            fd = -1
            raw = source.read()
    finally:
        if fd >= 0:
            os.close(fd)
    try:
        decoded = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("{}: CSV must be UTF-8".format(path)) from exc
    reader = csv.DictReader(io.StringIO(decoded, newline=""))
    if reader.fieldnames is None:
        raise ValueError("{}: CSV header is missing".format(path))
    missing = [field for field in required_fields if field not in reader.fieldnames]
    if missing:
        raise ValueError("{}: missing columns: {}".format(path, ", ".join(missing)))
    rows = list(reader)
    if not rows:
        raise ValueError("{}: no data rows".format(path))
    return rows, {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def _unique_json_object(pairs: Sequence[Tuple[str, Any]]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("preregistration JSON contains a duplicate key")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError("preregistration JSON contains a non-standard numeric constant")


def _read_preregistration(path: Path) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    nofollow = getattr(os, "O_NOFOLLOW", None)
    if nofollow is None:
        raise ValueError("platform cannot safely reject symlinked preregistration input")
    try:
        fd = os.open(str(path), os.O_RDONLY | nofollow)
    except OSError as exc:
        raise ValueError("cannot safely open preregistration JSON: {}".format(exc)) from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("preregistration input must be a regular file")
        if hasattr(os, "geteuid") and info.st_uid != os.geteuid():
            raise ValueError("preregistration input must be owned by the current user")
        mode = info.st_mode & 0o777
        if mode & 0o077 or not mode & 0o400:
            raise ValueError("preregistration input must be owner-readable and no broader than mode 0600")
        with os.fdopen(fd, "rb") as source:
            fd = -1
            raw = source.read(1024 * 1024 + 1)
    finally:
        if fd >= 0:
            os.close(fd)
    if len(raw) > 1024 * 1024:
        raise ValueError("preregistration JSON exceeds 1 MiB")
    try:
        decoded = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("preregistration JSON must be UTF-8") from exc
    try:
        document = json.loads(
            decoded,
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError("preregistration JSON is invalid") from exc
    if not isinstance(document, dict):
        raise ValueError("preregistration JSON must be an object")
    missing = PREREGISTRATION_FIELDS - set(document)
    unexpected = set(document) - PREREGISTRATION_FIELDS
    if missing or unexpected:
        raise ValueError("preregistration JSON fields do not match the supported schema")
    if document["schema"] != PREREGISTRATION_SCHEMA:
        raise ValueError("unsupported preregistration schema")
    if not isinstance(document["study_id"], str) or not OPAQUE_ID.fullmatch(document["study_id"]):
        raise ValueError("preregistration study_id must be a bounded opaque ASCII ID")

    run_sets: Dict[str, set[str]] = {}
    for field, minimum_length in (("calibration_run_ids", 2), ("evaluation_run_ids", 1)):
        values = document[field]
        if not isinstance(values, list) or len(values) < minimum_length:
            raise ValueError("preregistration {} must contain at least {} run IDs".format(field, minimum_length))
        if any(not isinstance(value, str) or not OPAQUE_ID.fullmatch(value) for value in values):
            raise ValueError("preregistration {} must contain bounded opaque ASCII IDs".format(field))
        if len(set(values)) != len(values):
            raise ValueError("preregistration {} contains duplicate run IDs".format(field))
        run_sets[field] = set(values)
    if run_sets["calibration_run_ids"] & run_sets["evaluation_run_ids"]:
        raise ValueError("preregistered calibration and evaluation run IDs must be disjoint")

    def finite_number(field: str) -> float:
        value = document[field]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError("preregistration {} must be a finite number".format(field))
        return float(value)

    if finite_number("position_error_threshold_m") <= 0:
        raise ValueError("preregistration position_error_threshold_m must be positive")
    if finite_number("max_time_uncertainty_ms") < 0:
        raise ValueError("preregistration max_time_uncertainty_ms must be nonnegative")
    if not 0 <= finite_number("tolerance_ratio") < 1:
        raise ValueError("preregistration tolerance_ratio must be in [0, 1)")
    for field in ("minimum_quorum", "minimum_independent_runs_per_class"):
        value = document[field]
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ValueError("preregistration {} must be a positive integer".format(field))
    if document["minimum_quorum"] > V2_FIXED_OBSERVER_COUNT:
        raise ValueError("preregistration minimum_quorum exceeds the current V2 observer topology")
    if not 0 <= finite_number("maximum_95_false_rate_ci_width") <= 1:
        raise ValueError("preregistration maximum_95_false_rate_ci_width must be in [0, 1]")

    return document, {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def validate_preregistered_run_sets(
    calibration_rows: Sequence[Mapping[str, str]],
    evaluation_rows: Sequence[Mapping[str, str]],
    preregistration: Mapping[str, Any],
) -> None:
    """Require the scored run sets to match the private preregistration exactly."""
    expected_calibration = set(preregistration["calibration_run_ids"])
    expected_evaluation = set(preregistration["evaluation_run_ids"])
    actual_calibration = _run_ids(calibration_rows, "calibration")
    actual_evaluation = _run_ids(evaluation_rows, "evaluation")
    if actual_calibration != expected_calibration:
        raise ValueError(
            "calibration CSV run_id set differs from preregistration ({} missing, {} unexpected)".format(
                len(expected_calibration - actual_calibration),
                len(actual_calibration - expected_calibration),
            )
        )
    if actual_evaluation != expected_evaluation:
        raise ValueError(
            "evaluation CSV run_id set differs from preregistration ({} missing, {} unexpected)".format(
                len(expected_evaluation - actual_evaluation),
                len(actual_evaluation - expected_evaluation),
            )
        )


def _validate_sample_ids(rows: Iterable[Mapping[str, str]], source: str) -> None:
    seen = set()
    for row_number, row in enumerate(rows, start=2):
        sample_id = (row.get("sample_id") or "").strip()
        if not sample_id:
            raise ValueError("{} row {}: sample_id is required".format(source, row_number))
        if sample_id in seen:
            raise ValueError("{} row {}: duplicate sample_id {}".format(source, row_number, sample_id))
        seen.add(sample_id)


def _run_ids(rows: Iterable[Mapping[str, str]], source: str) -> set[str]:
    run_ids = set()
    for row_number, row in enumerate(rows, start=2):
        run_id = (row.get("run_id") or "").strip()
        if not run_id:
            raise ValueError("{} row {}: run_id is required".format(source, row_number))
        run_ids.add(run_id)
    return run_ids


def validate_holdout_separation(
    calibration_rows: Sequence[Mapping[str, str]],
    evaluation_rows: Sequence[Mapping[str, str]],
) -> None:
    """Reject sample or independent-run leakage between calibration and evaluation."""
    _validate_sample_ids(calibration_rows, "calibration")
    _validate_sample_ids(evaluation_rows, "evaluation")
    calibration_runs = _run_ids(calibration_rows, "calibration")
    evaluation_runs = _run_ids(evaluation_rows, "evaluation")
    shared_runs = calibration_runs & evaluation_runs
    if shared_runs:
        raise ValueError(
            "calibration and evaluation share {} run_id(s); keep complete runs held out".format(
                len(shared_runs)
            )
        )

    calibration_samples = {
        (row.get("sample_id") or "").strip() for row in calibration_rows
    }
    evaluation_samples = {
        (row.get("sample_id") or "").strip() for row in evaluation_rows
    }
    shared_samples = calibration_samples & evaluation_samples
    if shared_samples:
        raise ValueError(
            "calibration and evaluation share {} sample_id(s)".format(len(shared_samples))
        )


def _capture_quality_summary(
    rows: Sequence[Mapping[str, str]],
    max_time_uncertainty_ms: float,
) -> Dict[str, Any]:
    fields = (
        "time_uncertainty_ms",
        "window_duration_ms",
        "capture_observation_count",
        "location_packet_count",
    )
    uncertainty_values: List[float] = []
    duration_values: List[float] = []
    capture_counts: List[int] = []
    location_counts: List[int] = []
    for row_number, row in enumerate(rows, start=2):
        missing = [field for field in fields if not (row.get(field) or "").strip()]
        if missing:
            raise ValueError(
                "evaluation row {}: capture quality metadata must be complete; missing {}".format(
                    row_number, ", ".join(missing)
                )
            )
        uncertainty = _finite_number(row, "time_uncertainty_ms", row_number)
        duration = _finite_number(row, "window_duration_ms", row_number)
        if uncertainty < 0 or duration <= 0 or uncertainty >= duration:
            raise ValueError(
                "evaluation row {}: time uncertainty must be nonnegative and smaller than a positive window".format(
                    row_number
                )
            )
        if uncertainty > max_time_uncertainty_ms:
            raise ValueError(
                "evaluation row {}: time uncertainty {} ms exceeds the pre-registered maximum {} ms".format(
                    row_number, uncertainty, max_time_uncertainty_ms
                )
            )
        uncertainty_values.append(uncertainty)
        duration_values.append(duration)
        counts = []
        for field in ("capture_observation_count", "location_packet_count"):
            raw = (row.get(field) or "").strip()
            if not re.fullmatch(r"(?:0|[1-9][0-9]*)", raw) or int(raw) < 1:
                raise ValueError("evaluation row {}: {} must be a positive integer".format(row_number, field))
            counts.append(int(raw))
        capture_counts.append(counts[0])
        location_counts.append(counts[1])

    def distribution(values: Sequence[float]) -> Dict[str, float]:
        return {
            "min": min(values),
            "median": statistics.median(values),
            "max": max(values),
        }

    return {
        "sample_count": len(rows),
        "time_uncertainty_ms": distribution(uncertainty_values),
        "window_duration_ms": distribution(duration_values),
        "capture_observation_count": distribution(capture_counts),
        "location_packet_count": distribution(location_counts),
    }


def _observer_and_profile(row: Mapping[str, str], row_number: int) -> Tuple[str, int]:
    observer_id = (row.get("observer_id") or "").strip()
    if not observer_id:
        raise ValueError("row {}: observer_id is required".format(row_number))
    raw_profile_id = (row.get("calibration_profile_id") or "").strip()
    try:
        profile_id = int(raw_profile_id)
    except ValueError as exc:
        raise ValueError("row {}: calibration_profile_id must be a uint32 integer".format(row_number)) from exc
    if not 0 <= profile_id <= 0xFFFFFFFF:
        raise ValueError("row {}: calibration_profile_id must be a uint32 integer".format(row_number))
    return observer_id, profile_id


def fit_path_loss_model(rows: Sequence[Mapping[str, str]]) -> PathLossModel:
    """Fit the log-distance model by ordinary least squares in RSSI dBm."""
    if len(rows) < 3:
        raise ValueError("calibration requires at least 3 independent windows")
    _validate_sample_ids(rows, "calibration")
    calibration_runs = _run_ids(rows, "calibration")
    if len(calibration_runs) < 2:
        raise ValueError("calibration requires at least 2 independent run_id values")

    points: List[Tuple[float, float]] = []
    for row_number, row in enumerate(rows, start=2):
        distance_m = _finite_number(row, "true_range_m", row_number)
        if distance_m <= 0:
            raise ValueError("calibration row {}: true_range_m must be positive".format(row_number))
        rssi = _validate_rssi(row, row_number)
        points.append((math.log10(distance_m), rssi))

    x_mean = sum(x for x, _ in points) / len(points)
    y_mean = sum(y for _, y in points) / len(points)
    variance_x = sum((x - x_mean) ** 2 for x, _ in points)
    if variance_x <= 1e-12:
        raise ValueError("calibration requires at least 2 distinct known distances")
    slope = sum((x - x_mean) * (y - y_mean) for x, y in points) / variance_x
    intercept = y_mean - slope * x_mean
    exponent = -slope / 10.0
    if not math.isfinite(exponent) or exponent <= 0 or exponent > 10:
        raise ValueError("fitted path-loss exponent must be in (0, 10]; review calibration data")

    squared_error = sum((y - (intercept + slope * x)) ** 2 for x, y in points)
    distinct_distances = len({round(x, 12) for x, _ in points})
    return PathLossModel(
        rssi_at_1m_dbm=intercept,
        path_loss_exponent=exponent,
        calibration_rmse_db=math.sqrt(squared_error / len(points)),
        calibration_samples=len(points),
        calibration_run_count=len(calibration_runs),
        distinct_calibration_distances=distinct_distances,
    )


def fit_path_loss_models(rows: Sequence[Mapping[str, str]]) -> Dict[Tuple[str, int], PathLossModel]:
    """Fit a separate model for each observer and immutable profile ID."""
    _validate_sample_ids(rows, "calibration")
    groups: Dict[Tuple[str, int], List[Mapping[str, str]]] = {}
    for row_number, row in enumerate(rows, start=2):
        key = _observer_and_profile(row, row_number)
        groups.setdefault(key, []).append(row)
    if not groups:
        raise ValueError("calibration requires at least one observer/profile group")
    return {key: fit_path_loss_model(group) for key, group in groups.items()}


def _coordinate(row: Mapping[str, str], prefix: str, axis: str, row_number: int) -> float:
    field = "{}_{}_deg".format(prefix, axis)
    value = _finite_number(row, field, row_number)
    minimum, maximum = (-90.0, 90.0) if axis == "lat" else (-180.0, 180.0)
    if not minimum <= value <= maximum:
        raise ValueError("row {}: {} is outside valid bounds".format(row_number, field))
    return value


def _position_altitude(row: Mapping[str, str], prefix: str, row_number: int) -> float:
    return _finite_number(row, "{}_alt_m".format(prefix), row_number)


def local_distance_m(
    first: Tuple[float, float, float],
    second: Tuple[float, float, float],
) -> float:
    """3-D distance using the same fixed local projection as the V2 circuit."""
    lat_delta_m = (first[0] - second[0]) * METERS_PER_LATITUDE_DEGREE
    lon_delta_m = (first[1] - second[1]) * METERS_PER_LONGITUDE_DEGREE
    alt_delta_m = first[2] - second[2]
    return math.sqrt(lat_delta_m ** 2 + lon_delta_m ** 2 + alt_delta_m ** 2)


def _safe_ratio(numerator: int, denominator: int) -> Optional[float]:
    return numerator / denominator if denominator else None


def _summarize_predictions(
    results: Sequence[Tuple[str, bool, bool, float]],
) -> Dict[str, Any]:
    tp, fp, tn, fn = _confusion_counts(results)
    mismatch_runs = {run_id for run_id, _, truth_mismatch, _ in results if truth_mismatch}
    consistent_runs = {run_id for run_id, _, truth_mismatch, _ in results if not truth_mismatch}
    mismatch_samples = sum(1 for _, _, truth_mismatch, _ in results if truth_mismatch)
    consistent_samples = len(results) - mismatch_samples
    range_errors: List[float] = []
    for _, _, _, range_error in results:
        range_errors.append(range_error)
    total = len(results)
    return {
        "sample_count": total,
        "independent_run_count": len({run_id for run_id, _, _, _ in results}),
        "ground_truth_label_coverage": {
            "position_mismatch": {"samples": mismatch_samples, "independent_runs": len(mismatch_runs)},
            "position_consistent": {"samples": consistent_samples, "independent_runs": len(consistent_runs)},
        },
        "confusion_matrix": {"true_positive": tp, "false_positive": fp, "true_negative": tn, "false_negative": fn},
        "metrics": {
            "accuracy": _safe_ratio(tp + tn, total),
            "precision": _safe_ratio(tp, tp + fp),
            "recall_sensitivity": _safe_ratio(tp, tp + fn),
            "specificity": _safe_ratio(tn, tn + fp),
            "false_positive_rate": _safe_ratio(fp, fp + tn),
            "false_negative_rate": _safe_ratio(fn, fn + tp),
        },
        "false_rate_confidence_intervals_95": _run_cluster_bootstrap(results),
        "range_error_m": {
            "mae": sum(abs(error) for error in range_errors) / total,
            "rmse": math.sqrt(sum(error ** 2 for error in range_errors) / total),
        },
    }


def _summarize_multi_observer_decisions(
    groups: Mapping[Tuple[str, str], Mapping[str, Any]],
    minimum_quorum: int,
) -> Dict[str, Any]:
    decisions = []
    finalized: List[Tuple[str, bool, bool, float]] = []
    status_counts = {
        "no_inconsistency_observed": 0,
        "position_inconsistency_suspected": 0,
        "insufficient_evidence": 0,
        "conflicting_counts": 0,
        "unsupported_observer_count": 0,
    }
    mismatch_runs = set()
    consistent_runs = set()
    mismatch_groups = 0
    consistent_groups = 0

    for (run_id, decision_window_id), group in sorted(groups.items()):
        consistent = group["consistent_count"]
        suspicious = group["suspicious_count"]
        consistent_reached = consistent >= minimum_quorum
        suspicious_reached = suspicious >= minimum_quorum
        observer_count = len(group["observers"])
        if observer_count < V2_FIXED_OBSERVER_COUNT:
            # The current recursive proof path consumes exactly three leaves.
            # Even a mathematical quorum from only two rows is not a proof-ready
            # decision for this topology.
            status = "INSUFFICIENT_EVIDENCE"
            status_counts["insufficient_evidence"] += 1
        elif observer_count > V2_FIXED_OBSERVER_COUNT:
            # Do not silently pretend a wider group was processed by pcd3.
            status = "UNSUPPORTED_OBSERVER_COUNT_FOR_CURRENT_V2_TOPOLOGY"
            status_counts["unsupported_observer_count"] += 1
        elif consistent_reached and suspicious_reached:
            status = "CONFLICTING_COUNTS_NO_FINAL_PROOF"
            status_counts["conflicting_counts"] += 1
        elif suspicious_reached:
            status = "POSITION_INCONSISTENCY_SUSPECTED"
            status_counts["position_inconsistency_suspected"] += 1
            finalized.append((run_id, True, group["truth_mismatch"], 0.0))
        elif consistent_reached:
            status = "NO_INCONSISTENCY_OBSERVED"
            status_counts["no_inconsistency_observed"] += 1
            finalized.append((run_id, False, group["truth_mismatch"], 0.0))
        else:
            status = "INSUFFICIENT_EVIDENCE"
            status_counts["insufficient_evidence"] += 1

        if group["truth_mismatch"]:
            mismatch_groups += 1
            mismatch_runs.add(run_id)
        else:
            consistent_groups += 1
            consistent_runs.add(run_id)
        decisions.append({
            "run_id": run_id,
            "decision_window_id": decision_window_id,
            "observer_count": observer_count,
            "consistent_count": consistent,
            "suspicious_count": suspicious,
            "ground_truth_mismatch": group["truth_mismatch"],
            "final_status": status,
        })

    if finalized:
        summary = _summarize_predictions(finalized)
        summary.pop("range_error_m")
    else:
        summary = {
            "sample_count": 0,
            "independent_run_count": 0,
            "confusion_matrix": {
                "true_positive": 0,
                "false_positive": 0,
                "true_negative": 0,
                "false_negative": 0,
            },
            "metrics": {
                "accuracy": None,
                "precision": None,
                "recall_sensitivity": None,
                "specificity": None,
                "false_positive_rate": None,
                "false_negative_rate": None,
            },
            "false_rate_confidence_intervals_95": None,
        }
    summary["ground_truth_label_coverage"] = {
        "position_mismatch": {
            "decision_windows": mismatch_groups,
            "independent_runs": len(mismatch_runs),
        },
        "position_consistent": {
            "decision_windows": consistent_groups,
            "independent_runs": len(consistent_runs),
        },
    }
    finalized_mismatch = [result for result in finalized if result[2]]
    finalized_consistent = [result for result in finalized if not result[2]]
    summary["finalized_truth_class_coverage"] = {
        "position_mismatch": {
            "decision_windows": len(finalized_mismatch),
            "independent_runs": len({result[0] for result in finalized_mismatch}),
        },
        "position_consistent": {
            "decision_windows": len(finalized_consistent),
            "independent_runs": len({result[0] for result in finalized_consistent}),
        },
    }
    return {
        "expected_observer_count": V2_FIXED_OBSERVER_COUNT,
        "minimum_quorum": minimum_quorum,
        "decision_window_count": len(groups),
        "finalized_count": len(finalized),
        "status_counts": status_counts,
        "classification_scope": (
            "current pcd3 V2 recursive topology requires exactly 3 distinct observers; "
            "only finalized decisions at that count enter false-positive/negative metrics. "
            "Smaller groups are insufficient, larger groups are unsupported, and conflicting "
            "groups are excluded"
        ),
        **summary,
        "decisions": decisions,
    }


def _confusion_counts(results: Sequence[Tuple[str, bool, bool, float]]) -> Tuple[int, int, int, int]:
    tp = fp = tn = fn = 0
    for _, predicted_suspicious, truth_mismatch, _ in results:
        if predicted_suspicious and truth_mismatch:
            tp += 1
        elif predicted_suspicious:
            fp += 1
        elif truth_mismatch:
            fn += 1
        else:
            tn += 1
    return tp, fp, tn, fn


def _percentile(values: Sequence[float], quantile: float) -> float:
    ordered = sorted(values)
    position = quantile * (len(ordered) - 1)
    lower_index = int(math.floor(position))
    upper_index = int(math.ceil(position))
    if lower_index == upper_index:
        return ordered[lower_index]
    fraction = position - lower_index
    return ordered[lower_index] * (1 - fraction) + ordered[upper_index] * fraction


def _run_cluster_bootstrap(
    results: Sequence[Tuple[str, bool, bool, float]],
) -> Optional[Dict[str, Any]]:
    """Percentile intervals resample whole independent runs, not packets/windows."""
    by_run: Dict[str, List[Tuple[str, bool, bool, float]]] = {}
    for result in results:
        by_run.setdefault(result[0], []).append(result)
    run_ids = sorted(by_run)
    if len(run_ids) < 2:
        return None

    rng = random.Random(BOOTSTRAP_SEED)
    false_positive_rates: List[float] = []
    false_negative_rates: List[float] = []
    for _ in range(BOOTSTRAP_REPLICATES):
        sampled = []
        for _ in run_ids:
            sampled.extend(by_run[rng.choice(run_ids)])
        tp, fp, tn, fn = _confusion_counts(sampled)
        fpr = _safe_ratio(fp, fp + tn)
        fnr = _safe_ratio(fn, fn + tp)
        if fpr is not None:
            false_positive_rates.append(fpr)
        if fnr is not None:
            false_negative_rates.append(fnr)

    def interval(values: Sequence[float]) -> Optional[Dict[str, float]]:
        minimum_valid = math.ceil(BOOTSTRAP_REPLICATES * 0.95)
        if len(values) < minimum_valid:
            return None
        return {"low": _percentile(values, 0.025), "high": _percentile(values, 0.975)}

    valid_replicates = {
        "false_positive_rate": len(false_positive_rates),
        "false_negative_rate": len(false_negative_rates),
    }
    return {
        "method": (
            "percentile bootstrap resampling whole run_id clusters; an interval is omitted "
            "when fewer than 95% of replicates contain the class needed for that rate"
        ),
        "replicates": BOOTSTRAP_REPLICATES,
        "seed": BOOTSTRAP_SEED,
        "valid_replicates": valid_replicates,
        "undefined_replicates": {
            name: BOOTSTRAP_REPLICATES - count for name, count in valid_replicates.items()
        },
        "false_positive_rate": interval(false_positive_rates),
        "false_negative_rate": interval(false_negative_rates),
    }


def evaluate(
    rows: Sequence[Mapping[str, str]],
    models: Mapping[Tuple[str, int], PathLossModel],
    position_error_threshold_m: float,
    max_time_uncertainty_ms: float,
    tolerance_ratio: float = 0.9,
    include_samples: bool = False,
    minimum_quorum: int = 2,
    minimum_independent_runs_per_class: Optional[int] = None,
    maximum_95_false_rate_ci_width: Optional[float] = None,
) -> Dict[str, Any]:
    """Evaluate per-observer RSSI outcomes and V2-style grouped quorum decisions."""
    if not rows:
        raise ValueError("evaluation requires at least one independent window")
    if not math.isfinite(position_error_threshold_m) or position_error_threshold_m <= 0:
        raise ValueError("position_error_threshold_m must be positive and finite")
    if not math.isfinite(max_time_uncertainty_ms) or max_time_uncertainty_ms < 0:
        raise ValueError("max_time_uncertainty_ms must be nonnegative and finite")
    if not math.isfinite(tolerance_ratio) or not 0 <= tolerance_ratio < 1:
        raise ValueError("tolerance_ratio must be in [0, 1)")
    if not isinstance(minimum_quorum, int) or isinstance(minimum_quorum, bool) or not 1 <= minimum_quorum <= 0xFFFFFFFF:
        raise ValueError("minimum_quorum must be a positive uint32 integer")
    if minimum_independent_runs_per_class is not None and (
        not isinstance(minimum_independent_runs_per_class, int)
        or isinstance(minimum_independent_runs_per_class, bool)
        or minimum_independent_runs_per_class < 1
    ):
        raise ValueError("minimum_independent_runs_per_class must be a positive integer")
    if maximum_95_false_rate_ci_width is not None and (
        not math.isfinite(maximum_95_false_rate_ci_width)
        or not 0 <= maximum_95_false_rate_ci_width <= 1
    ):
        raise ValueError("maximum_95_false_rate_ci_width must be finite and in [0, 1]")
    _validate_sample_ids(rows, "evaluation")
    capture_quality = _capture_quality_summary(rows, max_time_uncertainty_ms)

    results: List[Tuple[str, bool, bool, float]] = []
    results_by_observer: Dict[str, List[Tuple[str, bool, bool, float]]] = {}
    decision_groups: Dict[Tuple[str, str], Dict[str, Any]] = {}
    sample_reports: List[Dict[str, Any]] = []
    for row_number, row in enumerate(rows, start=2):
        run_id = (row.get("run_id") or "").strip()
        if not OPAQUE_ID.fullmatch(run_id):
            raise ValueError("row {}: run_id must be a bounded opaque ASCII ID".format(row_number))
        decision_window_id = (row.get("decision_window_id") or "").strip()
        if not OPAQUE_ID.fullmatch(decision_window_id):
            raise ValueError("row {}: decision_window_id must be a bounded opaque ASCII ID".format(row_number))
        observer_id, profile_id = _observer_and_profile(row, row_number)
        if not OPAQUE_ID.fullmatch(observer_id):
            raise ValueError("row {}: observer_id must be a bounded opaque ASCII ID".format(row_number))
        model = models.get((observer_id, profile_id))
        if model is None:
            raise ValueError(
                "evaluation row {}: no calibration model for observer {} profile {}".format(
                    row_number, observer_id, profile_id
                )
            )
        observer = (
            _coordinate(row, "observer", "lat", row_number),
            _coordinate(row, "observer", "lon", row_number),
            _position_altitude(row, "observer", row_number),
        )
        advertised = (
            _coordinate(row, "advertised", "lat", row_number),
            _coordinate(row, "advertised", "lon", row_number),
            _position_altitude(row, "advertised", row_number),
        )
        truth = (
            _coordinate(row, "truth", "lat", row_number),
            _coordinate(row, "truth", "lon", row_number),
            _position_altitude(row, "truth", row_number),
        )
        rssi = _validate_rssi(row, row_number)
        log10_range = (model.rssi_at_1m_dbm - rssi) / (10.0 * model.path_loss_exponent)
        if not -6 <= log10_range <= 9:
            raise ValueError("evaluation row {}: RSSI implies an implausible model range".format(row_number))
        estimated_range_m = 10.0 ** log10_range
        claimed_range_m = local_distance_m(observer, advertised)
        true_range_m = local_distance_m(observer, truth)
        position_error_m = local_distance_m(advertised, truth)

        # Same band semantics as the V2 circuit: claimed distance must be within
        # [measured_range*(1-tolerance), measured_range*(1+tolerance)].
        consistent = (
            (1.0 - tolerance_ratio) * estimated_range_m
            <= claimed_range_m
            <= (1.0 + tolerance_ratio) * estimated_range_m
        )
        predicted_suspicious = not consistent
        truth_mismatch = position_error_m >= position_error_threshold_m
        result = (run_id, predicted_suspicious, truth_mismatch, estimated_range_m - true_range_m)
        results.append(result)
        results_by_observer.setdefault(observer_id, []).append(result)

        group_key = (run_id, decision_window_id)
        group = decision_groups.setdefault(group_key, {
            "observers": set(),
            "consistent_count": 0,
            "suspicious_count": 0,
            "truth_mismatch": truth_mismatch,
        })
        if observer_id in group["observers"]:
            raise ValueError(
                "decision window {} has duplicate observer {}".format(decision_window_id, observer_id)
            )
        if truth_mismatch != group["truth_mismatch"]:
            raise ValueError(
                "decision window {} has inconsistent independent-truth mismatch labels".format(decision_window_id)
            )
        group["observers"].add(observer_id)
        group["suspicious_count" if predicted_suspicious else "consistent_count"] += 1

        if include_samples:
            sample_reports.append({
                "sample_id": (row.get("sample_id") or "").strip(),
                "decision_window_id": decision_window_id,
                "run_id": run_id,
                "observer_id": observer_id,
                "calibration_profile_id": profile_id,
                "ground_truth_mismatch": truth_mismatch,
                "predicted_suspicious": predicted_suspicious,
                "position_error_m": position_error_m,
                "claimed_range_m": claimed_range_m,
                "ground_truth_range_m": true_range_m,
                "rssi_estimated_range_m": estimated_range_m,
                "rssi_dbm_median": rssi,
            })

    summary = _summarize_predictions(results)
    multi_observer_summary = _summarize_multi_observer_decisions(decision_groups, minimum_quorum)
    finalized_coverage = multi_observer_summary["finalized_truth_class_coverage"]
    if minimum_independent_runs_per_class is None:
        multi_observer_summary["preregistered_run_count_adequacy"] = {
            "status": "not_assessed",
            "declared_minimum_independent_runs_per_class": None,
            "classes": None,
            "note": "No preregistered run-count minimum was supplied to the evaluator.",
        }
    else:
        class_adequacy = {
            label: {
                "observed_finalized_independent_runs": coverage["independent_runs"],
                "declared_minimum_independent_runs": minimum_independent_runs_per_class,
                "meets_minimum": coverage["independent_runs"] >= minimum_independent_runs_per_class,
            }
            for label, coverage in finalized_coverage.items()
        }
        meets_minimum = all(entry["meets_minimum"] for entry in class_adequacy.values())
        multi_observer_summary["preregistered_run_count_adequacy"] = {
            "status": "meets_minimum" if meets_minimum else "below_preregistered_minimum",
            "declared_minimum_independent_runs_per_class": minimum_independent_runs_per_class,
            "classes": class_adequacy,
            "note": (
                "This checks run-count coverage only; meeting the floor does not establish useful "
                "precision. Review false-rate intervals and any preregistered precision target."
            ),
        }
    if maximum_95_false_rate_ci_width is None:
        multi_observer_summary["preregistered_interval_precision_adequacy"] = {
            "status": "not_assessed",
            "declared_maximum_95_false_rate_ci_width": None,
            "rates": None,
            "note": "No preregistered confidence-interval width target was supplied to the evaluator.",
        }
    else:
        aggregate_intervals = multi_observer_summary["false_rate_confidence_intervals_95"]

        def assess_interval_width(rate_name: str) -> Dict[str, Any]:
            interval = aggregate_intervals.get(rate_name) if aggregate_intervals is not None else None
            if interval is None:
                return {
                    "interval_95": None,
                    "observed_width": None,
                    "meets_maximum_width": False,
                    "status": "interval_unavailable",
                }
            width = interval["high"] - interval["low"]
            meets_width = width <= maximum_95_false_rate_ci_width
            return {
                "interval_95": interval,
                "observed_width": width,
                "meets_maximum_width": meets_width,
                "status": "meets_target" if meets_width else "interval_too_wide",
            }

        rate_adequacy = {
            "false_positive_rate": assess_interval_width("false_positive_rate"),
            "false_negative_rate": assess_interval_width("false_negative_rate"),
        }
        precision_met = all(rate["meets_maximum_width"] for rate in rate_adequacy.values())
        multi_observer_summary["preregistered_interval_precision_adequacy"] = {
            "status": "meets_target" if precision_met else "target_not_met_or_interval_unavailable",
            "declared_maximum_95_false_rate_ci_width": maximum_95_false_rate_ci_width,
            "rates": rate_adequacy,
            "note": "A width target is descriptive precision, not a guarantee that the study is unbiased or representative.",
        }
    aggregate_by_group = {
        (decision["run_id"], decision["decision_window_id"]): decision
        for decision in multi_observer_summary["decisions"]
    }
    if include_samples:
        for sample in sample_reports:
            decision = aggregate_by_group[(sample["run_id"], sample["decision_window_id"])]
            sample["aggregate_final_status"] = decision["final_status"]
            sample["aggregate_consistent_count"] = decision["consistent_count"]
            sample["aggregate_suspicious_count"] = decision["suspicious_count"]
    per_observer = {
        observer_id: _summarize_predictions(observer_results)
        for observer_id, observer_results in sorted(results_by_observer.items())
    }
    serialized_models = [
        {"observer_id": observer_id, "calibration_profile_id": profile_id, **asdict(model)}
        for (observer_id, profile_id), model in sorted(models.items())
    ]
    report: Dict[str, Any] = {
        "schema": "signal.rssi-evaluation.v1",
        "sample_count": summary["sample_count"],
        "independent_run_count": summary["independent_run_count"],
        "ground_truth_label_coverage": summary["ground_truth_label_coverage"],
        "calibration_models": serialized_models,
        "decision_policy": {
            "position_error_threshold_m": position_error_threshold_m,
            "max_time_uncertainty_ms": max_time_uncertainty_ms,
            "consistency_tolerance_ratio": tolerance_ratio,
            "minimum_quorum": minimum_quorum,
            "minimum_independent_runs_per_truth_class": minimum_independent_runs_per_class,
            "maximum_95_false_rate_ci_width": maximum_95_false_rate_ci_width,
            "position_mismatch_label": "3-D advertised-vs-independent-truth distance >= threshold",
            "prediction": "suspicious unless claimed range is within measured RSSI range +/- tolerance",
            "distance_projection": "local planar projection matching V2 circuit constants (about 35 degrees N)",
        },
        "capture_quality": capture_quality,
        "confusion_matrix": summary["confusion_matrix"],
        "metrics": summary["metrics"],
        "false_rate_confidence_intervals_95": summary["false_rate_confidence_intervals_95"],
        "range_error_m": summary["range_error_m"],
        "multi_observer": multi_observer_summary,
        "per_observer": per_observer,
        "limitations": [
            "Calibration and evaluation run_id/sample_id overlap is rejected; report is only as valid as independent truth labels.",
            (
                "Fit one calibration profile per receiver, antenna, placement, and relevant environment; "
                "RSSI is hardware- and environment-dependent."
            ),
            (
                "Confidence intervals resample run_id clusters; at least 2 independent runs are needed, "
                "few runs produce unstable intervals, and a rate interval is omitted if fewer than 95% "
                "of its bootstrap replicates contain the required truth class."
            ),
            "The model does not prove sensor honesty, Remote ID authenticity, or an observer's claimed location.",
            "Synthetic unit-test data validates code only and is not field-evaluation evidence.",
            "A preregistered minimum independent-run count is a coverage floor, not a guarantee of statistical precision.",
            "Declared timing bounds are not independently authenticated; samples exceeding the pre-registered maximum are rejected.",
        ],
    }
    if include_samples:
        report["samples"] = sample_reports
    return report


def _write_private_report(path: Path, serialized: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as destination:
            destination.write(serialized)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            path.unlink()
        except OSError:
            pass
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate calibrated RSSI position-mismatch detection.")
    parser.add_argument(
        "--preregistration", required=True, type=Path,
        help="owner-private machine-readable preregistration JSON; supplies policy and expected run IDs",
    )
    parser.add_argument("--calibration", required=True, type=Path, help="CSV with true_range_m and median RSSI")
    parser.add_argument(
        "--evaluation", required=True, type=Path,
        help="held-out CSV with independent truth and RID position",
    )
    parser.add_argument("--output", type=Path,
                        help="create a new owner-private JSON report; existing files are not overwritten")
    parser.add_argument(
        "--include-samples", action="store_true",
        help="include per-window scalar results in the report",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        preregistration, preregistration_artifact = _read_preregistration(args.preregistration)
        calibration_rows, calibration_artifact = _read_csv(args.calibration, CALIBRATION_FIELDS)
        evaluation_rows, evaluation_artifact = _read_csv(args.evaluation, EVALUATION_FIELDS)
        validate_holdout_separation(calibration_rows, evaluation_rows)
        validate_preregistered_run_sets(calibration_rows, evaluation_rows, preregistration)
        models = fit_path_loss_models(calibration_rows)
        report = evaluate(
            evaluation_rows,
            models,
            float(preregistration["position_error_threshold_m"]),
            float(preregistration["max_time_uncertainty_ms"]),
            float(preregistration["tolerance_ratio"]),
            args.include_samples,
            minimum_quorum=preregistration["minimum_quorum"],
            minimum_independent_runs_per_class=preregistration["minimum_independent_runs_per_class"],
            maximum_95_false_rate_ci_width=float(preregistration["maximum_95_false_rate_ci_width"]),
        )
        report["study_id"] = preregistration["study_id"]
        report["input_artifacts"] = {
            "preregistration": preregistration_artifact,
            "calibration": calibration_artifact,
            "evaluation": evaluation_artifact,
            "meaning": (
                "hashes identify the exact preregistration and CSV bytes and prevent accidental value/run-set "
                "mismatch; they do not prove when the preregistration was created, authenticate data origin, "
                "or establish sensor honesty"
            ),
        }
        serialized = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
        if args.output is None:
            sys.stdout.write(serialized)
        else:
            try:
                _write_private_report(args.output, serialized)
            except FileExistsError:
                parser.error("report already exists; choose a new output path")
            print("Wrote evaluation report to {}".format(args.output))
        return 0
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
