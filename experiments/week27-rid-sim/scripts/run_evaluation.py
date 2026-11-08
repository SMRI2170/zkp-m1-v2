"""Sequential PR4 real INET generation, normal-only calibration and evaluation."""
import argparse
from collections import defaultdict
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import random
import re
import shutil
import platform
import subprocess
import sys

from evaluation import (fit_geometry,single_residual,kf_scores,drss_score,mlat_score,
                        calibrated_threshold,decide,metrics,grouped_frames,split_check,seed_interval,risk_mask)
from normalize import read_vectors,write_csv
from observations import detector_projection,asynchronous_view
from scene import run_scene,RX_POSITIONS
from setup import ROOT,REPO


def labels(model,offset):
    if model=='fixed':return 'PositionOnly' if offset else 'FixedNormal'
    if model=='adaptive':return 'AdaptiveSpoof' if offset else 'FixedNormal'
    return model.title()+('Spoof' if offset else 'Normal')


def create_spec(seed,model,offset,link,count,gap,risk=False):
    rng=random.Random(seed)
    power_limits={'strong':(10,20),'edge':(-6,-2),'weak':(-14,-10)}
    if link not in power_limits:raise ValueError('Unknown declared link stratum')
    return dict(seed=seed,model=model,case=labels(model,offset),offset_x_m=offset,
                count=count,gap_s=gap,angle_deg=rng.uniform(0,360),
                nominal_dbm=rng.uniform(*power_limits[link]),
                height_m=20 if risk else 40,radius_m=20 if risk else 80)


def score_methods(rows,run_id,geometry,solver):
    view=asynchronous_view(rows,list(RX_POSITIONS),len(rows)//len(RX_POSITIONS))
    projection=detector_projection(view,run_id)
    rx=[r['delivered'] for r in projection]
    output={'FreePowerUND':([None]*len(view),rx),'SingleResidual':(single_residual(projection,geometry),rx),
            'KF_NIS':(kf_scores(projection),rx)}
    multisite=detector_projection(rows,run_id,'same_physical_packet_comparison')
    for n in [2,3,4,5]:
        frames=grouped_frames(multisite,list(RX_POSITIONS)[:n])
        received=[any(r['delivered'] for r in frame) for frame in frames]
        output[f'DRSS{n}']=([drss_score(frame,geometry) for frame in frames],received)
        if n>=4:output[f'MLAT{n}']=([mlat_score(frame,solver) for frame in frames],received)
    return output


def user_at(t):
    return [200+10*math.sin(t/20),200+10*math.cos(t/20),0]


def native_kf_parity(directory,rows):
    observed={}
    for (module,event,time),fields in read_vectors(directory/'run.vec').items():
        if 'KF NIS Drone 1' in fields:
            node=int(re.search(r'host\[(\d+)\]',module).group(1))
            observed[f'{node}:{event}']=fields['KF NIS Drone 1']
    compared=[]
    for node in RX_POSITIONS:
        subset=[r for r in rows if r['rx_node_id']==node]
        projected=detector_projection(subset,'native-parity')
        for row,value in zip(subset,kf_scores(projected)):
            actual=observed.get(row['rx_event_id'])
            if value is None:
                if actual is not None:raise ValueError('Native KF initialization unexpectedly scored')
            elif actual is None:raise ValueError('Native KF NIS missing')
            else:compared.append(abs(value-actual))
    if not compared or max(compared)>1e-8:raise ValueError('Selected-observation KF replay differs from native equations')
    return dict(status='PASSED',native_nis_count=len(observed),compared=len(compared),max_nis_difference=max(compared),
                note='All observations in this control only. M0 replay uses selected observations only; native precomputed state is never reused for M0.')


def aggregate(reports,repeats):
    groups=defaultdict(list)
    keys=['risk_scenario','link','model','offset_m','method','gap_s']
    for row in reports:groups[tuple(row[k] for k in keys)].append(row)
    result=[]
    for group,rows in groups.items():
        if len({r['seed'] for r in rows})!=len(rows):raise ValueError('Duplicate seed within inference group')
        record=dict(zip(keys,group))
        for metric in ['alarm_scored','alarm_received','alarm_all_tx','below_scored','und_rate','received_rate','eligible_rate']:
            ci=seed_interval([r[metric] for r in rows],repeats=repeats)
            record.update({f'{metric}_{k}':v for k,v in ci.items()})
        record.update(total_tx=sum(r['tx_count'] for r in rows),received=sum(r['received_count'] for r in rows),
                      scored=sum(r['scored_count'] for r in rows),flags=sum(r['flag_count'] for r in rows),
                      undetermined=sum(r['und_count'] for r in rows),
                      interpretation='normal FPR' if record['offset_m']==0 else 'spoof TPR; below_scored is conditional FNR, UND separate')
        result.append(record)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--raw-dir',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--workspace',type=Path,default=REPO/'.cache/issue70')
    p.add_argument('--config',type=Path,default=ROOT/'config/evaluation.json')
    p.add_argument('--smoke',action='store_true');p.add_argument('--reuse-existing',action='store_true',help='Explicitly re-analyze hash-verified existing raw scenes without RF rerun')
    a=p.parse_args();os.umask(0o077)
    if not a.raw_dir.resolve().is_relative_to((REPO/'captures').resolve()):p.error('Use ignored captures/')
    if (a.raw_dir.exists() or a.out.exists()) and not a.reuse_existing:p.error('New paths required; evidence is not overwritten')
    a.raw_dir.mkdir(parents=True,exist_ok=True,mode=0o700);a.out.mkdir(parents=True,exist_ok=True)
    cfg=json.loads(a.config.read_text())
    if a.smoke:cfg.update(calibration_seeds=[601],evaluation_seeds=[701,702],models=['fixed','adaptive'],packets_per_flight=10,training_packets=100,include_risk=False,bootstrap_repeats=100)
    split_check(cfg['train_seeds'],cfg['calibration_seeds'],cfg['evaluation_seeds'])
    if len(cfg['train_seeds'])!=1:raise ValueError('This pilot uses one geometry-training seed, not an environment generalization claim')
    (a.out/'configuration.json').write_text(json.dumps(cfg,indent=2)+'\n')
    sys.path.insert(0,str(a.workspace.resolve()/'uli-net-sim'))
    os.environ.setdefault('MPLBACKEND','Agg')
    try:
        from evaluations.detectors import multilaterate_with_tx_power
    except Exception as error:
        failure=dict(dataset_source='simulation',status='ENV_BLOCKED',error=f'{type(error).__name__}: {error}',completed_scenes=0)
        (a.out/'summary.json').write_text(json.dumps(failure,indent=2)+'\n')
        raise
    solver=multilaterate_with_tx_power
    import numpy,pandas,pyarrow,scipy,matplotlib
    provenance=dict(parent_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
                    upstream_sha=subprocess.check_output(['git','-C',str(a.workspace/'uli-net-sim'),'rev-parse','HEAD'],text=True).strip(),
                    python=platform.python_version(),versions={m.__name__:m.__version__ for m in [numpy,pandas,pyarrow,scipy,matplotlib]},
                    binary_sha256=hashlib.sha256((a.workspace/'project-build/out/clang-release/rid_smoke').read_bytes()).hexdigest(),
                    script_sha256={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in (ROOT/'scripts').glob('*.py')})
    (a.out/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
    reports=[];receipts=[];thresholds={};paired=[];risks=[];score_cache={};tx_cache={}
    summary=dict(dataset_source='simulation',status='RUNNING',completed_scenes=0,planned_evaluation_seeds=len(cfg['evaluation_seeds']),
                 source='Actual OMNeT++/INET Beacon runs; no synthetic RSSI additions in analysis',
                 limitations=[cfg['scope'],cfg['attacker'],'Normal-only empirical thresholds, not guaranteed 5% FPR',
                              'Same-frame methods are additional observations, not the original asynchronous solution',
                              'MLP N/A: supervised attack labels conflict with normal-only training policy; native upstream offline KF missing-to-zero convention not used'])
    def checkpoint():
        (a.out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
        if reports:write_csv(a.out/'per-seed-metrics.csv',reports)
        (a.out/'case-receipts.json').write_text(json.dumps(receipts,indent=2)+'\n')
    def scene(run_id,spec):
        directory=a.raw_dir.resolve()/run_id
        reused=directory.exists()
        if reused:
            if not a.reuse_existing:raise ValueError('Unexpected existing scene')
            if json.loads((directory/'spec.json').read_text())!=spec:raise ValueError('Resume spec mismatch')
            audit=json.loads((directory/'audit.json').read_text())
            if audit['vector_sha256']!=hashlib.sha256((directory/'run.vec').read_bytes()).hexdigest():raise ValueError('Resume raw hash mismatch')
            # Re-parse verified source vectors, not a potentially edited
            # intermediate parquet file. Recheck exact PHY and GCS joins.
            from normalize import normalize
            from run_power import target_events,physical_audit
            events=read_vectors(directory/'run.vec')
            config=dict(seed=spec['seed'],tx_host=1,rx_hosts=list(RX_POSITIONS),
                        observer_regime='same_packet_multisite_comparison_only',phy_model='INET FreeSpace/Dipole')
            rows,tx,gcs,check=normalize(target_events(events,receivers=tuple(RX_POSITIONS)),spec['case'],config)
            check.update(physical_audit(events,tx,rows))
            if any(check[k]!=audit[k] for k in ['tx_enqueued','rx_delivered','gcs_report_count','phy_tx_count']):raise ValueError('Resume source audit mismatch')
        else:rows,tx,audit=run_scene(spec,a.workspace.resolve(),directory)
        if audit['execution_exit_code']!=0 or audit['phy_tx_count']!=spec['count']:raise ValueError('Unsuccessful scene cannot enter evaluation')
        execution=json.loads((directory/'execution.json').read_text())
        log=(directory/'simulation.log').read_text()
        for root,replace in [(str(REPO),'<REPO>'),(str(a.raw_dir.resolve()),'<PRIVATE_CAPTURE>')]:log=log.replace(root,replace)
        (a.out/'logs').mkdir(exist_ok=True)
        (a.out/'logs'/f'{run_id}.log').write_text(log)
        receipts.append(dict(run_id=run_id,spec=spec,exit_code=execution['exit_code'],vector_sha256=audit['vector_sha256'],log_sha256=execution['log_sha256'],
                             original_started_utc=execution['started_utc'],rf_reused_explicitly=reused,
                             tx_count=audit['tx_enqueued'],phy_tx_count=audit['phy_tx_count'],received=audit['rx_delivered'],
                             first_tx_time_s=audit['first_tx_time_s'],last_tx_time_s=audit['last_tx_time_s']))
        summary['completed_scenes']=len(receipts)
        return rows,sorted(tx,key=lambda t:t['tx_time'])
    try:
        parity_spec=create_spec(502,'fixed',0,'strong',10,10);parity_spec['record_kf']=True
        parity_rows,_=scene('native-kf-parity',parity_spec)
        summary['native_kf_parity']=native_kf_parity(a.raw_dir.resolve()/'native-kf-parity',parity_rows);checkpoint()
        for risk in ([False,True] if cfg['include_risk'] else [False]):
            scope='risk' if risk else 'main';models=['fixed','adaptive'] if risk else cfg['models'];links=['strong'] if risk else cfg['links']
            train_spec=create_spec(cfg['train_seeds'][0],'fixed',0,'strong',cfg['training_packets'],cfg['gap_s'],risk)
            rows,_=scene(scope+'-train-normal',train_spec)
            geometry=fit_geometry(detector_projection(rows,scope+'-train-normal','same_physical_packet_comparison'),'train_normal')
            for link,model in itertools.product(links,models):
                normal_scores=defaultdict(list)
                for seed in cfg['calibration_seeds']:
                    run_id=f'{scope}-cal-{link}-{model}-{seed}'
                    spec=create_spec(seed,model,0,link,cfg['packets_per_flight'],cfg['gap_s'],risk)
                    rows,_=scene(run_id,spec)
                    for method,(scores,received) in score_methods(rows,run_id,geometry,solver).items():normal_scores[method].extend(scores)
                    checkpoint()
                fitted={m:calibrated_threshold(s,'calibrate_normal',cfg['alpha']) for m,s in normal_scores.items()}
                thresholds[f'{scope}:{link}:{model}']=fitted
                (a.out/'thresholds.json').write_text(json.dumps(thresholds,indent=2)+'\n')
                for seed in cfg['evaluation_seeds']:
                    offsets=[0,100] if risk else cfg['offsets_m']
                    baseline=None;baseline_tx=None
                    for offset in offsets:
                        run_id=f'{scope}-eval-{link}-{model}-{seed}-offset{offset}'
                        spec=create_spec(seed,model,offset,link,cfg['packets_per_flight'],cfg['gap_s'],risk)
                        rows,tx=scene(run_id,spec)
                        scored=score_methods(rows,run_id,geometry,solver)
                        if offset==0:baseline=scored;baseline_tx=tx
                        elif baseline_tx is not None:
                            if any(abs(t['tx_time']-b['tx_time'])>1e-10 or math.dist(t['true_tx_xyz'],b['true_tx_xyz'])>1e-8 for t,b in zip(tx,baseline_tx)):
                                raise ValueError('Paired true trajectory or schedule differs')
                        for method,(scores,received) in scored.items():
                            decisions=decide(scores,fitted[method]);record=dict(seed=seed,model=model,link=link,risk_scenario=risk,offset_m=offset,method=method,gap_s=cfg['gap_s'])
                            record.update(metrics(decisions,received));reports.append(record)
                            if offset and baseline is not None:
                                before,before_rx=baseline[method];before_decisions=decide(before,fitted[method])
                                shared=[i for i,(x,y) in enumerate(zip(before,scores)) if x is not None and y is not None]
                                paired.append(dict(seed=seed,model=model,link=link,risk_scenario=risk,offset_m=offset,method=method,
                                                   shared_scored_count=len(shared),normal_flag_count=sum(before_decisions[i]=='FLAG' for i in shared),attack_flag_count=sum(decisions[i]=='FLAG' for i in shared),
                                                   shared_received_count=sum(x and y for x,y in zip(before_rx,received)),normal_received=sum(before_rx),attack_received=sum(received)))
                            if risk and offset:
                                mask=risk_mask(tx,user_at);indices=[i for i,v in enumerate(mask) if v]
                                risks.append(dict(seed=seed,model=model,method=method,**metrics([decisions[i] for i in indices],[received[i] for i in indices])))
                        # Detector-only decisions are private and do not contain labels/truth.
                        private= a.raw_dir.resolve()/run_id
                        (private/'detector-scores.json').write_text(json.dumps({method:dict(scores=v[0],decisions=decide(v[0],fitted[method])) for method,v in scored.items()})+'\n')
                        checkpoint()
        write_csv(a.out/'aggregate-metrics.csv',aggregate(reports,cfg['bootstrap_repeats']))
        write_csv(a.out/'paired-cohort.csv',paired)
        if risks:write_csv(a.out/'risk30-per-seed.csv',risks)
        summary.update(status='PR4_EVALUATION_PASSED',metric_rows=len(reports),risk_rows=len(risks),
                       calibration_uses_attacks=False,disjoint_seed_splits=True,
                       total_actual_tx=sum(r['tx_count'] for r in receipts),total_received=sum(r['received'] for r in receipts))
    except Exception as error:
        summary.update(status='PR4_FAILED',error=f'{type(error).__name__}: {error}')
    checkpoint();print(json.dumps(summary,indent=2));return 0 if summary['status']=='PR4_EVALUATION_PASSED' else 2


if __name__=='__main__':raise SystemExit(main())
