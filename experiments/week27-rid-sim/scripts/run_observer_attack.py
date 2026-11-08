"""Issue75 sequential native generation, frozen-normal calibration and audit."""
import argparse
from collections import defaultdict
import csv
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys

from evaluation import fit_geometry,calibrated_threshold,decide,metrics,split_check,signal_dbm,prediction
from normalize import read_vectors,normalize,write_csv
from observations import asynchronous_view,detector_projection
from observer_attack import CASES,SCHEDULE,attack_spec,attack_ini,run_attack_scene,audit_attack,apply_limits,compare_legacy
from run_evaluation import score_methods
from run_power import target_events,physical_audit,expected_total_rss
from scene import RX_POSITIONS
from setup import REPO,ROOT


def append_csv(path,record):
    exists=path.exists()
    with path.open('a',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(record))
        if not exists:writer.writeheader()
        writer.writerow(record)


def compare_pair(normal,attack):
    if len(normal)!=len(attack):raise ValueError('Paired TX counts differ')
    for a,b in zip(normal,attack):
        if abs(a['tx_time']-b['tx_time'])>1e-10 or math.dist(a['true_tx_xyz'],b['true_tx_xyz'])>1e-8:
            raise ValueError('Paired trajectory/schedule mismatch')


def bootstrap(values,repeats):
    import numpy as np
    values=[v for v in values if v is not None]
    if not values:return dict(mean=None,low=None,high=None,independent_seeds=0)
    if len(values)==1:return dict(mean=values[0],low=None,high=None,independent_seeds=1)
    array=np.asarray(values);rng=np.random.default_rng(750)
    means=np.sort(array[rng.integers(0,len(array),size=(repeats,len(array)))].mean(axis=1))
    return dict(mean=float(array.mean()),low=float(means[int(.025*repeats)]),high=float(means[min(repeats-1,int(.975*repeats))]),independent_seeds=len(values))


def aggregate(records,repeats):
    keys=['phy','link','attack_case','offset_m','bound_db','method'];groups=defaultdict(list)
    for row in records:groups[tuple(row[k] for k in keys)].append(row)
    result=[]
    for group,rows in groups.items():
        if len(set(r['seed'] for r in rows))!=len(rows):raise ValueError('Duplicate seed group')
        record=dict(zip(keys,group))
        for field in ['alarm_scored','alarm_received','alarm_all_tx','below_scored','und_rate','received_rate','eligible_rate']:
            record.update({f'{field}_{k}':v for k,v in bootstrap([r[field] for r in rows],repeats).items()})
        for field in ['tx_count','received_count','scored_count','flag_count','below_count','und_count']:
            record[field]=sum(r[field] for r in rows)
        result.append(record)
    return result


def load_verified(directory,spec):
    if json.loads((directory/'spec.json').read_text())!=spec:raise ValueError('Refusing mismatched raw spec')
    audit=json.loads((directory/'attack-audit.json').read_text())
    if hashlib.sha256((directory/'run.vec').read_bytes()).hexdigest()!=audit['vector_sha256']:raise ValueError('Raw vector hash changed')
    if hashlib.sha256((directory/'simulation.log').read_bytes()).hexdigest()!=audit['simulation_log_sha256']:raise ValueError('Original log hash changed')
    events=read_vectors(directory/'run.vec')
    config=dict(seed=spec['seed'],tx_host=1,rx_hosts=list(RX_POSITIONS),observer_regime='same_packet_multisite_comparison_only',phy_model='INET FreeSpace/Dipole')
    rows,tx,gcs,check=normalize(target_events(events,receivers=tuple(RX_POSITIONS)),spec['case'],config)
    check.update(physical_audit(events,tx,rows));ledger=audit_attack(events,tx,rows,spec)
    if any(check[k]!=audit[k] for k in ['tx_enqueued','rx_delivered','phy_tx_count','gcs_report_count']):raise ValueError('Source accounting changed')
    if audit['execution_exit_code']!=0:raise ValueError('Unsuccessful raw execution')
    return rows,sorted(tx,key=lambda t:t['tx_time']),audit,ledger


def factor_audit(normal_rows,normal_tx,rows,tx,ledger,geometry,scores,thresholds):
    compare_pair(normal_tx,tx);base=asynchronous_view(normal_rows,SCHEDULE,len(tx));view=asynchronous_view(rows,SCHEDULE,len(tx))
    public=dict(attack_bound_clamped=sum(r['clamped_by_attack_bound'] for r in ledger),phy_clamped=sum(r['clamped_by_phy_limit'] for r in ledger),
                tx_count=len(tx),selected_received=sum(r['delivered'] for r in ledger),target_mismatches=sum(r['target_mismatch'] is True for r in ledger),
                mean_abs_oracle_delta_mismatch_db=statistics.mean(abs(r['requested_delta_db']-r['oracle_requested_delta_db']) for r in ledger))
    errors=[];decomposition=[]
    for i,(a,b,l) in enumerate(zip(base,view,ledger)):
        if a['rssi_dbm'] is None or b['rssi_dbm'] is None:continue
        change=l['effective_phy_tx_dbm']-a['phy_tx_power_dbm_truth_only']
        error=b['rssi_dbm']-expected_total_rss(a['rssi_dbm'],change)
        errors.append(abs(error))
        # Algebraic counterfactual only, NOT another RF run. Retain only the
        # paired received cohort; no synthetic missing RSS is manufactured.
        nominal=l['effective_phy_tx_dbm']-l['applied_delta_db']
        ideal=signal_dbm(a)+(nominal-a['phy_tx_power_dbm_truth_only'])+l['requested_delta_db']-prediction(b,geometry)
        observed=signal_dbm(b)-prediction(b,geometry)
        decomposition.append(dict(index=i,ideal_unclipped_residual_db=ideal,observed_residual_db=observed,
                                  total_clipping_error_db=l['compensation_error_db'],channel_response_error_db=error,
                                  oracle_target_mismatch_db=l['requested_delta_db']-l['oracle_requested_delta_db']))
    if errors and max(errors)>1e-6:raise ValueError('Measured RSS response disagrees with actual PHY power change')
    public.update(paired_received=len(errors),rssi_response_max_error_db=max(errors) if errors else None)
    residual_scores=scores['SingleResidual'][0];kf=scores['KF_NIS'][0]
    flagged=decide(residual_scores,thresholds['SingleResidual'])
    public.update(single_flags_clipped=sum(d=='FLAG' and (l['clamped_by_attack_bound'] or l['clamped_by_phy_limit']) for d,l in zip(flagged,ledger)),
                  single_flags_unclipped=sum(d=='FLAG' and not (l['clamped_by_attack_bound'] or l['clamped_by_phy_limit']) for d,l in zip(flagged,ledger)),
                  kf_received_startup_und=sum(r['delivered'] and s is None for r,s in zip(view,kf)))
    return public,decomposition


def controls(scene,raw,out):
    a=attack_spec(701,'reference_rx0',100,'strong');b=attack_spec(701,'schedule_aware',100,'strong',schedule=[0])
    ra,ta,aa,la=scene('control-reference0',a);rb,tb,ab,lb=scene('control-aware-fixed0',b)
    compare_pair(ta,tb)
    delta=max(abs(x['effective_phy_tx_dbm']-y['effective_phy_tx_dbm']) for x,y in zip(la,lb))
    if delta>1e-8:raise ValueError('Fixed-zero aware power differs from reference0')
    a=attack_spec(702,'schedule_blind',100,'edge');b=dict(a,defender_schedule=list(reversed(SCHEDULE)))
    ra,ta,aa,la=scene('control-blind-original-schedule',a);rb,tb,ab,lb=scene('control-blind-permuted-schedule',b)
    blind_delta=max(abs(x['effective_phy_tx_dbm']-y['effective_phy_tx_dbm']) for x,y in zip(la,lb))
    if blind_delta>1e-8 or attack_ini(a)!=attack_ini(b):raise ValueError('Blind attack consumed observer schedule')
    result=dict(status='PASSED',fixed_zero_max_power_difference_db=delta,blind_permuted_max_power_difference_db=blind_delta,
                blind_ini_identical=True,scope='Actual independent native RF runs; defender assignment changes only in observation filtering')
    (out/'controls.json').write_text(json.dumps(result,indent=2)+'\n')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--raw-dir',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--workspace',type=Path,default=REPO/'.cache/issue75');p.add_argument('--config',type=Path,default=ROOT/'config/observer-attack.json')
    p.add_argument('--smoke',action='store_true');p.add_argument('--reuse-raw',action='store_true',help='Explicit hash-verified reuse, always write a NEW public analysis directory')
    a=p.parse_args();os.umask(0o077)
    if not a.raw_dir.resolve().is_relative_to((REPO/'captures').resolve()):p.error('Use ignored captures/')
    if a.out.exists() or (a.raw_dir.exists() and not a.reuse_raw):p.error('Preserve previous evidence; use new paths')
    a.raw_dir.mkdir(parents=True,exist_ok=True,mode=0o700);a.out.mkdir(parents=True)
    cfg=json.loads(a.config.read_text())
    if a.smoke:
        cfg.update(calibration_seeds=[601],evaluation_seeds=[701,702],links=['strong','edge'],offsets_m=[100],attack_bounds_db=[10],training_packets=100,bootstrap_repeats=100)
        cfg['phy_ablation']=[dict(name='default',minimum_dbm=-80,maximum_dbm=23,cases=CASES,bounds_db=[10])]
    split_check(cfg['train_seeds'],cfg['calibration_seeds'],cfg['evaluation_seeds'])
    (a.out/'configuration.json').write_text(json.dumps(cfg,indent=2)+'\n')
    native_hash={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in (ROOT/'native').glob('*') if f.is_file()}
    manifest=dict(binary_sha256=hashlib.sha256((a.workspace/'project-build/out/clang-release/rid_smoke').read_bytes()).hexdigest(),native_sha256=native_hash)
    path=a.raw_dir/'run-manifest.json'
    if path.exists():
        if json.loads(path.read_text())!=manifest:raise ValueError('Refusing raw reuse with different native binary/source')
    else:path.write_text(json.dumps(manifest,indent=2)+'\n')
    os.environ.setdefault('MPLBACKEND','Agg');sys.path.insert(0,str(a.workspace.resolve()/'uli-net-sim'))
    from evaluations.detectors import multilaterate_with_tx_power
    summary=dict(status='RUNNING',dataset_source='simulation',stage='PR5',completed_scenes=0,new_rf_scenes=0,reused_rf_scenes=0,smoke=a.smoke)
    reports=[];receipts=[];factors=[];cohorts=[];threshold_table={};reproduction=[]
    analysis_private=a.raw_dir/'analyses'/hashlib.sha256(str(a.out.resolve()).encode()).hexdigest()[:16]
    analysis_private.mkdir(parents=True,mode=0o700)
    def checkpoint():
        (a.out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    def scene(run_id,spec):
        directory=a.raw_dir.resolve()/run_id;reused=directory.exists()
        if reused:
            if not a.reuse_raw:raise ValueError('Unexpected existing raw scene')
            rows,tx,audit,ledger=load_verified(directory,spec)
        else:rows,tx,audit,ledger=run_attack_scene(spec,a.workspace.resolve(),directory)
        if run_id.startswith('default-eval-') and (spec['attack_case']=='position_only' or (spec['attack_case']=='reference_rx0' and spec['attack_bound_db']==10)):
            link=next(link for link in cfg['links'] if f'-{link}-' in run_id)
            model='adaptive' if spec['attack_case']=='reference_rx0' else 'fixed'
            old=REPO/'captures/issue70-evaluation-20261108-full-a'/f'main-eval-{link}-{model}-{spec["seed"]}-offset{spec["offset_x_m"]}'
            if old.exists():
                comparison=compare_legacy(rows,tx,old)
                with (a.out/'legacy-rf-reproduction.jsonl').open('a') as f:f.write(json.dumps(comparison)+'\n')
        receipt=json.loads((directory/'execution.json').read_text())
        published=dict(run_id=run_id,spec=spec,exit_code=receipt['exit_code'],started_utc=receipt['started_utc'],reused_rf=reused,
                       tx_count=audit['tx_enqueued'],rx_count=audit['rx_delivered'],phy_tx_count=audit['phy_tx_count'],
                       first_tx_time_s=audit['first_tx_time_s'],last_tx_time_s=audit['last_tx_time_s'],
                       vector_sha256=audit['vector_sha256'],original_log_sha256=receipt['log_sha256'],attack_ledger_sha256=audit['attack_ledger_sha256'])
        receipts.append(published)
        with (a.out/'case-receipts.jsonl').open('a') as f:f.write(json.dumps(published)+'\n')
        with (a.out/'simulation.log').open('a') as f:
            f.write(f'\nRUN {run_id} ORIGINAL_LOG_SHA256 {receipt["log_sha256"]}\n')
            f.write((directory/'simulation.log').read_text().replace(str(REPO),'<REPO>'))
        summary['completed_scenes']=len(receipts);summary['reused_rf_scenes']+=int(reused);summary['new_rf_scenes']+=int(not reused);checkpoint()
        return rows,sorted(tx,key=lambda t:t['tx_time']),audit,ledger
    try:
        controls(scene,a.raw_dir,a.out)
        for phy in cfg['phy_ablation']:
            bounds=phy['bounds_db'];limits=(phy['minimum_dbm'],phy['maximum_dbm']);name=phy['name']
            train=attack_spec(501,'position_only',0,'strong',0,limits,cfg['training_packets'])
            rows,_,_,_=scene(f'{name}-train-normal',train)
            geometry=fit_geometry(detector_projection(rows,name+'-train','same_physical_packet_comparison'),'train_normal')
            (analysis_private/f'{name}-geometry.json').write_text(json.dumps(geometry)+'\n')
            for link in cfg['links']:
                normal_scores=defaultdict(list)
                for seed in cfg['calibration_seeds']:
                    rid=f'{name}-cal-{link}-{seed}'
                    rows,_,_,_=scene(rid,attack_spec(seed,'position_only',0,link,0,limits,cfg['packets']))
                    for method,(values,rx) in score_methods(rows,rid,geometry,multilaterate_with_tx_power).items():normal_scores[method].extend(values)
                threshold={method:calibrated_threshold(values,'calibrate_normal') for method,values in normal_scores.items()}
                threshold_table[f'{name}:{link}']=threshold
                (a.out/'thresholds.json').write_text(json.dumps(threshold_table,indent=2)+'\n')
                if name=='default' and not a.smoke:
                    old=json.loads((REPO/'week27/results/uli-net-sim-evaluation-20261108-full-b/thresholds.json').read_text())[f'main:{link}:fixed']
                    errors=[abs(v-old[k]) for k,v in threshold.items() if v is not None and old[k] is not None]
                    if any((v is None)!=(old[k] is None) for k,v in threshold.items()) or (errors and max(errors)>1e-6):raise ValueError('PR4 normal thresholds failed reproduction; no attack retuning allowed')
                    reproduction.append(dict(phy=name,link=link,normal_threshold_max_difference=max(errors) if errors else None))
                for seed in cfg['evaluation_seeds']:
                    rid=f'{name}-eval-{link}-{seed}-normal'
                    normal_rows,normal_tx,_,normal_ledger=scene(rid,attack_spec(seed,'position_only',0,link,0,limits,cfg['packets']))
                    baseline=score_methods(normal_rows,rid,geometry,multilaterate_with_tx_power)
                    def emit(rid,spec,rows,scored,case,offset,bound):
                        meta=dict(phy=name,link=link,seed=seed,attack_case=case,offset_m=offset,bound_db=bound)
                        for method,(values,rx) in scored.items():
                            decisions=decide(values,threshold[method]);record=dict(meta,method=method,**metrics(decisions,rx))
                            reports.append(record);append_csv(a.out/'per-seed-metrics.csv',record)
                            if case!='normal':
                                before,before_rx=baseline[method];normal_decisions=decide(before,threshold[method])
                                shared=[i for i,(x,y) in enumerate(zip(before,values)) if x is not None and y is not None and threshold[method] is not None]
                                cohort=dict(meta,method=method,shared_scored_count=len(shared),shared_received_count=sum(x and y for x,y in zip(before_rx,rx)),normal_received=sum(before_rx),attack_received=sum(rx),
                                            shared_normal_flags=sum(normal_decisions[i]=='FLAG' for i in shared),shared_attack_flags=sum(decisions[i]=='FLAG' for i in shared))
                                cohorts.append(cohort);append_csv(a.out/'paired-cohort.csv',cohort)
                            if method in ['FreePowerUND','SingleResidual','KF_NIS']:
                                selected=asynchronous_view(rows,SCHEDULE,len(values))
                                for node in SCHEDULE:
                                    ids=[i for i,r in enumerate(selected) if r['rx_node_id']==node]
                                    append_csv(a.out/'per-observer-metrics.csv',dict(meta,method=method,rx_node_id=node,**metrics([decisions[i] for i in ids],[rx[i] for i in ids])))
                        (analysis_private/f'{rid}-scores.json').write_text(json.dumps({m:dict(scores=v[0],received=v[1],decisions=decide(v[0],threshold[m])) for m,v in scored.items()})+'\n')
                    emit(rid,None,normal_rows,baseline,'normal',0,0)
                    for offset in cfg['offsets_m']:
                        plans=[]
                        if 'position_only' in phy['cases']:plans.append(('position_only',0))
                        plans.extend((case,bound) for bound in bounds for case in phy['cases'] if case!='position_only')
                        for case,bound in plans:
                            spec=attack_spec(seed,case,offset,link,bound,limits,cfg['packets']);rid=f'{name}-eval-{link}-{seed}-{case}-offset{offset}-bound{bound}'
                            rows,tx,audit,ledger=scene(rid,spec)
                            scored=score_methods(rows,rid,geometry,multilaterate_with_tx_power)
                            factor,private=factor_audit(normal_rows,normal_tx,rows,tx,ledger,geometry,scored,threshold)
                            factor.update(phy=name,link=link,seed=seed,attack_case=case,offset_m=offset,bound_db=bound)
                            factors.append(factor);append_csv(a.out/'factor-audit.csv',factor)
                            (analysis_private/f'{rid}-decomposition.json').write_text(json.dumps(private)+'\n')
                            emit(rid,spec,rows,scored,case,offset,bound)
                            checkpoint()
        write_csv(a.out/'aggregate-metrics.csv',aggregate(reports,cfg['bootstrap_repeats']))
        (a.out/'normal-reproduction.json').write_text(json.dumps(reproduction,indent=2)+'\n')
        summary.update(status='PR5_EVALUATION_PASSED',metric_rows=len(reports),factor_rows=len(factors),
                       total_phy_tx=sum(r['phy_tx_count'] for r in receipts),total_rx=sum(r['rx_count'] for r in receipts))
    except Exception as error:
        summary.update(status='PR5_FAILED',error=f'{type(error).__name__}: {error}')
    provenance=dict(native_manifest=manifest,python=platform.python_version(),base_commit='55db328520594f94b5e19bf126a62934d337dea7',
                    upstream_sha=subprocess.check_output(['git','-C',str(a.workspace/'uli-net-sim'),'rev-parse','HEAD'],text=True).strip(),
                    config_sha256=hashlib.sha256(a.config.read_bytes()).hexdigest(),
                    script_sha256={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in (ROOT/'scripts').glob('*.py')})
    (a.out/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
    checkpoint();print(json.dumps(summary,indent=2));return 0 if summary['status']=='PR5_EVALUATION_PASSED' else 2


if __name__=='__main__':raise SystemExit(main())
