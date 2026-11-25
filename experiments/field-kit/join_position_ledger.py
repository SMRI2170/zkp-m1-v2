"""Conservative private event/position join. Metadata validation is not physical truth."""
import argparse
import collections
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path

from audit_receivers import private_path


def number(v):
    return type(v) in (int, float) and math.isfinite(v)


def epoch(v):
    if not isinstance(v, str):
        return None
    try:
        t = dt.datetime.fromisoformat(v.replace('Z', '+00:00'))
        return t.timestamp() if t.utcoffset() is not None else None
    except (ValueError, OverflowError):
        return None


def point(p):
    return (isinstance(p, dict) and number(p.get('latitude')) and
            number(p.get('longitude')) and -90 <= p['latitude'] <= 90 and
            -180 <= p['longitude'] <= 180)


def horizontal(a, b):
    x, y = math.radians(a['latitude']), math.radians(b['latitude'])
    d = math.radians(b['longitude'] - a['longitude'])
    h = math.sin((y-x)/2)**2 + math.cos(x)*math.cos(y)*math.sin(d/2)**2
    return 6371000 * 2 * math.asin(math.sqrt(min(1, max(0, h))))


def eligible(entry, event):
    """Return reasons; a clock interval must fit wholly inside ledger validity."""
    why = []
    if entry.get('alias') != event.get('alias') or entry.get('run_id') != event.get('run_id'):
        why.append('NODE_OR_RUN_MISMATCH')
    if not event.get('boot_id') or entry.get('boot_id') != event.get('boot_id'):
        why.append('BOOT_MISMATCH_OR_UNKNOWN')
    t, lo, hi = (epoch(event.get('observed_utc')), epoch(entry.get('valid_from_utc')),
                 epoch(entry.get('valid_until_utc')))
    err = event.get('clock_uncertainty_s')
    if not isinstance(event.get('clock_evidence_ref'), str) or not event['clock_evidence_ref'].strip() or not number(err) or err < 0:
        why.append('CLOCK_EVIDENCE_MISSING')
    if t is None or lo is None or hi is None or lo >= hi:
        why.append('INVALID_TIME_RANGE')
    elif number(err) and err >= 0 and not lo <= t-err <= t+err <= hi:
        why.append('OUTSIDE_VALIDITY_WITH_CLOCK_UNCERTAINTY')
    if entry.get('crs') != 'EPSG:4326' or not point(entry):
        why.append('INVALID_POSITION_OR_CRS')
    if not number(entry.get('horizontal_accuracy_m')) or entry['horizontal_accuracy_m'] <= 0:
        why.append('HORIZONTAL_ACCURACY_UNKNOWN')
    if any(not isinstance(entry.get(k), str) or not entry[k].strip() for k in ('method', 'evidence_ref')):
        why.append('POSITION_PROVENANCE_MISSING')
    if type(event.get('moving')) is not bool:
        why.append('MOVEMENT_MODE_UNKNOWN')
    if event.get('moving') is not False:
        # Moving A/phone may never be replaced with a static survey point.
        fix = epoch(entry.get('fix_utc'))
        if entry.get('kind') != 'track_fix' or fix is None or t is None or not number(err) or err < 0 or abs(t-fix)+err > 2:
            why.append('MOVING_FIX_MISSING_OR_STALE')
    elif entry.get('kind') != 'fixed':
        why.append('FIXED_RECORD_REQUIRED')
    return sorted(set(why))


def join_event(event, ledger):
    """Distances are to RID claims, never independent true aircraft positions."""
    candidates = [e for e in ledger if isinstance(e, dict) and
                  e.get('alias') == event.get('alias') and e.get('run_id') == event.get('run_id')]
    valid = [e for e in candidates if not eligible(e, event)]
    r = dict(alias=event.get('alias'), horizontal_distance_m=None, slant_distance_m=None,
             horizontal_uncertainty_sum_m=None, vertical_uncertainty_sum_m=None,
             status='HELD', reasons=[], claim_is_truth=False)
    if not valid:
        r['reasons'] = sorted({x for e in candidates for x in eligible(e, event)}) or ['POSITION_LEDGER_MISSING']
        return r
    if len(valid) != 1:
        r['reasons'] = ['AMBIGUOUS_LEDGER_MATCH']
        return r
    p, q = valid[0], event.get('claim')
    if not point(q):
        r['reasons'] = ['CLAIM_POSITION_MISSING']
        return r
    r['horizontal_distance_m'] = horizontal(p, q)
    r['status'] = 'CLAIM_2D_ONLY'
    qa = q.get('horizontal_accuracy_m')
    if number(qa) and qa > 0:
        r['horizontal_uncertainty_sum_m'] = p['horizontal_accuracy_m'] + qa
    else:
        r['reasons'].append('CLAIM_HORIZONTAL_ACCURACY_UNKNOWN')
    # AGL/local-ground is excluded without an explicit shared ground datum.
    ref = p.get('altitude_reference')
    if (ref not in ('MSL', 'WGS84_ellipsoid') or q.get('altitude_reference') != ref or
            not all(number(x.get('altitude_m')) and number(x.get('vertical_accuracy_m')) and
                    x['vertical_accuracy_m'] > 0 for x in (p, q))):
        r['reasons'].append('ALTITUDE_DATUM_OR_ACCURACY_UNRESOLVED')
        return r
    r['slant_distance_m'] = math.hypot(r['horizontal_distance_m'], p['altitude_m']-q['altitude_m'])
    r['vertical_uncertainty_sum_m'] = p['vertical_accuracy_m'] + q['vertical_accuracy_m']
    r['status'] = 'CLAIM_3D_METADATA_COMPATIBLE'
    return r


def summarize(rows):
    # Explicit allowlist: never publish event values, locations, IDs, times or file paths.
    return dict(schema_version=1, events=len(rows), statuses=dict(collections.Counter(r['status'] for r in rows)),
                hold_or_limit_reasons=dict(collections.Counter(x for r in rows for x in r['reasons'])),
                physical_truth_verified=False, physical_packet_identity_verified=False,
                metadata_only=True, real_fpr_tpr='NOT_EVALUABLE')


def load_private(path):
    path = private_path(path)
    if not path.is_file() or path.stat().st_mode & 0o077:
        raise ValueError('owner-private input required')
    for parent in path.parents:
        if parent == private_path(Path('captures')):
            break
        if parent.stat().st_mode & 0o077:
            raise ValueError('owner-private input directory required')
    return json.loads(path.read_text())


def _run_private(events_path, ledger_path, private_output, public_output):
    # Validate paths before touching them; fail if either input changes mid-run.
    events_path, ledger_path = private_path(events_path), private_path(ledger_path)
    events, ledger = load_private(events_path), load_private(ledger_path)
    before = {k:hashlib.sha256(p.read_bytes()).hexdigest() for k,p in
              [('events', events_path), ('ledger', ledger_path)]}
    if events != load_private(events_path) or ledger != load_private(ledger_path):
        raise ValueError('input changed while loading')
    if not isinstance(events, list) or not isinstance(ledger, list):
        raise ValueError('JSON lists required')
    if any(not isinstance(e, dict) or e.get('alias') not in list('ABCDEF')+['ANDROID'] or
           not isinstance(e.get('run_id'), str) or not e['run_id'] for e in events):
        raise ValueError('invalid event alias/run schema')
    private_output = private_path(private_output)
    if private_output.exists() or public_output.exists():
        raise ValueError('new output directories required')
    private_output.mkdir(parents=True, mode=0o700)
    rows = [join_event(e, ledger) for e in events]
    after = {k:hashlib.sha256(p.read_bytes()).hexdigest() for k,p in
             [('events', events_path), ('ledger', ledger_path)]}
    if before != after:
        raise ValueError('input changed during join')
    receipt = dict(inputs=before, input_unchanged=True)
    (private_output/'joins-private.json').write_text(json.dumps(rows, indent=2)+'\n')
    (private_output/'input-hashes-private.json').write_text(json.dumps(receipt, indent=2)+'\n')
    public_output.mkdir(parents=True)
    summary = summarize(rows)
    (public_output/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    return summary


def run(events_path, ledger_path, private_output, public_output):
    previous = os.umask(0o077)
    try:
        return _run_private(events_path, ledger_path, private_output, public_output)
    finally:
        os.umask(previous)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ('events', 'ledger', 'private-output', 'public-output'):
        p.add_argument('--'+arg, type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(run(a.events, a.ledger, a.private_output, a.public_output)))
