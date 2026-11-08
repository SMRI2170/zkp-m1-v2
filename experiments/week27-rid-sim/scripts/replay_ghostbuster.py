"""Apply GhostBuster-style NLSE/median to EXISTING audited PR5 RF, no new RF.

The model is learned on normal-only receiver claims, not actual TX power.
This is an adaptation to Dipole/FreeSpace RSS, not the paper's calibrated LDPL.
"""
import argparse
from collections import defaultdict
import hashlib
import json
import os
from pathlib import Path
import time
import numpy as np

from evaluation import signal_dbm
from ghostbuster import locate_frames, ranges_from_rss, normal_threshold
from normalize import write_csv
from observations import detector_projection
from run_ghostbuster import aggregate, record_scores
from run_observer_attack import load_verified
from setup import ROOT, REPO

NODES=[0,2,3,4,5]


def load(directory, receipts):
    spec=json.loads((directory/'spec.json').read_text())
    rows,tx,audit,_=load_verified(directory,spec)
    receipts.append(dict(run=directory.name,source_seed=spec['seed'],tx=len(tx),rx=audit['rx_delivered'],
                         vector_sha256=audit['vector_sha256'],log_sha256=audit['simulation_log_sha256']))
    return detector_projection(rows,directory.name,'same_physical_packet_comparison')


def fit_normal(view):
    design=[]; target=[]
    for row in view:
        value=signal_dbm(row)
        if value is None: continue
        node=NODES.index(row['rx_node_id'])
        basis=[float(i==node) for i in range(5)]
        design.append(basis+[-10*np.log10(np.linalg.norm(np.array(row['claimed_xyz'])-row['rx_xyz']))])
        target.append(value)
    coefficients,_,rank,_=np.linalg.lstsq(design,target,rcond=None)
    if rank!=6 or coefficients[-1]<=0: raise ValueError('Unidentifiable normal LDPL fit')
    return coefficients[:5],float(coefficients[-1])


def scores(view, k, intercepts, exponent, n=5):
    groups=defaultdict(dict)
    for row in view: groups[row['tx_event_id']][row['rx_node_id']]=row
    frames=list(groups.values()) # normalize() already orders physical TX time.
    total=len(frames)//n
    rss=np.full((total,n,k),np.nan); claims=np.zeros((total,n,3))
    receivers=None
    for w in range(total):
        for j in range(n):
            frame=frames[w*n+j]
            received=[frame[node] for node in NODES[:k] if frame[node]['delivered']]
            if received:
                claims[w,j]=received[0]['claimed_xyz']
                if any(r['claimed_xyz']!=received[0]['claimed_xyz'] for r in received): raise ValueError('Mismatched same-packet claims')
            for i,node in enumerate(NODES[:k]):
                value=signal_dbm(frame[node])
                if value is not None: rss[w,j,i]=value
            if len(received)==k: receivers=np.array([frame[node]['rx_xyz'] for node in NODES[:k]])
    good=np.isfinite(rss).all(axis=(1,2))
    output=np.full(total,np.nan)
    diagnostic=dict(windows=total,complete_windows=int(good.sum()),fit_count=0,nonstationary_fits=0)
    if good.any():
        ranges=ranges_from_rss(rss[good],intercepts[:k],exponent)
        xyz,audit=locate_frames(ranges.reshape(-1,k),receivers)
        stationary=audit.pop('frame_stationary').reshape(-1,n).all(axis=1)
        audit.pop('range_residual_rms_m')
        error=np.median(np.linalg.norm(xyz.reshape(-1,n,3)-claims[good],axis=-1),axis=1)
        output[np.flatnonzero(good)[stationary]]=error[stationary]
        diagnostic.update(audit)
    return output,diagnostic


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,default=REPO/'captures/issue75-full-20261108-a')
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();os.umask(0o077)
    if a.out.exists():p.error('Use a new output path')
    a.out.mkdir(parents=True);receipts=[];records=[];diagnostics=[];t0=time.time()
    cfg=json.loads((ROOT/'config/ghostbuster-range.json').read_text())
    status=dict(status='RUNNING',new_native_rf_cases=0,mode='existing_native_RF_reanalysis')
    try:
        intercepts,exponent=fit_normal(load(a.source/'default-train-normal',receipts))
        for k in [4,5]:
            calibration=[]
            for seed in cfg['calibration_seeds']:
                name=f'default-cal-strong-{seed}'
                values,audit=scores(load(a.source/name,receipts),k,intercepts,exponent)
                calibration.extend(values);diagnostics.append(dict(run=name,k=k,**audit))
            thresholds={policy:normal_threshold(calibration,policy,'calibrate_normal') for policy in cfg['thresholds']}
            for seed in cfg['evaluation_seeds']:
                plans=[('normal',0,f'default-eval-strong-{seed}-normal')]
                plans += [(case,offset,f'default-eval-strong-{seed}-{case}-offset{offset}-bound{bound}')
                          for offset in [30,100] for case,bound in [('position_only',0),('reference_rx0',10),('schedule_aware',10),('schedule_blind',10)]]
                for case,offset,name in plans:
                    values,audit=scores(load(a.source/name,receipts),k,intercepts,exponent)
                    diagnostics.append(dict(run=name,k=k,**audit))
                    meta=dict(source='existing_INET_FreeSpace_Dipole',k=k,noise_sd_db='not_Gaussian',
                              direction='x',attack=case,offset_m=offset)
                    record_scores(records,values,seed,meta,thresholds)
                write_csv(a.out/'per-seed.csv',records)
                status.update(completed_k=k,completed_seed=seed,elapsed_s=round(time.time()-t0,3))
                (a.out/'status.json').write_text(json.dumps(status,indent=2)+'\n')
            print(f'REPLAYED K={k} elapsed={time.time()-t0:.1f}s',flush=True)
        write_csv(a.out/'aggregate.csv',aggregate(records,cfg['bootstrap_repeats']))
        (a.out/'source-receipts.json').write_text(json.dumps(receipts,indent=2)+'\n')
        (a.out/'solver-audit.json').write_text(json.dumps(diagnostics,indent=2)+'\n')
        (a.out/'normal-model.json').write_text(json.dumps(dict(
            fit_role='train_normal',training_seed=501,receiver_intercepts_db=intercepts.tolist(),exponent=exponent,
            nominal_power='Not provided by truth. Normal mean power is absorbed into fitted intercepts.',
            adaptation='Per-receiver intercepts/shared exponent and known -100dBm background subtraction.'),indent=2)+'\n')
        status.update(status='COMPLETED',elapsed_s=round(time.time()-t0,3),source_cases=len({r['run'] for r in receipts}),
                      independent_evaluation_flights=20,nonoverlapping_windows_per_flight=4)
    except Exception as error:status.update(status='FAILED',error=f'{type(error).__name__}: {error}')
    (a.out/'status.json').write_text(json.dumps(status,indent=2)+'\n');print(json.dumps(status,indent=2))
    return 0 if status['status']=='COMPLETED' else 2


if __name__=='__main__':raise SystemExit(main())
