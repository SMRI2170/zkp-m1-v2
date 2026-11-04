"""Offline consistency audit of aggregate-only paired attack evidence."""
import argparse
import collections
import hashlib
import json
import math
from pathlib import Path


def check(out):
    j=json.loads((out/'summary.json').read_text());rows=j['fold_metrics'];aggregates=j['aggregate']
    if len(rows)!=2880 or len(aggregates)!=60:raise ValueError('Unexpected experiment matrix')
    normals=json.loads((Path(__file__).resolve().parents[2]/'week27/results/normal-lora-residuals-20261103-v2/summary.json').read_text())
    if j['source_sha256']!=normals['source_sha256']:raise ValueError('Normal and attack sources differ')
    if j['config']['seed'] is not None:raise ValueError('This paired transform is deterministic')
    groups=collections.defaultdict(list)
    for r in rows:
        groups[(r['condition'],r['fold'],r['direction'],r['claim_horizontal_shift_m'])].append(r)
        if r['eligible_packets']+r['geometry_deferred_packets']!=r['received_packets']:raise ValueError('Cohort accounting')
        if r['eligible_packets']==0:
            if r['alarm_rate'] is not None:raise ValueError('No sample must be deferred')
        elif not (0<=r['alarm_rate']<=1):raise ValueError('Invalid rate')
    for group in groups.values():
        if {r['variant'] for r in group}!=set(j['config']['variants']):raise ValueError('Missing variant')
        for key in ('threshold_db','received_packets','eligible_packets','geometry_deferred_packets','baseline_alarm_rate'):
            if len({r[key] for r in group})!=1:raise ValueError('Unpaired '+key)
        by={r['variant']:r for r in group}
        exact=by['exact_compensation'];normal=by['normal']
        if exact['eligible_packets']:
            if exact['max_score_difference_from_normal_db']>1e-10 or exact['alarm_disagreements']!=0:raise ValueError('Exact cancellation construction failed')
            if exact['alarm_rate']!=normal['alarm_rate']:raise ValueError('Exact alarm mismatch')
    for a in aggregates:
        rs=[r for r in rows if (r['direction'],r['claim_horizontal_shift_m'],r['variant'])==(a['direction'],a['claim_horizontal_shift_m'],a['variant'])]
        valid=[r for r in rs if r['alarm_rate'] is not None]
        if len(valid)!=a['folds_evaluable']:raise ValueError('Fold count')
        if sum(r['eligible_packets'] for r in rs)!=a['eligible_received_packets']:raise ValueError('Sample count')
        for key in ('alarm_rate','baseline_alarm_rate','new_alarms_fraction','lost_alarms_fraction'):
            expected=sum(r[key] for r in valid)/len(valid)
            if not math.isclose(expected,a['mean_'+key],abs_tol=1e-12):raise ValueError('Aggregate mismatch')
        if (a['direction'],a['claim_horizontal_shift_m'],a['variant'])==('outward',100.,'normal'):
            if not math.isclose(a['mean_alarm_rate'],normals['means']['empirical_slope']['normal_alarm_rate'],abs_tol=1e-12):raise ValueError('Normal baseline changed')
    c=j['normalized_score_distribution']['by_variant']
    if c['normal']['mean_fold_cdf']!=c['exact_compensation']['mean_fold_cdf']:raise ValueError('CDF identity')
    for values in c.values():
        curve=values['mean_fold_cdf']
        if not all(0<=v<=1 for v in curve) or any(b<a for a,b in zip(curve,curve[1:])):raise ValueError('Invalid CDF')
    code_hashes=json.loads((out/'code-hashes.json').read_text())
    for filename,digest in code_hashes.items():
        folder='week26-rssi-privacy' if filename=='recheck_lora.py' else 'week27-data-audit'
        file=Path(__file__).resolve().parents[1]/folder/filename
        if hashlib.sha256(file.read_bytes()).hexdigest()!=digest:raise ValueError('Source code differs: '+filename)
    print('Paired evidence: matrix, cohorts, thresholds, cancellation, aggregates, baseline and code hashes verified')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('result',type=Path);check(p.parse_args().result)
