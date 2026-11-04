"""Check saved sensitivity CSVs/summary against prior paired evidence, offline."""
import argparse
import collections
import csv
import hashlib
import json
import math
from pathlib import Path


def close(a,b):
    if not math.isclose(float(a),float(b),rel_tol=1e-10,abs_tol=1e-12):raise ValueError(f'Numeric mismatch: {a} / {b}')


def rows_at(root,key):
    with (root/(key+'-fold.csv')).open() as stream:
        return [{k:(None if v=='' else v if k in ('condition','variant') else float(v)) for k,v in row.items()} for row in csv.DictReader(stream)]


def audit(root):
    j=json.loads((root/'summary.json').read_text());basepath=Path(__file__).resolve().parents[2]
    prior=json.loads((basepath/'week27/results/paired-attacks-20261103-v2/summary.json').read_text())
    if j['source_sha256']!=prior['source_sha256']:raise ValueError('Source mismatch')
    expected={'absolute_exponent':8832,'relative_exponent':5952,'power_cap':2496,'joint':19344,'temporal':240,'n2_explanation':48}
    if j['fold_row_counts']!=expected:raise ValueError('Sweep counts differ')
    reference={}
    for key,keys in [('absolute_exponent',['shift_m','attacker_n']),('relative_exponent',['shift_m','n_ratio']),('power_cap',['shift_m','cap_db']),('joint',['n_ratio','cap_db'])]:
        data=rows_at(root,key)
        if len(data)!=expected[key]:raise ValueError('CSV row count')
        grouped=collections.defaultdict(list)
        for row in data:
            if not 0<=row['alarm_rate']<=1:raise ValueError('Invalid probability')
            cohort=(row['condition'],row['fold'])
            common=tuple(row[k] for k in ('training_run','calibration_run','evaluation_run','received_packets','threshold_db','baseline_alarm_rate'))
            if cohort in reference and reference[cohort]!=common:raise ValueError('Cohort/calibration changed')
            reference[cohort]=common
            if len({row['training_run'],row['calibration_run'],row['evaluation_run']})!=3:raise ValueError('Run leakage')
            grouped[tuple(row[k] for k in keys)].append(row)
        if len(grouped)!=len(j['aggregates'][key]):raise ValueError('Missing aggregate')
        for aggregate in j['aggregates'][key]:
            subset=grouped[tuple(aggregate[k] for k in keys)]
            if len(subset)!=48 or len({(r['condition'],r['fold']) for r in subset})!=48:raise ValueError('Fold missing or repeated')
            close(sum(r['received_packets'] for r in subset),aggregate['received_packets'])
            for field in ('alarm_rate','baseline_alarm_rate','mean_signed_shift_db','rms_shift_db'):
                target=field if field=='mean_signed_shift_db' else 'mean_'+field
                close(sum(r[field] for r in subset)/len(subset),aggregate[target])
            close((aggregate['mean_alarm_rate']-aggregate['mean_baseline_alarm_rate'])*100,aggregate['mean_excess_alarm_pp'])
            by_condition=collections.defaultdict(list)
            for row in subset:by_condition[row['condition']].append(row['alarm_rate'])
            means=[sum(values)/len(values) for values in by_condition.values()]
            close(min(means),aggregate['condition_mean_alarm_min']);close(max(means),aggregate['condition_mean_alarm_max'])
    for key,field,value,variant in [('absolute_exponent','attacker_n',2.,'mismatched_n2'),('relative_exponent','n_ratio',1.,'exact_compensation'),('power_cap','cap_db',3.,'bounded_3db'),('power_cap','cap_db',0.,'position_only'),('power_cap','cap_db',None,'exact_compensation')]:
        for r in j['aggregates'][key]:
            if r[field]==value:
                old=next(a for a in prior['aggregate'] if a['direction']=='outward' and a['claim_horizontal_shift_m']==r['shift_m'] and a['variant']==variant)
                close(r['mean_alarm_rate'],old['mean_alarm_rate'])
    for r in j['aggregates']['joint']:
        if r['cap_db']==0:
            old=next(a for a in prior['aggregate'] if a['direction']=='outward' and a['claim_horizontal_shift_m']==100 and a['variant']=='position_only')
            close(r['mean_alarm_rate'],old['mean_alarm_rate'])
        if r['cap_db'] is None and r['n_ratio']==1.:close(r['mean_alarm_rate'],r['mean_baseline_alarm_rate'])
    n2=rows_at(root,'n2_explanation')
    for r in n2:
        close(r['mean_signed_shift_db'],10*(r['detector_n']-2.)*r['log_range_ratio_mean'])
        close(r['baseline_alarm_rate']+r['new_alarm_fraction']-r['lost_alarm_fraction'],r['alarm_rate'])
        close(r['attacked_residual_mean_db']-r['baseline_residual_mean_db'],r['mean_signed_shift_db'])
    temporal=rows_at(root,'temporal')
    for r in temporal:
        if not 0<=r['episodes']<=r['alarm_packets']<=r['received_packets']:raise ValueError('Episode accounting')
        if r['window_threshold_db'] is None and r['window_median_alarm_rate'] is not None:raise ValueError('Missing window calibration')
    for r in j['aggregates']['temporal']:
        subset=[x for x in temporal if x['variant']==r['variant']]
        for source,target in [('episodes','total_episodes'),('alarm_packets','total_alarm_packets'),('evaluation_complete_windows','total_evaluation_windows')]:close(sum(x[source] for x in subset),r[target])
        close(sum(x['packet_alarm_rate'] for x in subset)/len(subset),r['mean_packet_alarm_rate'])
        valid=[x for x in subset if x['window_median_alarm_rate'] is not None]
        close(sum(x['window_median_alarm_rate'] for x in valid)/len(valid),r['mean_window_median_alarm_rate'])
    if len(reference)!=48:raise ValueError('Expected 48 shared evaluation cohorts')
    for condition,fold in reference:
        subgroup=[r for r in temporal if r['condition']==condition and r['fold']==fold]
        for field in ('calibration_complete_windows','evaluation_complete_windows','window_threshold_db'):
            if len({r[field] for r in subgroup})!=1:raise ValueError('Temporal cohort/calibration changed')
        normal=next(r for r in temporal if r['condition']==condition and r['fold']==fold and r['variant']=='normal')
        exact=next(r for r in temporal if r['condition']==condition and r['fold']==fold and r['variant']=='exact_compensation')
        for field in ('packet_alarm_rate','episodes','alarm_packets','window_median_alarm_rate'):close(normal[field],exact[field])
    hashes=json.loads((root/'code-hashes.json').read_text())
    for name,digest in hashes.items():
        folder='week26-rssi-privacy' if name=='recheck_lora.py' else 'week27-data-audit'
        file=basepath/'experiments'/folder/name
        if hashlib.sha256(file.read_bytes()).hexdigest()!=digest:raise ValueError('Source changed: '+name)
    print('Sensitivity evidence verified: all CSV/aggregate values, prior anchors, paired cohorts, n-error equation, windows/episodes and code hashes')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('result',type=Path);audit(p.parse_args().result)
