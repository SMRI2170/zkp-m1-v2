#!/usr/bin/env python3
"""Freeze derived horizontal-claim eligibility; private row masks are not physical truth."""
import argparse
import collections
import csv
import hashlib
import json
import math
import os
from pathlib import Path

POLICY = dict(version=1, max_os_accuracy_m=20, max_accuracy_over_claim_distance=.25,
              max_fix_delta_s=2, distance_scope='claimed_horizontal_only',
              independent_truth_verified=False, cross_device_time_verified=False,
              same_physical_transmission_verified=False, vertical_reference_verified=False)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def number(value):
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def reasons(row):
    result = []
    if row.get('quality') != 'ELIGIBLE_TIME_POSITION':
        result.append('UPSTREAM_ASSOCIATION_NOT_ELIGIBLE')
    boot = str(row.get('boot_scope') or '')
    if not boot or boot.startswith('unknown-'):
        result.append('BOOT_UNKNOWN')
    observed = number(row.get('observed_us'))
    if observed is None or observed <= 0:
        result.append('OBSERVATION_TIME_INVALID')
    delta = number(row.get('fix_delta_s'))
    if delta is None or not 0 <= delta <= POLICY['max_fix_delta_s']:
        result.append('FIX_TIME_DELTA_INVALID')
    accuracy = number(row.get('accuracy_m'))
    distance = number(row.get('claimed_horizontal_distance_m'))
    if accuracy is None or not 0 <= accuracy <= POLICY['max_os_accuracy_m']:
        result.append('OS_ACCURACY_OUTSIDE_POLICY')
    if distance is None or distance <= 0:
        result.append('CLAIM_DISTANCE_INVALID')
    elif accuracy is not None and accuracy / distance > POLICY['max_accuracy_over_claim_distance']:
        result.append('ACCURACY_TO_CLAIM_DISTANCE_TOO_LARGE')
    if number(row.get('rssi_dbm')) is None:
        result.append('RSSI_INVALID')
    return result


def build(rows, positions, intervals, distance):
    expected = positions['nodes']
    if any(row.get('node') not in expected for row in rows):
        raise ValueError('Unrecognized node in derived rows')
    masks = []
    public = {}
    for node, evidence in expected.items():
        group = [(i, r) for i, r in enumerate(rows) if r['node'] == node]
        if len(group) != evidence['target_rows'] or intervals['nodes'][node]['saved_rows'] != len(group):
            raise ValueError('Upstream target denominators disagree')
        if not evidence['input_unchanged'] or not intervals['nodes'][node]['input_unchanged']:
            raise ValueError('Upstream input verification failed')
        counts = collections.Counter()
        held = collections.Counter()
        for i, row in group:
            why = reasons(row)
            masks.append(dict(row_index=i, selected=not why, reasons=why))
            counts.update(why[:1])  # Exclusive first reason; denominator is held rows.
            held.update(why)       # Nonexclusive diagnostics; never sum as a denominator.
        selected = sum(x['selected'] for x in masks if x['row_index'] in {i for i, _ in group})
        # A manifest must reproduce, rather than silently change, the existing gate.
        old_selected = distance['nodes'].get(node, {}).get('retained_rows', 0)
        if selected != old_selected:
            raise ValueError('Selection differs from existing distance analysis; investigate before adoption')
        public[node] = dict(target_rows=len(group), selected_rows=selected,
                            held_rows=len(group)-selected, exclusive_hold_reasons=dict(counts),
                            nonexclusive_hold_reasons=dict(held),
                            observation_keys=intervals['nodes'][node]['observation_keys'],
                            distinct_pack_contents=intervals['nodes'][node]['distinct_pack_contents'])
    masks.sort(key=lambda x: x['row_index'])
    return masks, public


def private_path(path, *, existing=False):
    p = Path(path).absolute()
    root = Path(__file__).resolve().parents[2] / 'captures'
    if not p.is_relative_to(root) or any(x.is_symlink() for x in [p, *p.parents]):
        raise ValueError('Private artifacts must stay under nonsymlink captures/')
    if existing and (not p.is_file() or p.stat().st_mode & 0o077):
        raise ValueError('Owner-private input file required')
    return p


def load_selection(manifest, positions, rows):
    p = private_path(manifest, existing=True)
    m = json.loads(p.read_text())
    if m['format'] != 'week29_quality_mask_v1' or m['policy'] != POLICY:
        raise ValueError('Unsupported selection policy')
    if digest(positions) != m['position_csv_sha256']:
        raise ValueError('Position input no longer matches frozen selection')
    expected = [dict(row_index=i, selected=not reasons(r), reasons=reasons(r)) for i, r in enumerate(rows)]
    if m['rows'] != expected:
        raise ValueError('Selection mask is inconsistent with policy/input')
    return [r for r, mask in zip(rows, expected) if mask['selected']]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--private-output', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    config = json.loads(private_path(args.config, existing=True).read_text())
    paths = {k: Path(v) for k, v in config.items()}
    private_path(paths['positions'], existing=True)
    hashes = {k: digest(p) for k, p in paths.items()}
    documents = {k: json.loads(p.read_text()) for k, p in paths.items() if k != 'positions'}
    distance = documents['distance_summary']
    if distance['source_sha256'] != hashes['positions'] or not distance['input_unchanged']:
        raise ValueError('Existing distance analysis is not bound to this position input')
    source_inputs = documents['source_inputs']
    for source in source_inputs:
        if digest(private_path(source['path'], existing=True)) != source['sha256']:
            raise ValueError('Original source DB changed since position audit')
    with paths['positions'].open() as f:
        rows = list(csv.DictReader(f))
    masks, nodes = build(rows, documents['position_summary'], documents['interval_summary'], distance)
    if any(digest(p) != hashes[k] for k, p in paths.items()):
        raise ValueError('Evidence changed during manifest construction')
    private = private_path(args.private_output)
    if private.exists() or args.output.exists():
        raise ValueError('Fresh output directories required')
    private.mkdir(parents=True, mode=0o700)
    args.output.mkdir(parents=True)
    frozen = dict(format='week29_quality_mask_v1', policy=POLICY,
                  position_csv_sha256=hashes['positions'], rows=masks,
                  evidence=[dict(role=k, path=str(p), sha256=hashes[k]) for k,p in paths.items()],
                  source_database_hashes_verified=len(source_inputs))
    (private/'selection-private.json').write_text(json.dumps(frozen, indent=2)+'\n')
    summary = dict(format='week29_quality_summary_v1', policy=POLICY, nodes=nodes,
                   target_rows=len(rows), selected_rows=sum(x['selected'] for x in masks),
                   source_database_hashes_verified=len(source_inputs),
                   upstream_calendar_anchors_verified=documents['clock_summary']['independent_calendar_anchors_verified'],
                   cross_device_synchronization='NOT_EVALUABLE_independent_time_not_verified',
                   same_transmission_drss='NOT_EVALUABLE_same_physical_transmission_not_verified',
                   slant_distance='NOT_EVALUABLE_vertical_reference_not_verified',
                   physical_accuracy='NOT_EVALUABLE_independent_truth_not_available',
                   code_sha256=digest(Path(__file__)), input_unchanged=True)
    (args.output/'manifest.json').write_text(json.dumps(summary, indent=2)+'\n')
    with (args.output/'selection-counts.csv').open('x', newline='') as f:
        w=csv.DictWriter(f, fieldnames=['node','target_rows','selected_rows','held_rows'])
        w.writeheader()
        w.writerows(dict(node=n, **{k:v[k] for k in ['target_rows','selected_rows','held_rows']}) for n,v in nodes.items())
    print(json.dumps(dict(target_rows=summary['target_rows'], selected_rows=summary['selected_rows'], nodes=nodes)))


if __name__ == '__main__':
    main()
