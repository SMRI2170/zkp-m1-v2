"""PR5 MLAT audit of hash-verified PR4 RF records; NO new RF simulation.

The pinned upstream solver stays unchanged. Independent instrumented standard
least squares exposes its objective/termination, and a separately labelled
multi-start variant selects lowest accepted cost, never lowest truth error.
"""
import argparse
from collections import defaultdict
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import sys

os.environ.setdefault('MPLBACKEND','Agg')
import numpy as np
from scipy.optimize import least_squares

from evaluation import calibrated_threshold,decide,metrics
from normalize import normalize,read_vectors,write_csv
from observations import detector_projection
from run_power import target_events
from run_observer_attack import bootstrap
from scene import RX_POSITIONS
from setup import ROOT,REPO


def instrument(receivers,rssi,initial):
    distances=np.maximum(np.linalg.norm(receivers-initial,axis=1),.1)
    inferred=float(np.median(rssi+20*np.log10(distances)+40.04))
    x0=np.r_[initial,inferred]
    def objective(parameters):
        d=np.maximum(np.linalg.norm(receivers-parameters[:3],axis=1),.1)
        return rssi-(parameters[3]-20*np.log10(d)-40.04)
    result=least_squares(objective,x0,bounds=([-np.inf,-np.inf,-np.inf,-50],[np.inf,np.inf,np.inf,50]),method='trf',max_nfev=100)
    accepted=bool(result.success or result.cost<100)
    return dict(position=result.x[:3].tolist(),estimated_power_dbm=float(result.x[3]),
                cost=float(result.cost),residual_rms_db=float(np.sqrt(np.mean(result.fun**2))),
                success=bool(result.success),accepted=accepted,status=int(result.status),nfev=int(result.nfev),optimality=float(result.optimality),
                near_power_bound=bool(min(abs(result.x[3]+50),abs(result.x[3]-50))<1e-5),
                negative_height=bool(result.x[2]<0))


def geometry_diagnostic(receivers,point):
    delta=point-receivers;d=np.maximum(np.linalg.norm(delta,axis=1),.1)
    jac=np.c_[(20/math.log(10))*delta/(d[:,None]**2),-np.ones(len(receivers))]
    singular=np.linalg.svd(jac,compute_uv=False)
    condition=float(singular[0]/singular[-1]) if singular[-1]>np.finfo(float).eps*singular[0]*max(jac.shape) else None
    norms=np.linalg.norm(jac,axis=0)
    if np.any(norms==0):scaled=None
    else:
        values=np.linalg.svd(jac/norms,compute_uv=False)
        scaled=float(values[0]/values[-1]) if values[-1]>np.finfo(float).eps*values[0]*max(jac.shape) else None
    return dict(jacobian_condition=condition,column_scaled_condition=scaled,rank=int(np.linalg.matrix_rank(jac)))


def start_points(claim,receivers):
    # All starts use received claims/receiver geometry only, never true XYZ.
    center=receivers.mean(axis=0)
    return dict(claim=claim,x_plus100=claim+[100,0,0],x_minus100=claim+[-100,0,0],
                y_plus100=claim+[0,100,0],z_plus100=claim+[0,0,100],
                reflected_about_mean_rx_height=np.array([claim[0],claim[1],2*center[2]-claim[2]]),
                receiver_center_plus50=center+[0,0,50])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-raw',type=Path,default=REPO/'captures/issue70-evaluation-20261108-full-a')
    p.add_argument('--private-out',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--workspace',type=Path,default=REPO/'.cache/issue75')
    a=p.parse_args();os.umask(0o077)
    if not a.private_out.resolve().is_relative_to((REPO/'captures').resolve()):p.error('Private derived estimates require captures/')
    if a.out.exists() or a.private_out.exists():p.error('Preserve evidence; use new paths')
    a.out.mkdir(parents=True);a.private_out.mkdir(parents=True,mode=0o700)
    sys.path.insert(0,str(a.workspace.resolve()/'uli-net-sim'))
    from evaluations.detectors import multilaterate_with_tx_power
    cfg=json.loads((ROOT/'config/observer-attack.json').read_text())
    records=[];source_receipts=[];scores=defaultdict(list);starts_public=[];disagreements=[]
    status=dict(status='RUNNING',dataset_source='simulation',new_rf_runs=0,reused_rf_scenes=0)
    plans=[('cal',seed,0) for seed in cfg['calibration_seeds']]+[('eval',seed,offset) for seed in cfg['evaluation_seeds'] for offset in [0,100]]
    try:
        for role,seed,offset in plans:
            run_id=f'main-{role}-strong-fixed-{seed}'+(f'-offset{offset}' if role=='eval' else '')
            directory=a.source_raw/run_id;audit=json.loads((directory/'audit.json').read_text())
            if hashlib.sha256((directory/'run.vec').read_bytes()).hexdigest()!=audit['vector_sha256']:raise ValueError('Original PR4 vector hash changed')
            spec=json.loads((directory/'spec.json').read_text())
            config=dict(seed=seed,tx_host=1,rx_hosts=list(RX_POSITIONS),observer_regime='same_packet_multisite_comparison_only',phy_model='INET FreeSpace/Dipole')
            rows,tx,gcs,_=normalize(target_events(read_vectors(directory/'run.vec'),receivers=tuple(RX_POSITIONS)),spec['case'],config)
            tx=sorted(tx,key=lambda r:r['tx_time']);by_packet=defaultdict(list)
            for r in rows:by_packet[r['tx_event_id']].append(r)
            start_groups=defaultdict(list)
            for index,t in enumerate(tx):
                for n in [4,5]:
                    selected=[r for r in by_packet[t['tx_event_id']] if r['rx_node_id'] in list(RX_POSITIONS)[:n] and r['delivered']]
                    if len(selected)!=n:raise ValueError('Expected PR4 strong-link complete reception')
                    projection=detector_projection(selected,run_id,'same_physical_packet_comparison')
                    receivers=np.asarray([r['rx_xyz'] for r in projection]);rssi=np.asarray([r['rssi_dbm'] for r in projection]);claim=np.asarray(projection[0]['claimed_xyz'])
                    original,power=multilaterate_with_tx_power(receivers,rssi,claim)
                    candidates=[]
                    for init_name,initial in start_points(claim,receivers).items():
                        result=instrument(receivers,rssi,initial)
                        # Truth is used AFTER solving only for evaluation.
                        result.update(role=role,seed=seed,offset_m=offset,receivers=n,index=index,initialization=init_name,
                                      error_to_claim_m=float(np.linalg.norm(np.asarray(result['position'])-claim)),
                                      error_to_truth_m=float(np.linalg.norm(np.asarray(result['position'])-np.asarray(t['true_tx_xyz']))),
                                      power_error_to_truth_db=result['estimated_power_dbm']-t['tx_power_dbm_truth_only'])
                        result.update(geometry_diagnostic(receivers,np.asarray(result['position'])))
                        candidates.append(result);records.append(result);start_groups[(n,init_name)].append(result)
                    first=candidates[0]
                    if (original is None)!= (not first['accepted']):raise ValueError('Instrumented acceptance differs from upstream')
                    difference=float(np.linalg.norm(original-np.asarray(first['position']))) if original is not None else 0.
                    if difference>1e-6 or (power is not None and abs(power-first['estimated_power_dbm'])>1e-6):raise ValueError('Instrumented baseline differs from unmodified upstream')
                    disagreements.append(difference)
                    accepted=[r for r in candidates if r['accepted']]
                    best=min(accepted,key=lambda r:r['cost']) if accepted else None
                    scores[(role,seed,offset,f'upstream{n}')].append(first['error_to_claim_m'] if first['accepted'] else None)
                    scores[(role,seed,offset,f'multistart{n}')].append(best['error_to_claim_m'] if best else None)
            for (n,initial),group in start_groups.items():
                record=dict(role=role,seed=seed,offset_m=offset,receivers=n,initialization=initial,count=len(group),
                            converged=sum(r['success'] for r in group),accepted=sum(r['accepted'] for r in group),
                            fallback_cost_acceptances=sum(r['accepted'] and not r['success'] for r in group),power_bound_hits=sum(r['near_power_bound'] for r in group),
                            negative_heights=sum(r['negative_height'] for r in group),rank_deficient=sum(r['rank']<4 for r in group))
                for field in ['error_to_claim_m','error_to_truth_m','estimated_power_dbm','power_error_to_truth_db','cost','residual_rms_db','nfev','optimality','jacobian_condition','column_scaled_condition']:
                    values=[r[field] for r in group if r[field] is not None]
                    record[f'{field}_median']=statistics.median(values) if values else None
                    record[f'{field}_max']=max(values) if values else None
                starts_public.append(record)
            source_receipts.append(dict(run_id=run_id,vector_sha256=audit['vector_sha256'],tx_count=len(tx),new_rf_run=False))
            status['reused_rf_scenes']=len(source_receipts)
            (a.out/'summary.json').write_text(json.dumps(status,indent=2)+'\n')
        thresholds={method:calibrated_threshold([x for (role,seed,offset,m),values in scores.items() if role=='cal' and m==method for x in values],'calibrate_normal') for method in ['upstream4','upstream5','multistart4','multistart5']}
        prior=json.loads((REPO/'week27/results/uli-net-sim-evaluation-20261108-full-b/thresholds.json').read_text())['main:strong:fixed']
        for n in [4,5]:
            if abs(thresholds[f'upstream{n}']-prior[f'MLAT{n}'])>1e-6:raise ValueError('Original normal MLAT threshold failed reproduction')
        output=[];aggregate=[]
        for (role,seed,offset,method),values in scores.items():
            if role!='eval':continue
            output.append(dict(seed=seed,offset_m=offset,method=method,**metrics(decide(values,thresholds[method]),[True]*len(values))))
        for offset,method in itertools.product([0,100],thresholds):
            group=[r for r in output if r['offset_m']==offset and r['method']==method];record=dict(offset_m=offset,method=method)
            for field in ['alarm_scored','alarm_all_tx','und_rate']:
                record.update({f'{field}_{k}':v for k,v in bootstrap([r[field] for r in group],1000).items()})
            aggregate.append(record)
        write_csv(a.out/'solver-start-summary.csv',starts_public);write_csv(a.out/'per-seed-metrics.csv',output);write_csv(a.out/'aggregate-metrics.csv',aggregate)
        (a.out/'thresholds.json').write_text(json.dumps(thresholds,indent=2)+'\n')
        (a.out/'source-receipts.json').write_text(json.dumps(source_receipts,indent=2)+'\n')
        (a.private_out/'solver-truth-results.json').write_text(json.dumps(records)+'\n')
        status.update(status='MLAT_DIAGNOSTICS_PASSED',instrumented_solver_runs=len(records),upstream_position_max_difference_m=max(disagreements),
                      normal_only_calibration=True,evaluation_seeds=20,
                      note='Original upstream unchanged. Multi-start lowest accepted cost is a separately labelled method; no truth-based initialization or selection.')
    except Exception as error:status.update(status='MLAT_DIAGNOSTICS_FAILED',error=f'{type(error).__name__}: {error}')
    (a.out/'summary.json').write_text(json.dumps(status,indent=2)+'\n');print(json.dumps(status,indent=2));return 0 if status['status']=='MLAT_DIAGNOSTICS_PASSED' else 2


if __name__=='__main__':
    import itertools
    raise SystemExit(main())
