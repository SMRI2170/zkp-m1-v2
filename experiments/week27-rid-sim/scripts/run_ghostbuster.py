"""Frozen sparse GhostBuster-style LDPL experiment; no native RF is run here."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time
import numpy as np

from ghostbuster import locate_frames, ranges_from_rss, normal_threshold
from normalize import write_csv
from setup import ROOT, REPO


def receiver_layout(k):
    if k == 1:
        return np.array([[0., 0., 2.]])
    if k in (4, 5):
        return np.array([[0.,0.,2.], [500.,0.,2.], [500.,500.,2.], [0.,500.,2.]] +
                        ([[210.,180.,8.]] if k == 5 else []))
    if k == 12:
        theta = np.linspace(0, 2*np.pi, 12, endpoint=False)
        return np.c_[250+250*np.cos(theta), 250+250*np.sin(theta), np.full(12, 2.)]
    raise ValueError('Undeclared layout')


def observations(cfg, seed, windows, k, sd):
    # Separate RNG streams: K and noise changes do not alter the flight.
    rng = np.random.default_rng(seed)
    start = rng.uniform([80.,80.,40.], [420.,420.,100.], (windows,1,3))
    heading = rng.uniform(0, 2*np.pi, (windows,1))
    velocity = np.stack([3*np.cos(heading), 3*np.sin(heading), np.zeros_like(heading)], axis=-1)
    p = start + velocity*np.arange(cfg['packets_per_window'])[None,:,None]
    receivers = receiver_layout(k)
    distance = np.linalg.norm(p[:,:,None,:]-receivers, axis=-1)
    # First K columns are shared for paired subset comparisons K=4 versus K=5.
    noise = np.random.default_rng(seed+10000).normal(size=(windows,cfg['packets_per_window'],12))[:,:,:k]*sd
    intercept = cfg['nominal_power_dbm']-cfg['pl_d0_db']
    rss = intercept-10*cfg['path_loss_exponent']*np.log10(distance)+noise
    return p, receivers, rss


def estimate(rss, receivers, cfg):
    ranges = ranges_from_rss(rss, cfg['nominal_power_dbm']-cfg['pl_d0_db'], cfg['path_loss_exponent'])
    good = np.isfinite(ranges).all(axis=(1,2))
    n = rss.shape[1]
    if len(receivers)==1:
        return ranges[...,0], good, dict(fit_count=0,nonstationary_fits=0,subset_count=0)
    xyz, audit = locate_frames(ranges.reshape(-1,len(receivers)), receivers,
                              cfg['subset_size'], cfg['solver_max_iterations'])
    good &= audit.pop('frame_stationary').reshape(-1,n).all(axis=1)
    audit.pop('range_residual_rms_m')
    return xyz.reshape(-1,n,3), good, audit


def score(estimates, valid, claims, receivers):
    if len(receivers)==1:
        error = np.abs(estimates-np.linalg.norm(claims-receivers[0],axis=-1))
    else:
        error = np.linalg.norm(estimates-claims,axis=-1)
    scores = np.median(error,axis=1)
    scores[~valid]=np.nan
    return scores


def claims_for(p, receivers, direction, offset):
    radial = p[...,:2]-receivers[0,:2]
    radial /= np.linalg.norm(radial,axis=-1)[...,None]
    if direction=='transverse_rx0':
        radial = np.stack([-radial[...,1],radial[...,0]],axis=-1)
    elif direction!='away_rx0':
        raise ValueError('Undeclared direction')
    q=p.copy(); q[...,:2] += offset*radial
    if not np.allclose(np.linalg.norm(q-p,axis=-1),offset,atol=1.e-9):
        raise ValueError('Invalid displacement norm')
    return q


def record_scores(records, scores, seed, meta, thresholds):
    for policy, threshold in thresholds.items():
        good=np.isfinite(scores); flags=good & (scores>threshold)
        records.append(dict(meta,seed=seed,threshold_policy=policy,threshold_m=threshold,
                            windows=len(scores),scored=int(good.sum()),flags=int(flags.sum()),
                            und=int((~good).sum()),alarm_all=float(flags.mean()),
                            alarm_scored=float(flags[good].mean()) if good.any() else None,
                            eligible=float(good.mean())))


def aggregate(records, repeats):
    from collections import defaultdict
    keys=['source','k','noise_sd_db','direction','attack','offset_m','threshold_policy']
    groups=defaultdict(list)
    for row in records: groups[tuple(row[k] for k in keys)].append(row)
    output=[]
    for group,rows in groups.items():
        record=dict(zip(keys,group),independent_seeds=len(rows),windows=sum(r['windows'] for r in rows),
                    scored=sum(r['scored'] for r in rows),flags=sum(r['flags'] for r in rows),
                    und=sum(r['und'] for r in rows),threshold_m=rows[0]['threshold_m'])
        rng=np.random.default_rng(777)
        for name in ['alarm_all','alarm_scored','eligible']:
            values=np.array([r[name] for r in rows if r[name] is not None])
            if len(values):
                boot=values[rng.integers(0,len(values),(repeats,len(values)))].mean(axis=1)
                record.update({name+'_mean':float(values.mean()), name+'_low':float(np.quantile(boot,.025)),
                               name+'_high':float(np.quantile(boot,.975))})
            else:
                record.update({name+'_mean':None,name+'_low':None,name+'_high':None})
        output.append(record)
    return output


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,default=ROOT/'config/ghostbuster-range.json')
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--raw-dir',type=Path,required=True)
    a=parser.parse_args(); os.umask(0o077)
    if a.out.exists() or a.raw_dir.exists() or not a.raw_dir.resolve().is_relative_to((REPO/'captures').resolve()):
        parser.error('New output and private captures paths required')
    cfg=json.loads(a.config.read_text()); a.out.mkdir(parents=True); a.raw_dir.mkdir(parents=True,mode=0o700)
    if set(cfg['calibration_seeds']) & set(cfg['evaluation_seeds']): raise ValueError('Calibration/evaluation overlap')
    (a.out/'config.json').write_text(json.dumps(cfg,indent=2)+'\n')
    records=[]; receipts=[]; t0=time.time()
    status=dict(status='RUNNING',new_native_rf_cases=0,config_sha256=hashlib.sha256(a.config.read_bytes()).hexdigest())
    try:
        for k,sd in [(1,3.5),(4,3.5),(5,3.5),(12,3.5),(5,1.),(5,6.)]:
            label=f'k{k}-sd{sd:g}'; calibration=[]
            for seed in cfg['calibration_seeds']:
                p,r,rss=observations(cfg,seed,cfg['calibration_windows_per_seed'],k,sd)
                rss=np.trunc(rss) # Published integer truncation convention.
                e,valid,audit=estimate(rss,r,cfg)
                calibration.extend(score(e,valid,p,r))
                receipts.append(dict(stage='normal_calibration',cell=label,seed=seed,**audit))
            thresholds={policy:normal_threshold(calibration,policy,'calibrate_normal') for policy in cfg['thresholds']}
            for seed in cfg['evaluation_seeds']:
                p,r,base=observations(cfg,seed,cfg['evaluation_windows_per_seed'],k,sd)
                original=np.trunc(base); e,valid,audit=estimate(original,r,cfg)
                receipts.append(dict(stage='normal_evaluation',cell=label,seed=seed,**audit))
                # Synthetic truth is retained only in ignored, owner-only captures.
                np.savez_compressed(a.raw_dir/f'{label}-{seed}.npz',position=p,receivers=r,rss=original)
                for direction in cfg['directions']:
                    for offset in cfg['offsets_m']:
                        q=claims_for(p,r,direction,offset)
                        meta=dict(source='synthetic_ldpl',k=k,noise_sd_db=sd,direction=direction,attack='position_only',offset_m=offset)
                        record_scores(records,score(e,valid,q,r),seed,meta,thresholds)
                        if k in (1,5) and sd==3.5:
                            d=np.linalg.norm(p-r[0],axis=-1); dq=np.linalg.norm(q-r[0],axis=-1)
                            change=np.clip(10*cfg['attack_exponent']*np.log10(d/dq),-cfg['power_change_bound_db'],cfg['power_change_bound_db'])
                            altered=np.trunc(base+change[...,None])
                            # Same common power change at every receiver, no
                            # per-receiver power oracle; paired identical noise.
                            if offset==0: ae,av,detail=e,valid,audit
                            else: ae,av,detail=estimate(altered,r,cfg)
                            meta['attack']='power_compensation_rx0'
                            record_scores(records,score(ae,av,q,r),seed,meta,thresholds)
                            receipts.append(dict(stage='power_attack',cell=label,seed=seed,direction=direction,offset_m=offset,**detail))
                write_csv(a.out/'per-seed.csv',records)
                status.update(completed_cell=label,completed_seed=seed,elapsed_s=round(time.time()-t0,3))
                (a.out/'status.json').write_text(json.dumps(status,indent=2)+'\n')
            print(f'COMPLETED {label} elapsed={time.time()-t0:.1f}s',flush=True)
        write_csv(a.out/'aggregate.csv',aggregate(records,cfg['bootstrap_repeats']))
        (a.out/'solver-audit.json').write_text(json.dumps(receipts,indent=2)+'\n')
        status.update(status='COMPLETED',completed_cells=6,evaluation_seeds=len(cfg['evaluation_seeds']),
                      elapsed_s=round(time.time()-t0,3),independent_normal_windows_per_cell=len(cfg['evaluation_seeds'])*cfg['evaluation_windows_per_seed'],
                      calibration_windows_per_cell=len(cfg['calibration_seeds'])*cfg['calibration_windows_per_seed'])
    except Exception as error:
        status.update(status='FAILED',error=f'{type(error).__name__}: {error}')
        (a.out/'solver-audit.json').write_text(json.dumps(receipts,indent=2)+'\n')
    (a.out/'status.json').write_text(json.dumps(status,indent=2)+'\n')
    print(json.dumps(status,indent=2)); return 0 if status['status']=='COMPLETED' else 2


if __name__=='__main__': raise SystemExit(main())
