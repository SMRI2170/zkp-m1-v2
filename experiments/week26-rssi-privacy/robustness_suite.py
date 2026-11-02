"""Stress-test the assumptions of Week26, with separate aggregate outputs.

Indoor empirical BLE residual injection is not a UAV measurement. No genuine
coordinates, capture rows, keys or proofs are written outside ignored captures/.
"""
import os
for _key in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS']:
    os.environ[_key]='1'
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import platform
import resource
import sys
import time

import numpy as np
from scipy.optimize import brentq
from scipy.stats import norm
from threadpoolctl import threadpool_limits
from recheck_ble import load, download
from sensitivity_suite import rng_for,receiver_sites,profiled_power_score,power_forecast


def residual_pools(data,cal_parity):
    """Keep baseline rows and scoring rows separate, then hold out sectors."""
    pools=[[],[]];sectors=[set(),set()]
    for groups in data.values():
        for (sector,beacon),values in groups.items():
            baseline=float(np.median(values[:50]))
            index=0 if sector%2==cal_parity else 1
            pools[index].extend(v-baseline for v in values[50:])
            sectors[index].add(sector)
    assert not sectors[0]&sectors[1]
    return [np.sort(np.asarray(v,float)) for v in pools],sectors


def pool_statistics(pool):
    return {'count':len(pool),'mean_db':float(pool.mean()),'rms_db':float(np.sqrt(np.mean(pool**2))),
            'abs_p95_db':float(np.quantile(np.abs(pool),.95))}


def empirical_sync_study(cfg,pools,seed):
    c=cfg['empirical_sync'];nc=c['calibration_events'];nt=c['test_events'];b=10*c['assumed_exponent'];rows=[]
    for parity in [0,1]:
        cal_pool,test_pool=pools[parity];rng=rng_for(seed,511+parity)
        points=np.column_stack([rng.uniform(-100,100,(nc+nt,2)),rng.uniform(5,70,nc+nt)])
        common=-42+rng.normal(0,8,nc+nt)
        bias=rng.normal(0,.8,max(c['receivers']))
        uniforms=rng.uniform(1e-8,1-1e-8,(nc+nt,max(c['receivers'])))
        normal_noise=norm.ppf(uniforms)
        empirical=np.empty_like(uniforms)
        empirical[:nc]=cal_pool[(uniforms[:nc]*len(cal_pool)).astype(int)]
        empirical[nc:]=test_pool[(uniforms[nc:]*len(test_pool)).astype(int)]
        rms=float(np.sqrt(np.mean(cal_pool**2)))
        headings=rng.uniform(0,2*np.pi,nc+nt);angles=rng.uniform(0,2*np.pi,nt)
        for noise_name in c['noise_models']:
            noise=normal_noise*(2 if noise_name=='gaussian2' else rms) if noise_name!='empirical' else empirical
            for receivers in c['receivers']:
                sites=receiver_sites(receivers,c['radius_m'])
                vectors=sites[None,:,:]-points[:,None,:]
                distance=np.linalg.norm(vectors,axis=2)
                direction=np.arctan2(vectors[:,:,1],vectors[:,:,0])-headings[:,None]
                raw=common[:,None]-b*np.log10(distance)+noise[:,:receivers]+bias[:receivers]
                cal_score=profiled_power_score(raw[:nc],distance[:nc],b)
                threshold=float(np.quantile(cal_score,1-c['target_calibration_fpr']))
                for environment in c['environments']:
                    test_r=raw[nc:].copy()
                    if environment in ['gain_shift6','combined_shift']:test_r+=6*np.cos(direction[nc:])
                    if environment in ['exponent_shift05','combined_shift']:test_r-=5*np.log10(distance[nc:])
                    normal_score=profiled_power_score(test_r,distance[nc:],b)
                    normal_alarms=int((normal_score>threshold).sum())
                    for delta in c['claim_shifts_m']:
                        claim=points[nc:].copy();claim[:,:2]+=delta*np.column_stack([np.cos(angles),np.sin(angles)])
                        claim_distance=np.linalg.norm(claim[:,None,:]-sites[None,:,:],axis=2)
                        score=profiled_power_score(test_r,claim_distance,b)
                        rows.append(dict(seed=seed,calibration_sector_parity=parity,noise_model=noise_name,receivers=receivers,
                                         environment=environment,delta_m=delta,tested=nt,alarms=int((score>threshold).sum()),
                                         matched_normal_alarms=normal_alarms,threshold_db=threshold,calibration_rms_db=rms))
    return rows


def huber_location(values,threshold):
    if threshold<=0:raise ValueError('Huber threshold must be positive')
    low=float(np.min(values));high=float(np.max(values))
    if low==high:return low
    return float(brentq(lambda location:np.clip(values-location,-threshold,threshold).sum(),low,high))


def nuisance_estimates(residuals):
    """External clean ID x flight x packet residuals only."""
    ids,flights,packets=residuals.shape
    a=float(residuals.mean())
    noise=float(np.var(residuals,axis=2,ddof=1).mean())
    flight=max(float(np.var(residuals.mean(axis=2),axis=1,ddof=1).mean()-noise/packets),0.)
    identity=max(float(np.var(residuals.mean(axis=(1,2)),ddof=1)-flight/flights-noise/(flights*packets)),0.)
    centered=residuals-residuals.mean(axis=(1,2),keepdims=True)
    robust_scale=max(float(1.4826*np.median(np.abs(centered-np.median(centered)))),.01)
    return a,noise,flight,identity,robust_scale


def corruption_masks(rng,ids,flights,packets,patterns,fraction):
    # Separate RNG supplied by caller makes masks nested across fraction values.
    if patterns=='random_rows':
        rank=np.argsort(rng.uniform(size=(ids,flights*packets)),axis=1)
        mask=np.zeros((ids,flights*packets),bool)
        np.put_along_axis(mask,rank[:,:round(fraction*flights*packets)],True,axis=1)
        return mask
    if patterns!='whole_flights':raise ValueError(patterns)
    rank=np.argsort(rng.uniform(size=(ids,flights)),axis=1)
    mask=np.zeros((ids,flights),bool)
    np.put_along_axis(mask,rank[:,:round(fraction*flights)],True,axis=1)
    return np.repeat(mask,packets,axis=1)


def poisoning_study(cfg,seed):
    c=cfg['poisoning'];rows=[];ext=c['external_ids'];ids=c['target_ids']
    ef=c['enrollment_flights'];em=c['events_per_flight'];tf=c['test_flights'];tm=c['test_events_per_flight'];b=22.
    for flight_sd in c['flight_sd_db']:
        rng=rng_for(seed,611)
        external_alpha=rng.normal(0,c['identity_sd_db'],ext)
        ext_res=-42+external_alpha[:,None,None]+rng.normal(0,flight_sd,(ext,ef,1))+rng.normal(0,c['measurement_sd_db'],(ext,ef,em))
        a,noise_var,flight_var,identity_var,scale=nuisance_estimates(ext_res)
        alpha=rng.normal(0,c['identity_sd_db'],ids)
        enrollment=-42+alpha[:,None,None]+rng.normal(0,flight_sd,(ids,ef,1))+rng.normal(0,c['measurement_sd_db'],(ids,ef,em))
        clean_offset=enrollment.reshape(ids,-1)-a
        z=rng.uniform(np.log10(10),np.log10(150),(ids,tf,tm));truth=10**z
        future_flight=rng.normal(0,flight_sd,(ids,tf,1));future_noise=rng.normal(0,c['measurement_sd_db'],z.shape)
        weight=identity_var/(identity_var+flight_var/ef+noise_var/(ef*em)) if identity_var>0 else 0.
        for pattern in c['patterns']:
            for fraction in c['corrupt_fractions']:
                mask=corruption_masks(rng_for(seed,612),ids,ef,em,pattern,fraction)
                for multiplier in c['false_distance_multipliers']:
                    poisoned=clean_offset+mask*b*np.log10(multiplier)
                    offsets={'shared':np.zeros(ids),'mean':weight*poisoned.mean(axis=1),
                             'median':weight*np.median(poisoned,axis=1),
                             'huber':weight*np.array([huber_location(v,c['huber_scale_multiplier']*scale) for v in poisoned])}
                    for scenario in ['normal','tx_step8','cloned_rid']:
                        query_alpha=np.roll(alpha,1) if scenario=='cloned_rid' else alpha
                        rssi=-42+query_alpha[:,None,None]-b*z+future_flight+future_noise+(8 if scenario=='tx_step8' else 0)
                        for model,offset in offsets.items():
                            point=10**((a+offset[:,None,None]-rssi)/b)
                            assert np.isfinite(point).all()
                            err=point-truth
                            rows.append(dict(seed=seed,flight_sd_db=flight_sd,pattern=pattern,corrupt_fraction=fraction,
                                             distance_multiplier=multiplier,scenario=scenario,model=model,tested=int(truth.size),
                                             abs_error_sum=float(np.abs(err).sum()),squared_error_sum=float((err**2).sum()),
                                             point_wrong30=int(((point<30)!=(truth<30)).sum()),effective_corrupt_fraction=float(mask.mean()),
                                             estimated_noise_variance=noise_var,estimated_flight_variance=flight_var,
                                             estimated_identity_variance=identity_var,shrink_weight=weight,huber_threshold=c['huber_scale_multiplier']*scale))
    return rows


def gate_cases(base_power,alpha,case):
    anchor=base_power.copy();query=base_power.copy()
    if case in ['step_before8','step_before16']:
        change=8 if case=='step_before8' else 16;anchor+=change;query+=change
    elif case=='step_after8':query+=8
    elif case=='cloned_rid':
        change=np.roll(alpha,1)-alpha;anchor+=change[:,None];query+=change[:,None]
    elif case!='normal':raise ValueError(case)
    return anchor,query


def anchor_gate_study(cfg,seed):
    c=cfg['fresh_anchor_gate'];rows=[]
    nc=c['calibration_units'];ids=c['target_ids'];tf=c['test_flights'];tm=c['query_events_per_flight'];ef=c['enrollment_flights'];em=c['enrollment_events_per_flight']
    max_anchor=max(c['anchor_counts']);b=22.
    for flight_sd in c['flight_sd_db']:
        rng=rng_for(seed,711);tau2=c['identity_sd_db']**2;noise2=c['measurement_sd_db']**2
        weight=tau2/(tau2+flight_sd**2/ef+noise2/(ef*em))
        cal_alpha=rng.normal(0,c['identity_sd_db'],nc)
        cal_enrollment=cal_alpha+rng.normal(0,flight_sd,(nc,ef)).mean(axis=1)+rng.normal(0,c['measurement_sd_db']/math.sqrt(ef*em),nc)
        cal_prediction=-42+weight*cal_enrollment
        cal_power=-42+cal_alpha+rng.normal(0,flight_sd,nc)
        cal_noise=rng.normal(0,c['measurement_sd_db'],(nc,max_anchor))
        alpha=rng.normal(0,c['identity_sd_db'],ids)
        enrollment=alpha+rng.normal(0,flight_sd,(ids,ef)).mean(axis=1)+rng.normal(0,c['measurement_sd_db']/math.sqrt(ef*em),ids)
        prediction=-42+weight*enrollment
        base_power=-42+alpha[:,None]+rng.normal(0,flight_sd,(ids,tf))
        anchor_noise=rng.normal(0,c['measurement_sd_db'],(ids,tf,max_anchor))
        z=rng.uniform(np.log10(10),np.log10(150),(ids,tf,tm));truth=10**z
        query_noise=rng.normal(0,c['measurement_sd_db'],z.shape)
        for m in c['anchor_counts']:
            calibration_score=np.abs(cal_power+cal_noise[:,:m].mean(axis=1)-cal_prediction)
            threshold=float(np.quantile(calibration_score,1-c['calibration_false_reject_target']))
            for scenario in ['normal','step_before8','step_before16','step_after8','cloned_rid']:
                anchor_power,query_power=gate_cases(base_power,alpha,scenario)
                anchor_estimate=anchor_power+anchor_noise[:,:,:m].mean(axis=2)
                accepted=np.abs(anchor_estimate-prediction[:,None])<=threshold
                rssi=query_power[:,:,None]-b*z+query_noise
                point=10**((prediction[:,None,None]-rssi)/b)
                for model,unit_mask in [('rid_unchecked',np.ones_like(accepted)),('rid_gated',accepted)]:
                    query_mask=np.broadcast_to(unit_mask[:,:,None],point.shape)
                    err=point[query_mask]-truth[query_mask]
                    rows.append(dict(seed=seed,flight_sd_db=flight_sd,anchor_count=m,scenario=scenario,model=model,
                                     anchor_units=ids*tf,accepted_units=int(unit_mask.sum()),query_total=int(truth.size),
                                     tested=int(query_mask.sum()),abs_error_sum=float(np.abs(err).sum()),squared_error_sum=float((err**2).sum()),
                                     point_wrong30=int(((point[query_mask]<30)!=(truth[query_mask]<30)).sum()),gate_threshold_db=threshold))
    return rows


def time_mismatch_study(cfg,seed):
    c=cfg['time_mismatch'];rng=rng_for(seed,811);n=c['events_per_seed'];b=22.
    z=rng.uniform(np.log10(10),np.log10(150),n);truth=10**z
    mean=-42.;truth_mean=mean+rng.normal(0,c['mean_uncertainty_sd_db'],n)
    initial=rng.normal(0,c['power_sd_db'],n);innovation=rng.normal(0,c['power_sd_db'],n)
    anchor=truth_mean+initial+rng.normal(0,c['anchor_noise_sd_db'],n)
    measurement=rng.normal(0,c['query_noise_sd_db'],n);q=norm.ppf(.95);rows=[]
    for true_tau in c['true_tau_s']:
        for gap in c['gaps_s']:
            rho=math.exp(-gap/true_tau)
            power=truth_mean+rho*initial+math.sqrt(1-rho*rho)*innovation
            for scenario,shift in [('normal',0),('tx_step8',8)]:
                rssi=power+shift-b*z+measurement
                for assumption in ['none']+c['assumed_tau_s']:
                    assumed_rho=math.exp(-gap/assumption) if assumption!='none' else 0.
                    method='no_history' if assumption=='none' else 'ou_matched'
                    forecast,var=power_forecast(anchor,mean,c['mean_uncertainty_sd_db'],c['power_sd_db'],c['anchor_noise_sd_db'],assumed_rho,method)
                    point=10**((forecast-rssi)/b);radius=q*math.sqrt(var+c['query_noise_sd_db']**2)/b
                    lo=point*10**(-radius);hi=point*10**radius
                    rows.append(dict(seed=seed,true_tau_s=true_tau,assumed_tau_s=assumption,gap_s=gap,scenario=scenario,
                                     tested=n,abs_error_sum=float(np.abs(point-truth).sum()),squared_error_sum=float(((point-truth)**2).sum()),
                                     covered=int(((lo<=truth)&(truth<=hi)).sum()),width_sum=float((hi-lo).sum())))
    return rows


KEYS={'empirical_sync':['noise_model','receivers','environment','delta_m'],
      'poisoning':['flight_sd_db','pattern','corrupt_fraction','distance_multiplier','scenario','model'],
      'anchor_gate':['flight_sd_db','anchor_count','scenario','model'],
      'time_mismatch':['true_tau_s','assumed_tau_s','gap_s','scenario']}


def aggregate(study,rows):
    groups={}
    for row in rows:groups.setdefault(tuple(row[k] for k in KEYS[study]),[]).append(row)
    output=[]
    for key,group in groups.items():
        row=dict(zip(KEYS[study],key));tested=sum(r['tested'] for r in group)
        row.update(seeds=len({r['seed'] for r in group}),tested=tested)
        for field in ['alarms','matched_normal_alarms','point_wrong30','covered','anchor_units','accepted_units','query_total']:
            if field in group[0]:row[field]=sum(r[field] for r in group)
        if 'alarms' in row:
            row['alarm_rate']=row['alarms']/tested if tested else None
            row['matched_normal_fpr']=row['matched_normal_alarms']/tested if tested else None
        if 'abs_error_sum' in group[0]:
            row['mae_m']=sum(r['abs_error_sum'] for r in group)/tested if tested else None
            row['rmse_m']=math.sqrt(sum(r['squared_error_sum'] for r in group)/tested) if tested else None
        if 'point_wrong30' in row:row['point_wrong30_rate']=row['point_wrong30']/tested if tested else None
        if 'covered' in row:
            row['interval_coverage']=row['covered']/tested;row['mean_width_m']=sum(r['width_sum'] for r in group)/tested
        if 'accepted_units' in row:row['accept_rate']=row['accepted_units']/row['anchor_units'];row['abstain_rate']=1-row['accept_rate']
        output.append(row)
    return output


def write_csv(path,rows):
    with path.open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,default=Path(__file__).with_name('robustness_config.json'))
    parser.add_argument('--raw',type=Path,default=Path('captures/week26-public-ble'))
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();cfg=json.loads(args.config.read_text())
    if args.out.exists():parser.error('new run directory required; existing outputs preserved')
    if not args.raw.exists():download(args.raw)
    data,sources=load(args.raw);pools={};stats=[]
    for parity in [0,1]:
        pools[parity],sectors=residual_pools(data,parity)
        stats.append({'calibration_parity':parity,'calibration':pool_statistics(pools[parity][0]),'test':pool_statistics(pools[parity][1]),
                      'calibration_sector_count':len(sectors[0]),'test_sector_count':len(sectors[1]),'sectors_disjoint':not bool(sectors[0]&sectors[1])})
    args.out.mkdir(parents=True);(args.out/'config.json').write_text(json.dumps(cfg,indent=2)+'\n')
    status={'status':'running','completed_seed_studies':0};start=time.monotonic();results={}
    def checkpoint():(args.out/'status.json').write_text(json.dumps(status,indent=2)+'\n')
    checkpoint()
    jobs={'empirical_sync':lambda seed:empirical_sync_study(cfg,pools,seed),'poisoning':lambda seed:poisoning_study(cfg,seed),
          'anchor_gate':lambda seed:anchor_gate_study(cfg,seed),'time_mismatch':lambda seed:time_mismatch_study(cfg,seed)}
    try:
        with threadpool_limits(limits=1):
            for study,job in jobs.items():
                rows=[]
                for seed in cfg['seeds']:
                    new=job(seed);rows.extend(new);write_csv(args.out/f'{study}-seed-metrics.csv',rows)
                    status.update(study=study,seed=seed,completed_seed_studies=status['completed_seed_studies']+1);checkpoint()
                    with (args.out/'progress.jsonl').open('a') as f:f.write(json.dumps(dict(study=study,seed=seed,rows=len(new)))+'\n')
                    print(json.dumps(dict(study=study,seed=seed,rows=len(new))),flush=True)
                results[study]=aggregate(study,rows);write_csv(args.out/f'{study}-summary.csv',results[study])
        summary={'scope':__doc__,'config':cfg,'source_ble_files':sources,'empirical_residual_pools':stats,'summaries':results,
                 'runtime':{'wall_seconds':time.monotonic()-start,'peak_process_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform=='darwin' else 1024),
                            'platform':platform.platform(),'python':sys.version,'compute_threads':1},
                 'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                 'limitations':['Indoor pooled BLE residuals, resampled independently across virtual links; not real UAV or multi-receiver RF',
                   'Corruption affects only target enrollment, with protected clean external training',
                   'Gate requires independent fresh true-distance anchors and stable power between anchor and query',
                   'Gate is a model-mismatch screen, not aircraft identity authentication, CRC or physical guarantee',
                   'Time constants remain hypothetical and are not fitted from actual UAV data',
                   'No real coordinates/captures/keys/proofs exported; no ZKP implementation']}
        (args.out/'summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
        status.update(status='complete',wall_seconds=summary['runtime']['wall_seconds']);checkpoint()
    except BaseException as exc:
        status.update(status='failed',error=f'{type(exc).__name__}: {exc}');checkpoint();raise


if __name__=='__main__':main()
