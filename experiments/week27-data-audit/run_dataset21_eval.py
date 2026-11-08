"""D1 input/availability experiment and gated GhostBuster adapter evaluation.

An unavailable geometry produces NOT_RUN + null FPR/TPR, never a fake zero.
Nearest-time multisite results, if enabled by verified metadata, are explicitly
a static-position approximation, NOT same-transmission power cancellation.
"""
import argparse
from collections import defaultdict
import hashlib
import json
import os
from pathlib import Path
import sys
import numpy as np
from aerpaw21_local import write_table
from dataset21_adapter import load_d1,geometry,groups,local_xy

REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO/'experiments/week27-rid-sim/scripts'))
from ghostbuster import window_scores,normal_threshold


def designs(cfg):
    rows=[]
    for k in cfg['receiver_counts']:
        for span in cfg['time_span_limits_s']:rows.append(dict(k=k,max_span_s=span,lag_s=0.,missing=0.,seed=801))
    for k in [1,4,5]:
        for missing in cfg['missing_rates'][1:]:
            for seed in cfg['missing_seeds']:rows.append(dict(k=k,max_span_s=.2,lag_s=0.,missing=missing,seed=seed))
    for k in [4,5]:
        for lag in cfg['observation_lags_s'][1:]:rows.append(dict(k=k,max_span_s=.2,lag_s=lag,missing=0.,seed=801))
    return rows


def real_rss_diagnostics(streams):
    blocks=[];splits=[]
    for name,s in streams.items():
        for role in ['train','calibrate','evaluate','embargo']:
            ids=np.flatnonzero(s['role']==role)
            splits.append(dict(station=name,role=role,source_rows=len(ids)))
        # Aggregate only; no raw RSS, absolute timestamp or position is public.
        for b in np.unique((s['elapsed']//20).astype(int)):
            mask=(s['elapsed']//20).astype(int)==b
            for ch in [0,1]:
                values=s['rss'][mask,ch]
                blocks.append(dict(station=name,channel=ch+1,elapsed_start_s=20*int(b),count=len(values),
                                   median_rss=float(np.median(values)),q25_rss=float(np.quantile(values,.25)),q75_rss=float(np.quantile(values,.75))))
    return blocks,splits


def synthesize_inputs(streams,cfg,private):
    """Executable input generation, NOT geometric detection performance.

    Horizontal translations in a declared local metric projection do not need
    a ground receiver's position. Targeted power compensation DOES need it and
    remains gated. Raw RSS is retained separately, unchanged.
    """
    first=streams['LW1'];lo=float(first['lon'][0]);la=float(first['lat'][0])
    rows=[]
    for name,s in streams.items():
        xyz=np.c_[local_xy(s['lon'],s['lat'],lo,la),s['z']]
        s['input_local_xyz']=xyz
        claims=np.repeat(xyz[:,None,:],len(cfg['offsets_m']),axis=1)
        claims[:,:,0]+=np.asarray(cfg['offsets_m'])[None,:]
        shifts=np.stack([np.zeros(len(xyz)),np.full(len(xyz),6.),6*np.sin(np.pi*s['elapsed'])],axis=1)
        modified=s['rss'][:,None,:]+shifts[:,:,None]
        if not np.array_equal(modified[:,0,:],s['rss']):raise ValueError('Position-only input changed measured RSS')
        for j,distance in enumerate(cfg['offsets_m']):
            error=float(np.max(abs(np.linalg.norm(claims[:,j]-xyz,axis=1)-distance)))
            if error>1.e-8:raise ValueError('Synthetic displacement norm incorrect')
            rows.append(dict(station=name,offset_m=distance,observations=len(xyz),maximum_displacement_error_m=error,
                             position_only_measured_rss_unchanged=True,constant_and_timevarying_power_inputs_generated=True,
                             reference0_compensation_generated=False,position_detection_executed=False))
        np.savez_compressed(private/(name+'-synthetic-inputs.npz'),true_local_xyz=xyz,claimed_local_xyz=claims,
                            measured_rss=s['rss'],synthetically_perturbed_rss=modified,elapsed=s['elapsed'],roles=s['role'])
    return rows


def fit_model(streams,receivers,channel):
    design=[];target=[]
    for j,s in enumerate(streams.values()):
        mask=s['role']=='train';distance=np.linalg.norm(s['xyz'][mask]-receivers[j],axis=1)
        if (distance<=1).any():raise ValueError('Training geometry has zero/near-zero range')
        basis=np.zeros((mask.sum(),6));basis[:,j]=1;basis[:,-1]=-10*np.log10(distance)
        design.append(basis);target.append(s['rss'][mask,channel])
    x=np.concatenate(design);y=np.concatenate(target)
    coef,_,rank,_=np.linalg.lstsq(x,y,rcond=None)
    if rank!=6 or not np.isfinite(coef).all() or coef[-1]<=0:raise ValueError('Normal-only shared LDPL exponent is not identifiable/positive')
    return coef[:5],float(coef[-1])


def decision_bins(streams,g,role,window_s=5.):
    reference=streams['LW1'];times=reference['elapsed'][g['reference_indices']]
    duration=max(float(s['elapsed'][-1]) for s in streams.values())
    limits={'train':(0,.4),'calibrate':(.45,.65),'evaluate':(.7,1)}[role]
    return [(b,np.flatnonzero((times>=b*window_s)&(times<(b+1)*window_s)&g['accepted']))
            for b in range(int(np.ceil(limits[0]*duration/window_s)),int(np.floor(limits[1]*duration/window_s)))]


def make_input(streams,receivers,design,role,channel,offset,power):
    g=groups(streams,role=role,**design);k=design['k'];total=g['total'];n=5
    rss=np.full((total,k),np.nan)
    reference=streams['LW1'];positions=reference['xyz'] if 'xyz' in reference else reference['input_local_xyz']
    claims=positions[g['reference_indices']].copy();claims[:,0]+=offset
    for j,s in enumerate(list(streams.values())[:k]):
        idx=g['selected'][:,j];values=s['rss'][idx,channel].copy();positions=s['xyz'] if 'xyz' in s else s['input_local_xyz'];p=positions[idx];q=p.copy();q[:,0]+=offset
        if power=='constant_plus6db':values+=6
        elif power=='sinusoid_6db_period2s':values+=6*np.sin(np.pi*s['elapsed'][idx])
        elif power=='reference0_compensation_clip10db_n2':
            d=np.linalg.norm(p-receivers[0],axis=1);dq=np.linalg.norm(q-receivers[0],axis=1)
            values+=np.clip(20*np.log10(np.maximum(d,1)/np.maximum(dq,1)),-10,10)
        elif power!='unchanged':raise ValueError('Unknown declared power condition')
        rss[g['accepted'],j]=values[g['accepted']]
    bins=decision_bins(streams,g,role);out_rss=np.full((len(bins),n,k),np.nan);out_claims=np.zeros((len(bins),n,3))
    for w,(_,ids) in enumerate(bins):
        if len(ids)>=n:
            out_rss[w]=rss[ids[:n]];out_claims[w]=claims[ids[:n]]
    return out_rss,out_claims,g


def metrics(scores,threshold):
    good=np.isfinite(scores);flag=good&(scores>threshold)
    return dict(windows=len(scores),scored=int(good.sum()),flags=int(flag.sum()),und=int((~good).sum()),
                alarm_all=float(flag.mean()) if len(scores) else None,
                alarm_scored=float(flag[good].mean()) if good.any() else None,
                fnr_scored=float((~flag[good]).mean()) if good.any() else None,
                und_rate=float((~good).mean()) if len(scores) else None)


def evaluate(streams,receivers,cfg,private,allow_nearest_time=False):
    output=[];model=[]
    # Sparse geometric design: K, then missing, then observation lag; no full
    # Cartesian product. Calibration split is separate from every evaluation.
    matrix=[dict(k=k,max_span_s=.2,lag_s=0.,missing=0.,seed=801) for k in cfg['receiver_counts']]
    matrix += [r for r in designs(cfg) if r['missing']>0 or r['lag_s']>0]
    for ch in [0,1]:
        try:intercepts,n=fit_model(streams,receivers,ch)
        except ValueError as e:
            output.append(dict(channel=ch+1,k=0,offset_m=None,power='none',status='NOT_RUN_NORMAL_MODEL_INVALID',reason=str(e),fpr=None,tpr=None,und_rate=None));continue
        model.append(dict(channel=ch+1,role='train_only',intercepts=intercepts.tolist(),exponent=n))
        for design in matrix:
            k=design['k']
            if k in [2,3]:
                output.append(dict(channel=ch+1,**design,offset_m=None,power='none',status='NOT_RUN_K2_K3_UNSUPPORTED_3D',fpr=None,tpr=None,und_rate=None));continue
            if k>1 and not allow_nearest_time:
                output.append(dict(channel=ch+1,**design,offset_m=None,power='none',status='NOT_RUN_SAME_TRANSMISSION_UNVERIFIED',fpr=None,tpr=None,und_rate=None));continue
            kwargs=dict(bounds=cfg['solver_bounds_m'],start_heights=cfg['solver_start_heights_m'])
            calibration_design=dict(design,lag_s=0.,missing=0.,seed=801)
            cr,cq,_=make_input(streams,receivers,calibration_design,'calibrate',ch,0.,'unchanged')
            calibration,_=window_scores(cr,cq,receivers[:k],intercepts[:k],n,**kwargs)
            if np.isfinite(calibration).sum()<cfg['minimum_normal_calibration_windows']:
                output.append(dict(channel=ch+1,**design,offset_m=None,power='none',status='NOT_RUN_INSUFFICIENT_NORMAL_CALIBRATION',fpr=None,tpr=None,und_rate=None));continue
            threshold=normal_threshold(calibration,cfg['threshold_policy'],'calibrate_normal')
            powers=cfg['power_conditions'] if not design['lag_s'] and not design['missing'] else ['unchanged','sinusoid_6db_period2s']
            for power in powers:
                nr,nq,_=make_input(streams,receivers,design,'evaluate',ch,0.,power)
                normal,_=window_scores(nr,nq,receivers[:k],intercepts[:k],n,**kwargs);fpr=metrics(normal,threshold)
                for offset in cfg['offsets_m']:
                    rss,claim,g=make_input(streams,receivers,design,'evaluate',ch,offset,power)
                    scores,solver=window_scores(rss,claim,receivers[:k],intercepts[:k],n,**kwargs);m=metrics(scores,threshold)
                    output.append(dict(channel=ch+1,**design,offset_m=offset,power=power,status='EXECUTED_NEAREST_TIME_APPROXIMATION' if k>1 else 'EXECUTED_SINGLE_RECEIVER',
                                       fpr=fpr['alarm_all'],tpr=m['alarm_all'],fpr_scored=fpr['alarm_scored'],tpr_scored=m['alarm_scored'],normal_und_rate=fpr['und_rate'],threshold_m=threshold,
                                       normal_windows=fpr['windows'],normal_scored=fpr['scored'],normal_flags=fpr['flags'],**m,
                                       physical_same_packet=False,independent_flights=1))
                    # Only the private file contains per-window scores/indices.
                    tag=f'ch{ch+1}-k{k}-lag{design["lag_s"]}-miss{design["missing"]}-seed{design["seed"]}-{power}-{offset}'
                    np.savez_compressed(private/(tag+'.npz'),scores=scores,normal_scores=normal,reference_indices=g['reference_indices'],source_indices=g['selected'])
    return output,model


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--audit',type=Path,required=True)
    p.add_argument('--config',type=Path,default=Path(__file__).with_name('config_dataset21_eval.json'))
    p.add_argument('--receivers',type=Path);p.add_argument('--private-out',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--allow-nearest-time-approximation',action='store_true',help='Explicit additional model, not original same-transmission evidence')
    a=p.parse_args();os.umask(0o077)
    for path in [a.source,a.private_out]+([a.receivers] if a.receivers else []):
        if not path.resolve().is_relative_to((REPO/'captures').resolve()):p.error('Source, receiver metadata and private output must be inside ignored captures')
    if a.out.exists() or a.private_out.exists():p.error('New output paths required')
    a.out.mkdir(parents=True);a.private_out.mkdir(parents=True,mode=0o700)
    cfg=json.loads(a.config.read_text());(a.out/'config.json').write_text(json.dumps(cfg,indent=2)+'\n')
    summary=dict(status='RUNNING',raw_source='D1_real_measured_RSS',new_rf_runs=0,d3_used=False,geometric_detection_executed=False)
    try:
        streams,source=load_d1(a.source.resolve(),json.loads(a.audit.read_text()))
        receivers,gate=geometry(streams,a.receivers)
        injections=synthesize_inputs(streams,cfg,a.private_out)
        write_table(a.out/'synthetic-input-checks.csv',injections)
        shapes=[]
        for k in cfg['receiver_counts']:
            design=dict(k=k,max_span_s=.2,lag_s=0.,missing=0.,seed=801)
            rss,claim,_=make_input(streams,receivers,design,'evaluate',0,20.,'unchanged')
            shapes.append(dict(k=k,decision_windows=len(rss),observations_per_window=rss.shape[1],rss_columns=rss.shape[2],claim_components=claim.shape[2],
                               shape_compatible=True,receiver_geometry_available=receivers is not None,actual_ghostbuster_scoring_executed=False))
        write_table(a.out/'input-shapes.csv',shapes)
        blocks,splits=real_rss_diagnostics(streams);write_table(a.out/'rss-time-blocks.csv',blocks);write_table(a.out/'split-counts.csv',splits)
        availability=[]
        for design in designs(cfg):
            g=groups(streams,role='evaluate',**design);n=cfg['packets_per_window'];bins=decision_bins(streams,g,'evaluate');windows=len(bins)
            availability.append(dict(design,reference_rows=g['total'],candidate_complete=g['candidate_complete'],
                                     unique_complete=g['unique_complete'],source_reuse_removed=g['source_reuse_removed'],
                                     candidate_rate=g['unique_complete']/g['total'],reference_windows=windows,
                                     complete_windows=sum(len(ids)>=n for _,ids in bins),physical_same_packet=False))
        write_table(a.out/'availability.csv',availability)
        if receivers is None:
            records=[dict(k=k,offset_m=distance,power=power,status='NOT_RUN_MISSING_RECEIVER_GEOMETRY',fpr=None,tpr=None,und_rate=None)
                     for k in cfg['receiver_counts'] for distance in cfg['offsets_m'] for power in cfg['power_conditions']]
            model=[]
        else:
            records,model=evaluate(streams,receivers,cfg,a.private_out,a.allow_nearest_time_approximation)
        # Heterogeneous status rows keep absent metrics empty, never fill with0.
        fields=list(dict.fromkeys(key for row in records for key in row))
        write_table(a.out/'metrics.csv',[{k:r.get(k) for k in fields} for r in records])
        executed=sum(str(r['status']).startswith('EXECUTED') for r in records)
        summary.update(status='COMPLETED' if executed else 'INPUT_EXPERIMENT_COMPLETE_GEOMETRIC_EVALUATION_NOT_RUN',
                       source=source,geometry_gate=gate,availability_cells=len(availability),status_rows=len(records),
                       geometric_detection_executed=executed>0,executed_detection_cells=executed,normal_models=model,
                       synthetic_position_input_cases=len(injections),targeted_power_compensation_generated=any(r.get('power')=='reference0_compensation_clip10db_n2' and str(r['status']).startswith('EXECUTED') for r in records),
                       config_sha256=hashlib.sha256(a.config.read_bytes()).hexdigest(),
                       code_sha256={f:hashlib.sha256(Path(__file__).with_name(f).read_bytes()).hexdigest() for f in ['run_dataset21_eval.py','dataset21_adapter.py']},
                       limitations=['One real flight; stochastic missing-mask seeds do not create independent flights',
                                    'Candidate availability is not detector eligibility, TPR or FPR',
                                    'Normal synthetic RID claims copy measured GPS; this is not received RID payload data',
                                    'Power perturbations/missingness/extra observation lag are synthetic; native RSS is measured'])
    except Exception as e:
        summary.update(status='FAILED',error=f'{type(e).__name__}: {e}');raise
    finally:(a.out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,indent=2));return 0 if summary['geometric_detection_executed'] else 2


if __name__=='__main__':raise SystemExit(main())
