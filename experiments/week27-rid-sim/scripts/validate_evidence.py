"""Offline integrity checks for public aggregates; this never runs RF simulation."""
import argparse
import csv
import json
import math
from pathlib import Path

from evaluation import metrics,split_check


def read_csv(path):
    with path.open() as stream:return list(csv.DictReader(stream))


def validate(root):
    cfg=json.loads((root/'configuration.json').read_text())
    summary=json.loads((root/'summary.json').read_text())
    if summary['status']!='PR4_EVALUATION_PASSED':raise ValueError('Evaluation did not pass')
    split_check(cfg['train_seeds'],cfg['calibration_seeds'],cfg['evaluation_seeds'])
    if len(cfg['evaluation_seeds'])<20:raise ValueError('Full evidence needs at least 20 independent evaluation seeds')
    receipts=json.loads((root/'case-receipts.json').read_text())
    expected=2+len(cfg['models'])*len(cfg['links'])*(len(cfg['calibration_seeds'])+len(cfg['evaluation_seeds'])*len(cfg['offsets_m']))
    if cfg['include_risk']:expected+=1+2*len(cfg['calibration_seeds'])+4*len(cfg['evaluation_seeds'])
    if len(receipts)!=expected:raise ValueError('Configured scene matrix is incomplete')
    if len({r['run_id'] for r in receipts})!=len(receipts):raise ValueError('Duplicate scene receipt')
    if summary['completed_scenes']!=len(receipts):raise ValueError('Completed scene accounting mismatch')
    if any(r['exit_code']!=0 or r['tx_count']!=r['phy_tx_count'] for r in receipts):raise ValueError('Unsuccessful PHY execution included')
    if sum(r['tx_count'] for r in receipts)!=summary['total_actual_tx']:raise ValueError('TX accounting mismatch')
    if sum(r['received'] for r in receipts)!=summary['total_received']:raise ValueError('RX accounting mismatch')
    for row in receipts:
        spec=row['spec']
        if spec['count']!=row['tx_count']:raise ValueError('Schedule count mismatch')
        if not math.isclose(row['last_tx_time_s']-row['first_tx_time_s'],(spec['count']-1)*spec['gap_s'],abs_tol=1e-8):raise ValueError('Time spacing mismatch')
        if '-train-' in row['run_id'] or '-cal-' in row['run_id']:
            if spec['offset_x_m']!=0:raise ValueError('Attack entered training or calibration')
        if not (root/'logs'/f'{row["run_id"]}.log').exists():raise ValueError('Execution log missing')
    seeds=set(cfg['evaluation_seeds']);groups={};group_rows={}
    rows=read_csv(root/'per-seed-metrics.csv')
    for r in rows:
        flags=int(r['flag_count']);below=int(r['below_count']);und=int(r['und_count']);total=int(r['tx_count']);received=int(r['received_count']);scored=int(r['scored_count'])
        if flags+below+und!=total or scored!=flags+below or not scored<=received<=total:raise ValueError('Invalid metric denominator')
        reference=metrics(['FLAG']*flags+['BELOW_THRESHOLD']*below+['UNDETERMINED']*und,[True]*received+[False]*(total-received))
        for key,value in reference.items():
            if value is None:
                if r[key]!='':raise ValueError('Undefined rate was turned into a numeric score')
            elif not math.isclose(float(r[key]),value,abs_tol=1e-12):raise ValueError('Rate mismatch: '+key)
        key=tuple(r[k] for k in ['risk_scenario','link','model','offset_m','method','gap_s'])
        seen=groups.setdefault(key,set())
        if int(r['seed']) in seen:raise ValueError('Duplicate seed metric')
        seen.add(int(r['seed']))
        group_rows.setdefault(key,[]).append(r)
        if r['method']=='FreePowerUND' and (scored or und!=total):raise ValueError('Unrestricted single RSSI claimed a decision')
    if any(s!=seeds for s in groups.values()):raise ValueError('Incomplete independent-seed group')
    aggregates=read_csv(root/'aggregate-metrics.csv')
    if len(aggregates)!=len(groups):raise ValueError('Aggregate group mismatch')
    expected_groups=9*len(cfg['models'])*len(cfg['links'])*len(cfg['offsets_m'])+(36 if cfg['include_risk'] else 0)
    if len(groups)!=expected_groups:raise ValueError('Method comparison matrix incomplete')
    for r in aggregates:
        key=tuple(r[k] for k in ['risk_scenario','link','model','offset_m','method','gap_s'])
        # Numeric spacing is represented as 10 or 10.0 across CSV producers.
        candidates=[k for k in group_rows if k[:-1]==key[:-1] and float(k[-1])==float(key[-1])]
        if len(candidates)!=1:raise ValueError('Unexpected aggregate condition')
        source=group_rows[candidates[0]]
        for field,per_seed in [('total_tx','tx_count'),('received','received_count'),('scored','scored_count'),('flags','flag_count'),('undetermined','und_count')]:
            if int(r[field])!=sum(int(row[per_seed]) for row in source):raise ValueError('Aggregate counts disagree with per-seed records')
        for metric in ['alarm_scored','alarm_received','alarm_all_tx','below_scored','und_rate','received_rate','eligible_rate']:
            valid=[float(row[metric]) for row in source if row[metric]!='']
            if int(r[f'{metric}_independent_seeds'])!=len(valid):raise ValueError('Scored-seed denominator mismatch')
            if valid and not math.isclose(float(r[f'{metric}_mean']),sum(valid)/len(valid),abs_tol=1e-12):raise ValueError('Aggregate mean disagrees with seed rates')
            values=[r[f'{metric}_{name}'] for name in ['low','mean','high']]
            if values[1]=='':
                if any(values):raise ValueError('Invalid undefined interval')
            elif int(r[f'{metric}_independent_seeds'])==1:
                if values[0] or values[2] or not 0<=float(values[1])<=1:raise ValueError('One seed cannot establish a between-seed interval')
            elif not all(0<=float(v)<=1 for v in values) or not float(values[0])-1e-12<=float(values[1])<=float(values[2])+1e-12:
                raise ValueError('Invalid seed interval')
    for r in read_csv(root/'paired-cohort.csv'):
        if not int(r['shared_scored_count'])<=int(r['shared_received_count'])<=min(int(r['normal_received']),int(r['attack_received'])):raise ValueError('Paired cohort accounting mismatch')
    return dict(status='PASSED',scene_count=len(receipts),metric_rows=len(rows),independent_seeds=len(seeds),groups=len(groups),
                scope='Public aggregate integrity only; CI does not install or run OMNeT++/INET')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('results',type=Path)
    print(json.dumps(validate(p.parse_args().results),indent=2))
