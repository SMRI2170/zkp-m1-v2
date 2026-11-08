"""Offline PR5 aggregate audit. This does not execute OMNeT++ or access raw XYZ."""
import argparse
from collections import defaultdict
import csv
import json
import math
from pathlib import Path

from evaluation import metrics,split_check


def read(path):
    with path.open() as f:return list(csv.DictReader(f))


def validate(root,mlat):
    cfg=json.loads((root/'configuration.json').read_text());summary=json.loads((root/'summary.json').read_text())
    if summary['status']!='PR5_EVALUATION_PASSED' or summary['smoke']:raise ValueError('Full native evaluation required')
    split_check(cfg['train_seeds'],cfg['calibration_seeds'],cfg['evaluation_seeds'])
    if cfg['train_seeds']!=[501] or len(cfg['calibration_seeds'])!=10 or len(cfg['evaluation_seeds'])!=20:raise ValueError('Incomplete seed protocol')
    expected=4;eval_cases=0;expected_groups=0
    for phy in cfg['phy_ablation']:
        attacks=(1 if 'position_only' in phy['cases'] else 0)+len([c for c in phy['cases'] if c!='position_only'])*len(phy['bounds_db'])
        conditions=len(cfg['links'])*(1+len(cfg['offsets_m'])*attacks)
        eval_cases+=conditions*len(cfg['evaluation_seeds']);expected_groups+=conditions*9
        expected+=1+len(cfg['links'])*len(cfg['calibration_seeds'])+conditions*len(cfg['evaluation_seeds'])
    receipts=[json.loads(line) for line in (root/'case-receipts.jsonl').read_text().splitlines()]
    if len(receipts)!=expected or len({r['run_id'] for r in receipts})!=expected:raise ValueError('Missing or duplicate RF cases')
    if summary['completed_scenes']!=expected or summary['new_rf_scenes']+summary['reused_rf_scenes']!=expected:raise ValueError('RF status accounting mismatch')
    if sum(r['phy_tx_count'] for r in receipts)!=summary['total_phy_tx'] or sum(r['rx_count'] for r in receipts)!=summary['total_rx']:raise ValueError('Physical TX/RX total mismatch')
    for r in receipts:
        if r['exit_code']!=0 or r['phy_tx_count']!=r['tx_count'] or not 0<=r['rx_count']<=r['tx_count']*5:raise ValueError('Unsuccessful or invalid RF record')
        if not math.isclose(r['last_tx_time_s']-r['first_tx_time_s'],(r['tx_count']-1)*10,abs_tol=1e-8):raise ValueError('Simulator spacing changed')
        if '-cal-' in r['run_id'] or '-train-' in r['run_id']:
            if r['spec']['offset_x_m']!=0 or r['spec']['attack_case']!='position_only':raise ValueError('Attack used for fitting')
    rows=read(root/'per-seed-metrics.csv');groups=defaultdict(list);lookup={}
    if len(rows)!=eval_cases*9:raise ValueError('Incomplete method matrix')
    group_keys=['phy','link','attack_case','offset_m','bound_db','method']
    for r in rows:
        total=int(r['tx_count']);flags=int(r['flag_count']);below=int(r['below_count']);und=int(r['und_count']);received=int(r['received_count'])
        if flags+below+und!=total or not flags+below<=received<=total:raise ValueError('Invalid denominators')
        reference=metrics(['FLAG']*flags+['BELOW_THRESHOLD']*below+['UNDETERMINED']*und,[True]*received+[False]*(total-received))
        for k,v in reference.items():
            if v is None:
                if r[k]!='':raise ValueError('Undefined value replaced with a number')
            elif not math.isclose(float(r[k]),v,abs_tol=1e-12):raise ValueError('Rate does not match counts')
        key=tuple(r[k] for k in group_keys);groups[key].append(r)
        lookup[(*key,r['seed'])]=r
        if r['method']=='FreePowerUND' and (flags or below or und!=total):raise ValueError('Unrestricted one-RSSI position verdict invented')
    seeds=set(cfg['evaluation_seeds'])
    if len(groups)!=expected_groups or any({int(r['seed']) for r in v}!=seeds or len(v)!=20 for v in groups.values()):raise ValueError('Independent seed groups incomplete')
    aggregate=read(root/'aggregate-metrics.csv')
    if len(aggregate)!=len(groups):raise ValueError('Aggregate conditions mismatch')
    for a in aggregate:
        group=groups[tuple(a[k] for k in group_keys)]
        for metric in ['alarm_scored','alarm_received','alarm_all_tx','below_scored','und_rate','received_rate','eligible_rate']:
            values=[float(r[metric]) for r in group if r[metric]!=''];n=len(values)
            if int(a[f'{metric}_independent_seeds'])!=n:raise ValueError('Eligible-seed count mismatch')
            if not values:
                if a[f'{metric}_mean']!='':raise ValueError('No-scored-seed mean invented')
            elif not math.isclose(float(a[f'{metric}_mean']),sum(values)/n,abs_tol=1e-12):raise ValueError('Aggregate mean mismatch')
            if n<2:
                if a[f'{metric}_low'] or a[f'{metric}_high']:raise ValueError('Fewer than two seeds cannot support uncertainty interval')
            elif not 0<=float(a[f'{metric}_low'])<=float(a[f'{metric}_high'])<=1:raise ValueError('Invalid rate interval')
    for r in read(root/'paired-cohort.csv'):
        shared=int(r['shared_scored_count'])
        if not shared<=int(r['shared_received_count'])<=min(int(r['normal_received']),int(r['attack_received'])):raise ValueError('Paired cohort denominator mismatch')
        if int(r['shared_normal_flags'])>shared or int(r['shared_attack_flags'])>shared:raise ValueError('Paired flags exceed evaluated cohort')
    for r in read(root/'factor-audit.csv'):
        if r['attack_case']=='schedule_aware' and (int(r['target_mismatches']) or float(r['mean_abs_oracle_delta_mismatch_db'])>1e-8):raise ValueError('Oracle target differs from actual observation selection')
        if r['rssi_response_max_error_db'] and float(r['rssi_response_max_error_db'])>1e-6:raise ValueError('Recorded PHY/RSS response did not match')
        if any(not 0<=int(r[k])<=int(r['tx_count']) for k in ['attack_bound_clamped','phy_clamped','selected_received']):raise ValueError('Invalid clamp count')
        key=tuple(r[k] for k in ['phy','link','attack_case','offset_m','bound_db'])+('SingleResidual',r['seed'])
        if int(r['single_flags_clipped'])+int(r['single_flags_unclipped'])!=int(lookup[key]['flag_count']):raise ValueError('Residual alarm factor counts do not reconcile')
    targets=read(root/'attack-target-audit.csv')
    if len(targets)!=eval_cases:raise ValueError('Target audit incomplete')
    for r in targets:
        total=int(r['tx_count'])
        if sum(int(r[f'target_{n}_count']) for n in [-1,0,2,3,4,5])!=total:raise ValueError('Target histogram incomplete')
        if r['attack_case']=='schedule_aware' and any(int(r[f'target_{n}_count'])!=total//5 for n in [0,2,3,4,5]):raise ValueError('Oracle schedule did not cycle over five nodes')
    for r in read(root/'B-to-C-shared-cohort.csv'):
        if not int(r['shared_scored_count'])<=int(r['shared_received'])<=min(int(r['B_received']),int(r['C_received'])):raise ValueError('B/C paired accounting mismatch')
    control=json.loads((root/'controls.json').read_text())
    if control['status']!='PASSED' or not control['blind_ini_identical'] or max(control['fixed_zero_max_power_difference_db'],control['blind_permuted_max_power_difference_db'])>1e-8:raise ValueError('Attack-knowledge control failed')
    negative=json.loads((root/'negative-controls.json').read_text())
    if negative['status']!='EXPECTED_REJECTION_PASSED' or negative['exit_code']==0:raise ValueError('Invalid-distance native rejection not established')
    reproduction=json.loads((root/'normal-reproduction.json').read_text())
    if len(reproduction)!=len(cfg['links']) or any(r['normal_threshold_max_difference'] is not None and r['normal_threshold_max_difference']>1e-6 for r in reproduction):raise ValueError('PR4 normal threshold reproduction failed')
    legacy=[json.loads(line) for line in (root/'legacy-rf-reproduction.jsonl').read_text().splitlines()]
    if len(legacy)!=300 or any(r['status']!='PASSED' or (r['max_measured_rss_difference_db'] is not None and r['max_measured_rss_difference_db']>1e-8) for r in legacy):raise ValueError('PR4 A/B RF reproduction incomplete')
    diagnostic=json.loads((mlat/'summary.json').read_text())
    if diagnostic['status']!='MLAT_DIAGNOSTICS_PASSED' or diagnostic['new_rf_runs']!=0 or diagnostic['upstream_position_max_difference_m']>1e-6:raise ValueError('MLAT baseline reproduction failed')
    for r in read(mlat/'per-seed-metrics.csv'):
        if int(r['flag_count'])+int(r['below_count'])+int(r['und_count'])!=int(r['tx_count']):raise ValueError('MLAT metric denominators inconsistent')
    model=json.loads((root/'model-audit.json').read_text())
    if model['status']!='PASSED' or model['new_rf_runs']!=0 or max(model['max_signal_reconstruction_error_db'],model['max_signed_residual_identity_error_db'])>1e-6:
        raise ValueError('Physical-model residual decomposition failed')
    preservation=json.loads((root/'preservation-audit.json').read_text())
    if preservation['status']!='PASSED' or preservation['old_rf_vectors_and_logs_unchanged']!=943 or not preservation['source_upstream_clean']:
        raise ValueError('Prior results preservation was not established')
    if any(r['group_or_other_access'] or not r['ignored'] for r in preservation['privacy']):raise ValueError('Raw privacy audit failed')
    return dict(status='PASSED',rf_cases=expected,evaluation_cases=eval_cases,metric_rows=len(rows),seed_groups=len(groups),
                independent_evaluation_seeds=20,mlat_reused_scenes=diagnostic['reused_rf_scenes'],
                scope='Offline aggregate and protocol audit; CI does not run RF simulations or read private captures')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('results',type=Path);p.add_argument('mlat_results',type=Path)
    a=p.parse_args();print(json.dumps(validate(a.results,a.mlat_results),indent=2))
