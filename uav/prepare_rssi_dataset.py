#!/usr/bin/env python3
"""Normalize protected BLE capture logs plus independent truth windows for RSSI evaluation.

This joins only opaque per-run UAS tags and timestamps. It does not authenticate
the transmitter, observer, RSSI, or coordinates; the generated CSV is only as
reliable as its separately maintained ground-truth ledger.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import re
import statistics
import stat
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

from evaluate_rssi import local_distance_m


WINDOW_FIELDS = (
    "sample_id",
    "decision_window_id",
    "run_id",
    "observer_id",
    "calibration_profile_id",
    "uas_id_tag",
    "window_start_unix_ms",
    "window_end_unix_ms",
    "time_uncertainty_ms",
    "observer_lat_deg",
    "observer_lon_deg",
    "observer_alt_m",
    "truth_lat_deg",
    "truth_lon_deg",
    "truth_alt_m",
)
CALIBRATION_OUTPUT_FIELDS = (
    "sample_id", "decision_window_id", "run_id", "observer_id", "calibration_profile_id",
    "true_range_m", "rssi_dbm_median", "capture_observation_count",
    "location_packet_count", "window_duration_ms",
    "time_uncertainty_ms",
    "capture_set_sha256", "truth_windows_sha256",
)
EVALUATION_OUTPUT_FIELDS = (
    "sample_id", "decision_window_id", "run_id", "observer_id", "calibration_profile_id",
    "observer_lat_deg", "observer_lon_deg", "observer_alt_m",
    "advertised_lat_deg", "advertised_lon_deg", "advertised_alt_m",
    "truth_lat_deg", "truth_lon_deg", "truth_alt_m", "rssi_dbm_median",
    "capture_observation_count", "location_packet_count", "window_duration_ms",
    "time_uncertainty_ms",
    "capture_set_sha256", "truth_windows_sha256",
)
OPAQUE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
UAS_TAG = re.compile(r"[0-9a-f]{24}\Z")


@dataclass(frozen=True)
class TruthWindow:
    sample_id: str
    decision_window_id: str
    run_id: str
    observer_id: str
    profile_id: int
    uas_id_tag: str
    start_ms: int
    end_ms: int
    time_uncertainty_ms: float
    observer: Tuple[float, float, float]
    truth: Tuple[float, float, float]


@dataclass(frozen=True)
class CaptureLog:
    profile_id: int
    tag_scope: str
    observations: List[Dict[str, Any]]
    source_sha256: str


def _open_private_input(path: Path, label: str, encoding: str | None, newline: str | None = None):
    nofollow = getattr(os, "O_NOFOLLOW", None)
    if nofollow is None:
        raise ValueError("{}: this platform cannot safely reject symlinked input files".format(label))
    try:
        fd = os.open(str(path), os.O_RDONLY | nofollow)
    except OSError as exc:
        raise ValueError("cannot safely open {} {}: {}".format(label, path, exc)) from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("{} must be a regular file".format(label))
        if hasattr(os, "geteuid") and info.st_uid != os.geteuid():
            raise ValueError("{} must be owned by the current user".format(label))
        mode = info.st_mode & 0o777
        if mode & 0o077 or not mode & 0o400:
            raise ValueError("{} must be owner-readable and no broader than mode 0600".format(label))
        if encoding is None:
            return os.fdopen(fd, "rb")
        return os.fdopen(fd, "r", encoding=encoding, newline=newline)
    except Exception:
        os.close(fd)
        raise


def _finite(row: Mapping[str, str], field: str, row_number: int) -> float:
    raw = row.get(field)
    if raw is None or not raw.strip():
        raise ValueError("truth row {}: missing {}".format(row_number, field))
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("truth row {}: {} must be numeric".format(row_number, field)) from exc
    if not math.isfinite(value):
        raise ValueError("truth row {}: {} must be finite".format(row_number, field))
    return value


def _opaque(row: Mapping[str, str], field: str, row_number: int) -> str:
    value = (row.get(field) or "").strip()
    if not OPAQUE_ID.fullmatch(value):
        raise ValueError("truth row {}: {} must be a bounded opaque ASCII ID".format(row_number, field))
    return value


def _coordinate(row: Mapping[str, str], field: str, row_number: int, minimum: float, maximum: float) -> float:
    value = _finite(row, field, row_number)
    if not minimum <= value <= maximum:
        raise ValueError("truth row {}: {} is outside valid bounds".format(row_number, field))
    return value


def _timestamp_ms(row: Mapping[str, str], field: str, row_number: int) -> int:
    raw = (row.get(field) or "").strip()
    if not re.fullmatch(r"(?:0|[1-9][0-9]*)", raw):
        raise ValueError("truth row {}: {} must be a canonical nonnegative integer".format(row_number, field))
    return int(raw)


def read_truth_windows(path: Path) -> Tuple[List[TruthWindow], str]:
    try:
        source = _open_private_input(path, "truth windows CSV", None)
    except (OSError, ValueError) as exc:
        raise ValueError("cannot open truth windows {}: {}".format(path, exc)) from exc

    with source:
        raw = source.read()
    try:
        decoded = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("truth windows CSV must be UTF-8") from exc
    truth_sha256 = hashlib.sha256(raw).hexdigest()
    windows: List[TruthWindow] = []
    with io.StringIO(decoded, newline="") as text_source:
        reader = csv.DictReader(text_source)
        if reader.fieldnames is None:
            raise ValueError("truth windows CSV header is missing")
        missing = [field for field in WINDOW_FIELDS if field not in reader.fieldnames]
        if missing:
            raise ValueError("truth windows CSV is missing columns: {}".format(", ".join(missing)))
        seen_samples = set()
        intervals: Dict[Tuple[str, str, str], List[Tuple[int, int, int]]] = defaultdict(list)
        decision_groups: Dict[Tuple[str, str], Dict[str, Any]] = {}
        for row_number, row in enumerate(reader, start=2):
            sample_id = _opaque(row, "sample_id", row_number)
            decision_window_id = _opaque(row, "decision_window_id", row_number)
            run_id = _opaque(row, "run_id", row_number)
            observer_id = _opaque(row, "observer_id", row_number)
            if sample_id in seen_samples:
                raise ValueError("truth row {}: duplicate sample_id {}".format(row_number, sample_id))
            seen_samples.add(sample_id)

            raw_profile = (row.get("calibration_profile_id") or "").strip()
            if not re.fullmatch(r"(?:0|[1-9][0-9]*)", raw_profile) or int(raw_profile) > 0xFFFFFFFF:
                raise ValueError("truth row {}: calibration_profile_id must be a canonical uint32".format(row_number))
            tag = (row.get("uas_id_tag") or "").strip()
            if not UAS_TAG.fullmatch(tag):
                raise ValueError("truth row {}: uas_id_tag must be the 24-character capture pseudonym".format(row_number))
            start_ms = _timestamp_ms(row, "window_start_unix_ms", row_number)
            end_ms = _timestamp_ms(row, "window_end_unix_ms", row_number)
            if end_ms <= start_ms:
                raise ValueError("truth row {}: window_end_unix_ms must be after start".format(row_number))
            time_uncertainty_ms = _finite(row, "time_uncertainty_ms", row_number)
            if time_uncertainty_ms < 0:
                raise ValueError("truth row {}: time_uncertainty_ms must be nonnegative".format(row_number))
            if time_uncertainty_ms >= end_ms - start_ms:
                raise ValueError("truth row {}: time uncertainty must be smaller than the window".format(row_number))

            observer = (
                _coordinate(row, "observer_lat_deg", row_number, -90.0, 90.0),
                _coordinate(row, "observer_lon_deg", row_number, -180.0, 180.0),
                _finite(row, "observer_alt_m", row_number),
            )
            truth = (
                _coordinate(row, "truth_lat_deg", row_number, -90.0, 90.0),
                _coordinate(row, "truth_lon_deg", row_number, -180.0, 180.0),
                _finite(row, "truth_alt_m", row_number),
            )
            group_key = (run_id, decision_window_id)
            group = decision_groups.get(group_key)
            if group is None:
                decision_groups[group_key] = {
                    "uas_id_tag": tag,
                    "common_start_ms": start_ms,
                    "common_end_ms": end_ms,
                    "observers": {observer_id},
                }
            else:
                if group["uas_id_tag"] != tag:
                    raise ValueError(
                        "truth row {}: decision window {} maps to different uas_id_tag values".format(
                            row_number, decision_window_id
                        )
                    )
                if observer_id in group["observers"]:
                    raise ValueError(
                        "truth row {}: decision window {} repeats observer {}".format(
                            row_number, decision_window_id, observer_id
                        )
                    )
                common_start = max(group["common_start_ms"], start_ms)
                common_end = min(group["common_end_ms"], end_ms)
                if common_end <= common_start:
                    raise ValueError(
                        "truth row {}: decision window {} has no common time overlap".format(
                            row_number, decision_window_id
                        )
                    )
                group["common_start_ms"] = common_start
                group["common_end_ms"] = common_end
                group["observers"].add(observer_id)
            window = TruthWindow(sample_id, decision_window_id, run_id, observer_id, int(raw_profile), tag,
                                 start_ms, end_ms, time_uncertainty_ms, observer, truth)
            windows.append(window)
            intervals[(run_id, observer_id, tag)].append((start_ms, end_ms, row_number))

    if not windows:
        raise ValueError("truth windows CSV has no data rows")
    for key, entries in intervals.items():
        entries.sort()
        for previous, current in zip(entries, entries[1:]):
            if current[0] < previous[1]:
                raise ValueError(
                    "truth windows rows {} and {} overlap for run/observer/tag {}".format(
                        previous[2], current[2], "/".join(key)
                    )
                )
    return windows, truth_sha256


def _load_capture_file(path: Path) -> Tuple[Tuple[str, str], CaptureLog]:
    records: List[Dict[str, Any]] = []
    digest = hashlib.sha256()
    try:
        source = _open_private_input(path, "capture JSONL", None)
    except (OSError, ValueError) as exc:
        raise ValueError("cannot open capture {}: {}".format(path, exc)) from exc
    with source:
        for line_number, line in enumerate(source, start=1):
            digest.update(line)
            try:
                record = json.loads(line)
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                message = exc.msg if isinstance(exc, json.JSONDecodeError) else "invalid UTF-8"
                raise ValueError("{}:{}: invalid JSON: {}".format(path, line_number, message)) from exc
            if not isinstance(record, dict) or record.get("schema") != "signal.observer-capture.v1":
                raise ValueError("{}:{}: unsupported capture schema".format(path, line_number))
            records.append(record)

    starts = [record for record in records if record.get("record_type") == "capture_start"]
    ends = [record for record in records if record.get("record_type") == "capture_end"]
    if len(starts) != 1 or len(ends) != 1:
        raise ValueError("{}: require exactly one capture_start and capture_end".format(path))
    if any(record.get("record_type") == "capture_error" for record in records):
        raise ValueError("{}: capture contains capture_error; incomplete data is not evaluated".format(path))
    start = starts[0]
    identity_fields = ("run_id", "observer_id", "calibration_profile_id", "uas_id_tag_scope")
    identity = tuple(start.get(field) for field in identity_fields)
    if (not isinstance(identity[0], str) or not OPAQUE_ID.fullmatch(identity[0])
            or not isinstance(identity[1], str) or not OPAQUE_ID.fullmatch(identity[1])
            or not isinstance(identity[2], int) or isinstance(identity[2], bool)
            or not 0 <= identity[2] <= 0xFFFFFFFF
            or identity[3] not in ("shared_session_key_and_run_id", "process_local_key_and_run_id")):
        raise ValueError("{}: invalid capture identity metadata".format(path))

    observations = []
    event_metadata: Dict[int, Tuple[int, int, Any]] = {}
    last_event_seq = 0
    event_sequence_records = 0
    for record in records:
        record_type = record.get("record_type")
        if record_type not in ("capture_start", "capture_end", "observation"):
            raise ValueError("{}: unknown capture record type {!r}".format(path, record_type))
        if tuple(record.get(field) for field in identity_fields) != identity:
            raise ValueError("{}: capture identity changes within the file".format(path))
        if record_type != "observation":
            continue
        timestamp = record.get("captured_at_unix_ms")
        rssi = record.get("rssi_dbm")
        if (not isinstance(timestamp, int) or isinstance(timestamp, bool) or timestamp < 0
                or not isinstance(rssi, int) or isinstance(rssi, bool) or not -200 <= rssi <= 50):
            raise ValueError("{}: observation has invalid timestamp or RSSI".format(path))
        event_seq = record.get("capture_event_seq")
        if event_seq is not None:
            event_sequence_records += 1
            if (not isinstance(event_seq, int) or isinstance(event_seq, bool)
                    or event_seq < 1 or event_seq < last_event_seq):
                raise ValueError("{}: invalid or out-of-order capture_event_seq".format(path))
            last_event_seq = event_seq
            event_fingerprint = (timestamp, rssi, record.get("advertiser_tag"))
            previous = event_metadata.get(event_seq)
            if previous is not None and previous != event_fingerprint:
                raise ValueError("{}: capture event has inconsistent time, RSSI, or advertiser".format(path))
            event_metadata[event_seq] = event_fingerprint
        observations.append(record)
    declared_count = ends[0].get("captured")
    if not isinstance(declared_count, int) or isinstance(declared_count, bool) or declared_count != len(observations):
        raise ValueError("{}: capture_end count does not match observation records".format(path))
    if event_sequence_records not in (0, len(observations)):
        raise ValueError("{}: capture_event_seq must be present on all or no observations".format(path))
    declared_event_count = ends[0].get("capture_event_count")
    if declared_event_count is not None:
        if (not isinstance(declared_event_count, int) or isinstance(declared_event_count, bool)
                or event_sequence_records != len(observations)
                or declared_event_count != len(event_metadata)):
            raise ValueError("{}: capture_end event count does not match observation events".format(path))
    return (identity[0], identity[1]), CaptureLog(
        identity[2], identity[3], observations, digest.hexdigest()
    )


def load_captures(paths: Sequence[Path]) -> Dict[Tuple[str, str], CaptureLog]:
    if not paths:
        raise ValueError("at least one capture JSONL file is required")
    captures: Dict[Tuple[str, str], CaptureLog] = {}
    seen_nodes = set()
    seen_files = set()
    for path in paths:
        resolved = path.resolve()
        if resolved in seen_files:
            raise ValueError("capture file was supplied more than once: {}".format(path))
        seen_files.add(resolved)
        (run_id, observer_id), capture = _load_capture_file(path)
        node_key = (run_id, observer_id)
        if node_key in seen_nodes:
            raise ValueError("multiple capture files for the same run/observer: {}/{}".format(*node_key))
        seen_nodes.add(node_key)
        captures[node_key] = capture
    return captures


def _median_field(records: Iterable[Mapping[str, Any]], field: str) -> float:
    values = [float(record[field]) for record in records]
    return float(statistics.median(values))


def _one_rssi_sample_per_capture_event(
    records: Sequence[Mapping[str, Any]],
) -> List[Mapping[str, Any]]:
    """Avoid weighting an RSSI event multiple times for packed RID messages.

    Legacy logs lack `capture_event_seq` and keep the previous one-row/one-event
    interpretation. Current logs assign the same event sequence to all messages
    decoded from one BLE advertisement.
    """
    unique: List[Mapping[str, Any]] = []
    seen = set()
    for index, record in enumerate(records):
        event_seq = record.get("capture_event_seq")
        key = ("event", event_seq) if event_seq is not None else ("legacy-row", index)
        if key not in seen:
            seen.add(key)
            unique.append(record)
    return unique


def prepare_rows(
    windows: Sequence[TruthWindow],
    captures: Mapping[Tuple[str, str], CaptureLog],
    mode: str,
) -> List[Dict[str, Any]]:
    if mode not in ("calibration", "evaluation"):
        raise ValueError("mode must be calibration or evaluation")
    output: List[Dict[str, Any]] = []
    for window in windows:
        capture = captures.get((window.run_id, window.observer_id))
        if capture is None:
            raise ValueError("no capture for truth sample {} run/observer".format(window.sample_id))
        if capture.profile_id != window.profile_id:
            raise ValueError("truth sample {} calibration profile does not match capture".format(window.sample_id))
        matching = [
            record for record in capture.observations
            if record.get("uas_id_tag") == window.uas_id_tag
            and window.start_ms <= record.get("captured_at_unix_ms", -1) < window.end_ms
        ]
        if not matching:
            raise ValueError("truth sample {} has no matching tagged RSSI observations".format(window.sample_id))
        location_records = [record for record in matching if record.get("message_type") == "location"]
        if not location_records:
            raise ValueError("truth sample {} has no matching Remote ID Location packet".format(window.sample_id))
        rssi_events = _one_rssi_sample_per_capture_event(matching)
        for record in location_records:
            for field in ("latitude_deg", "longitude_deg", "altitude_geo_m"):
                if record.get(field) is None:
                    raise ValueError("truth sample {}: Location packet is missing {}".format(window.sample_id, field))
                try:
                    value = float(record[field])
                except (TypeError, ValueError) as exc:
                    raise ValueError("truth sample {}: invalid Location {}".format(window.sample_id, field)) from exc
                if not math.isfinite(value):
                    raise ValueError("truth sample {}: non-finite Location {}".format(window.sample_id, field))
        advertised_lat = _median_field(location_records, "latitude_deg")
        advertised_lon = _median_field(location_records, "longitude_deg")
        advertised_alt = _median_field(location_records, "altitude_geo_m")
        for axis, value, bound in (("latitude", advertised_lat, 90), ("longitude", advertised_lon, 180)):
            if not -bound <= value <= bound:
                raise ValueError("truth sample {}: advertised {} is out of bounds".format(window.sample_id, axis))

        row: Dict[str, Any] = {
            "sample_id": window.sample_id,
            "decision_window_id": window.decision_window_id,
            "run_id": window.run_id,
            "observer_id": window.observer_id,
            "calibration_profile_id": window.profile_id,
            "rssi_dbm_median": _median_field(rssi_events, "rssi_dbm"),
            "capture_observation_count": len(rssi_events),
            "location_packet_count": len(location_records),
            "window_duration_ms": window.end_ms - window.start_ms,
            "time_uncertainty_ms": window.time_uncertainty_ms,
        }
        if mode == "calibration":
            row["true_range_m"] = local_distance_m(window.observer, window.truth)
        else:
            row.update({
                "observer_lat_deg": window.observer[0],
                "observer_lon_deg": window.observer[1],
                "observer_alt_m": window.observer[2],
                "advertised_lat_deg": advertised_lat,
                "advertised_lon_deg": advertised_lon,
                "advertised_alt_m": advertised_alt,
                "truth_lat_deg": window.truth[0],
                "truth_lon_deg": window.truth[1],
                "truth_alt_m": window.truth[2],
            })
        output.append(row)
    return output


def write_private_csv(path: Path, rows: Sequence[Mapping[str, Any]], fields: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(str(path), flags, 0o600)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as destination:
            writer = csv.DictWriter(destination, fieldnames=fields, extrasaction="raise")
            writer.writeheader()
            writer.writerows(rows)
    except Exception:
        # The file was created exclusively by this invocation. Remove only this
        # partial output so a failed normalization cannot look complete.
        try:
            path.unlink()
        except OSError:
            pass
        raise


def capture_set_sha256(captures: Mapping[Tuple[str, str], CaptureLog]) -> str:
    content_hashes = sorted(capture.source_sha256 for capture in captures.values())
    envelope = b"signal.observer-capture-set.v1\x00" + json.dumps(
        content_hashes, separators=(",", ":")
    ).encode("ascii")
    return hashlib.sha256(envelope).hexdigest()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build private RSSI calibration/evaluation CSV from capture JSONL and independent truth windows."
    )
    parser.add_argument("--captures", required=True, nargs="+", type=Path,
                        help="one completed observer_capture.py JSONL file per run/observer")
    parser.add_argument("--truth-windows", required=True, type=Path,
                        help="separately maintained CSV with independent surveyed observer/aircraft positions")
    parser.add_argument("--mode", required=True, choices=("calibration", "evaluation"))
    parser.add_argument("--output", required=True, type=Path,
                        help="new mode-0600 CSV; existing files are never overwritten")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        windows, truth_hash = read_truth_windows(args.truth_windows)
        captures = load_captures(args.captures)
        rows = prepare_rows(windows, captures, args.mode)
        capture_hash = capture_set_sha256(captures)
        for row in rows:
            row["capture_set_sha256"] = capture_hash
            row["truth_windows_sha256"] = truth_hash
        fields = CALIBRATION_OUTPUT_FIELDS if args.mode == "calibration" else EVALUATION_OUTPUT_FIELDS
        write_private_csv(args.output, rows, fields)
        print("Wrote {} {} windows to {} (mode 0600).".format(len(rows), args.mode, args.output))
        return 0
    except (OSError, ValueError, csv.Error) as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
