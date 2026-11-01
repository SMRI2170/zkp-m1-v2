"""Four predeclared synthetic studies, plus fixed-budget async receiver control.

No actual RID capture, aircraft authentication, paper reproduction or ZKP.
All labels and positions are synthetic. Run serially and retain failures.
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
from scipy.stats import norm
from threadpoolctl import threadpool_limits
from simulate3d_independent import generate, receive, fit_models


def rng_for(seed, tag):
    return np.random.default_rng(np.random.SeedSequence([seed,tag]))


def radial_claim(base, delta, direction):
    """Additional displacement on top of unchanged normal GPS error.

    The same-range control represents a feasible chord on a sphere, without
    inventing new absolute coordinates. Infeasible chords are excluded.
    """
    valid=np.ones(len(base['d_true']),bool)
    if direction=='out':claim=base['d_claim']+delta
    elif direction=='in':
        valid=base['d_true']>delta+1
        claim=np.maximum(base['d_claim']-delta,1)
    elif direction=='same_range':
        valid=delta<=2*base['d_true'];claim=base['d_claim'].copy()
    else:raise ValueError(direction)
    return claim,valid


def position_study(cfg, old, seed):
    cal=generate(old,seed,'calibration');base=generate(old,seed,'test')
    cm,cr=receive(cal,old,'mixed');mask,r=receive(base,old,'mixed')
    b=10*old['path_loss_exponent']
    normal_residual=r+b*np.log10(base['d_claim'])
    cal_residual=cr[cm]+b*np.log10(cal['d_claim'][cm])
    center=float(np.median(cal_residual))
    threshold=float(np.quantile(np.abs(cal_residual-center),1-cfg['fpr_calibration_target']))
    normal_alarm=np.abs(normal_residual-center)>threshold
    rows=[]
    for delta in cfg['spoof_displacements_m']:
        for direction in ['out','in','same_range']:
            claim,eligible=radial_claim(base,delta,direction)
            for attack in ['position_only','joint_unbounded','joint_bounded8']:
                power_delta=np.zeros(len(r))
                if attack!='position_only':
                    power_delta=b*np.log10(base['d_claim']/claim)
                    if attack=='joint_bounded8':power_delta=np.clip(power_delta,-8,8)
                changed={k:v.copy() for k,v in base.items()}
                changed['raw']+=power_delta
                am,ar=receive(changed,old,'mixed')
                alarms=np.abs(ar+b*np.log10(claim)-center)>threshold
                for label,selection in [('all',np.ones(len(r),bool)),('20-40m',(base['d_true']>=20)&(base['d_true']<40)),('80-120m',(base['d_true']>=80)&(base['d_true']<120))]:
                    valid=eligible&selection
                    tested=valid&am;baseline_tested=valid&mask
                    rows.append(dict(seed=seed,delta_m=delta,direction=direction,attack=attack,range_bin=label,
                                     emitted=int(valid.sum()),tested=int(tested.sum()),alarms=int(alarms[tested].sum()),
                                     baseline_tested=int(baseline_tested.sum()),baseline_alarms=int(normal_alarm[baseline_tested].sum()),
                                     threshold_db=threshold,power_delta_min_db=float(power_delta[valid].min()) if valid.any() else None,
                                     power_delta_max_db=float(power_delta[valid].max()) if valid.any() else None))
    return rows


def receiver_sites(count,radius):
    angle=2*np.pi*np.arange(count)/count
    return np.column_stack([radius*np.cos(angle),radius*np.sin(angle),10*(np.arange(count)%2)])


def profiled_power_score(rssi,claim_distance,b):
    residual=rssi+b*np.log10(claim_distance)
    return np.sqrt(np.mean((residual-residual.mean(axis=1,keepdims=True))**2,axis=1))


def claim_points(points,sites,delta,direction,angles):
    claim=points.copy();valid=np.ones(len(points),bool)
    if direction=='random_horizontal':
        claim[:,:2]+=delta*np.column_stack([np.cos(angles),np.sin(angles)])
    elif direction=='same_range_first_rx':
        xy=points[:,:2]-sites[0,:2];h=np.linalg.norm(xy,axis=1)
        valid=delta<=2*h
        theta=2*np.arcsin(np.minimum(delta/(2*np.maximum(h,1e-9)),1))
        co=np.cos(theta);si=np.sin(theta)
        claim[:,0]=sites[0,0]+co*xy[:,0]-si*xy[:,1]
        claim[:,1]=sites[0,1]+si*xy[:,0]+co*xy[:,1]
    else:raise ValueError(direction)
    return claim,valid


def synchronous_study(cfg,seed):
    c=cfg['sync'];rng=rng_for(seed,211)
    nc=c['calibration_events'];nt=c['test_events'];n=nc+nt
    points=np.column_stack([rng.uniform(*c['true_xy_bounds_m'],size=(n,2)),rng.uniform(*c['true_altitude_bounds_m'],size=n)])
    angles=rng.uniform(0,2*np.pi,nt)
    power=-42+rng.normal(0,c['common_power_sd_db'],n)+rng.normal(0,4,n)
    bias=rng.normal(0,c['residual_receiver_bias_sd_db'],max(cfg['receiver_counts']))
    noise=rng.normal(size=(n,max(cfg['receiver_counts'])))
    b=10*c['path_loss_exponent'];rows=[]
    for aperture in c['aperture_radius_m']:
        for sd in c['independent_link_noise_sd_db']:
            for count in cfg['receiver_counts']:
                sites=receiver_sites(count,aperture)
                distances=np.linalg.norm(points[:,None,:]-sites[None,:,:],axis=2)
                rssi=power[:,None]-b*np.log10(distances)+sd*noise[:,:count]+bias[:count]
                normal_score=profiled_power_score(rssi,distances,b)
                threshold=np.quantile(normal_score[:nc],1-cfg['fpr_calibration_target'])
                for delta in cfg['spoof_displacements_m']:
                    for direction in ['random_horizontal','same_range_first_rx']:
                        claim,valid=claim_points(points[nc:],sites,delta,direction,angles)
                        claimed_dist=np.linalg.norm(claim[:,None,:]-sites[None,:,:],axis=2)
                        score=profiled_power_score(rssi[nc:],claimed_dist,b)
                        rows.append(dict(seed=seed,receivers=count,aperture_radius_m=aperture,link_noise_sd_db=sd,
                                         delta_m=delta,direction=direction,tested=int(valid.sum()),
                                         alarms=int((score[valid]>threshold).sum()),baseline_tested=int(valid.sum()),
                                         baseline_alarms=int((normal_score[nc:][valid]>threshold).sum()),threshold_db=float(threshold)))
    return rows


def remap_async(old,seed,split,count):
    c=dict(old,receivers=10)
    data=generate(c,seed,split)
    rng=np.random.default_rng(np.random.SeedSequence([seed,919]))
    bias=rng.normal(0,c['receiver_bias_sd_db'],10)
    estimate=bias+rng.normal(0,c['receiver_calibration_error_sd_db'],10)
    new=data['flight']%10000%count
    data['raw']+=bias[new]-bias[data['receiver']]
    data['receiver']=new;data['bias_est']=estimate[new]
    return data


def async_study(cfg,old,seed):
    rows=[]
    for count in cfg['receiver_counts']:
        train=remap_async(old,seed,'train',count);cal=remap_async(old,seed,'calibration',count)
        base=remap_async(old,seed,'test',count)
        models,info,_=fit_models(train,cal,old,'mixed',seed)
        for case in ['normal','range_shift30','range_shift30_joint']:
            data={k:v.copy() for k,v in base.items()}
            if case!='normal':data['d_claim']+=30
            if case=='range_shift30_joint':
                data['raw']+=10*old['path_loss_exponent']*np.log10(base['d_claim']/data['d_claim'])
            mask,r=receive(data,old,'mixed');z=models[2].predict(r[mask,None]);point=10**z
            error=point-data['d_true'][mask]
            residual=r[mask]+10*old['path_loss_exponent']*np.log10(data['d_claim'][mask])
            alarm=np.abs(residual-models[5])>models[6]
            rows.append(dict(seed=seed,receivers=count,scenario=case,tested=int(mask.sum()),emitted=len(mask),alarms=int(alarm.sum()),
                             abs_error_sum=float(np.abs(error).sum()),squared_error_sum=float((error**2).sum()),
                             labeled_training_events=len(train['flight']),labeled_calibration_events=len(cal['flight']),
                             fit_warning_count=len(info['warnings']),fit_warnings='; '.join(info['warnings'])))
    return rows


def power_forecast(anchor,mu,sigma_mean,sigma_power,sigma_anchor,rho,method):
    if method=='no_history':return np.full_like(anchor,mu),sigma_mean**2+sigma_power**2
    if method=='hold_last':return anchor.copy(),sigma_anchor**2
    if method!='ou_matched':raise ValueError(method)
    covariance=sigma_mean**2+rho*sigma_power**2
    denominator=sigma_mean**2+sigma_power**2+sigma_anchor**2
    gain=covariance/denominator
    return mu+gain*(anchor-mu),sigma_mean**2+sigma_power**2-covariance**2/denominator


def time_study(cfg,seed):
    c=cfg['time'];rng=rng_for(seed,311);n=c['events_per_seed'];b=10*c['path_loss_exponent']
    distance=10**rng.uniform(np.log10(10),np.log10(150),n)
    mu=-42.;truth_mean=mu+rng.normal(0,c['historical_mean_uncertainty_sd_db'],n)
    u0=rng.normal(0,c['power_stationary_sd_db'],n);innovation=rng.normal(0,c['power_stationary_sd_db'],n)
    anchor=truth_mean+u0+rng.normal(0,c['anchor_measurement_sd_db'],n)
    current_error=rng.normal(0,c['current_measurement_sd_db'],n)
    q=norm.ppf((1+c['normal_coverage'])/2);rows=[]
    for tau in c['power_correlation_time_s']:
        for gap in c['gaps_s']:
            rho=math.exp(-gap/tau) if tau>0 else 0.
            current_power=truth_mean+rho*u0+math.sqrt(1-rho*rho)*innovation
            for case,shift in [('normal',0),('tx_step8',8)]:
                rssi=current_power+shift-b*np.log10(distance)+current_error
                for method in ['no_history','hold_last','ou_matched']:
                    mean,var=power_forecast(anchor,mu,c['historical_mean_uncertainty_sd_db'],c['power_stationary_sd_db'],c['anchor_measurement_sd_db'],rho,method)
                    point=10**((mean-rssi)/b);radius=q*math.sqrt(var+c['current_measurement_sd_db']**2)/b
                    lo=point*10**(-radius);hi=point*10**radius
                    decided=(hi<30)|(lo>30)
                    wrong=((hi<30)&(distance>=30))|((lo>30)&(distance<=30))
                    rows.append(dict(seed=seed,tau_s=tau,gap_s=gap,scenario=case,model=method,tested=n,
                                     abs_error_sum=float(np.abs(point-distance).sum()),squared_error_sum=float(((point-distance)**2).sum()),
                                     covered=int(((lo<=distance)&(distance<=hi)).sum()),decided=int(decided.sum()),wrong=int(wrong.sum()),
                                     width_sum=float((hi-lo).sum()),rho=rho))
    return rows


def fit_identity_offsets(rssi,z,global_a,global_b,k,tau2,flight_sd,noise_sd,per_flight):
    """Enrollment uses independent true-distance labels; no query truth enters."""
    ids=rssi.shape[0]
    if k==0:
        return np.zeros(ids),np.zeros(ids),np.full(ids,global_a),np.full(ids,global_b),ids
    x=z[:,:k];y=rssi[:,:k]
    offset=(y+global_b*x-global_a).mean(axis=1)
    weights=np.bincount(np.arange(k)//per_flight)/k
    mean_variance=noise_sd**2/k+flight_sd**2*np.sum(weights**2)
    shrink=tau2/(tau2+mean_variance) if tau2>0 else 0.
    regularized=shrink*offset
    full_a=global_a+regularized;full_b=np.full(ids,global_b);fallback=0
    for i in range(ids):
        matrix=np.column_stack([np.ones(k),-x[i]])
        if k<3 or np.linalg.cond(matrix)>1e4:
            fallback+=1;continue
        a,b=np.linalg.lstsq(matrix,y[i],rcond=None)[0]
        # Declared lower physical slope bound. Retain all failures via fallback counts.
        if not np.isfinite(b) or b<5:
            fallback+=1;continue
        full_a[i]=a;full_b[i]=b
    return offset,regularized,full_a,full_b,fallback


def personalization_study(cfg,seed):
    c=cfg['personalization'];rows=[]
    ext=c['external_training_ids'];ids=c['target_ids'];en_f=c['enrollment_flights'];en_m=c['enrollment_events_per_flight']
    te_f=c['test_flights'];te_m=c['test_events_per_flight'];noise_sd=c['measurement_noise_sd_db']
    for profile in c['profiles']:
        # Identical standardized draws across profiles; only the named factors change.
        rng=rng_for(seed,411);total=ext+ids
        identity=rng.normal(0,profile['identity_sd_db'],total)
        exponent=np.clip(2.2+rng.normal(0,profile['exponent_sd'],total),1.5,3.)
        z=rng.uniform(np.log10(10),np.log10(150),(total,en_f,en_m))
        flight=rng.normal(0,profile['flight_sd_db'],(total,en_f,1))
        train_r=-42+identity[:,None,None]-10*exponent[:,None,None]*z+flight+rng.normal(0,noise_sd,z.shape)
        global_matrix=np.column_stack([np.ones(z[:ext].size),-z[:ext].reshape(-1)])
        global_a,global_b=np.linalg.lstsq(global_matrix,train_r[:ext].reshape(-1),rcond=None)[0]
        assert global_b>5
        identity_residual=(train_r[:ext]+global_b*z[:ext]-global_a).mean(axis=(1,2))
        tau2=max(float(np.var(identity_residual,ddof=1)-profile['flight_sd_db']**2/en_f-noise_sd**2/(en_f*en_m)),0.)
        en_z=z[ext:].reshape(ids,-1);en_r=train_r[ext:].reshape(ids,-1)
        test_z=rng.uniform(np.log10(10),np.log10(150),(ids,te_f,te_m));truth=10**test_z
        test_flight=rng.normal(0,profile['flight_sd_db'],(ids,te_f,1));test_noise=rng.normal(0,noise_sd,test_z.shape)
        for k in c['labeled_enrollment_counts']:
            offset,shrink,full_a,full_b,fallback=fit_identity_offsets(en_r,en_z,global_a,global_b,k,tau2,profile['flight_sd_db'],noise_sd,en_m)
            predictors={'global':(np.full(ids,global_a),np.full(ids,global_b),0),
                        'rid_offset':(global_a+offset,np.full(ids,global_b),ids if k==0 else 0),
                        'rid_shrinkage':(global_a+shrink,np.full(ids,global_b),ids if k==0 else 0),
                        'rid_full_ols':(full_a,full_b,fallback)}
            for case in ['normal','tx_step8','cloned_rid']:
                alpha=identity[ext:].copy();b=10*exponent[ext:].copy()
                if case=='cloned_rid':alpha=np.roll(alpha,1);b=np.roll(b,1)
                test_r=-42+alpha[:,None,None]-b[:,None,None]*test_z+test_flight+test_noise+(8 if case=='tx_step8' else 0)
                for method,(a,b_pred,fb) in predictors.items():
                    estimated_log=(a[:,None,None]-test_r)/b_pred[:,None,None]
                    low,high=c['numeric_log10_prediction_bounds']
                    clipped=(estimated_log<low)|(estimated_log>high)
                    estimate=10**np.clip(estimated_log,low,high)
                    error=estimate-truth
                    rows.append(dict(seed=seed,profile=profile['name'],labeled_per_rid=k,scenario=case,model=method,tested=int(truth.size),
                                     abs_error_sum=float(np.abs(error).sum()),squared_error_sum=float((error**2).sum()),
                                     point_wrong30=int(((estimate<30)!=(truth<30)).sum()),fallback_ids=fb,target_ids=ids,
                                     numeric_guard_count=int(clipped.sum()),estimated_identity_variance_db2=tau2,
                                     label_flights_used=math.ceil(k/en_m),global_training_labels=int(z[:ext].size)))
    return rows


KEYS={
    'position':['delta_m','direction','attack','range_bin'],
    'synchronous':['receivers','aperture_radius_m','link_noise_sd_db','delta_m','direction'],
    'asynchronous':['receivers','scenario'],
    'time':['tau_s','gap_s','scenario','model'],
    'personalization':['profile','labeled_per_rid','scenario','model']}


def aggregate(study,rows):
    groups={};keys=KEYS[study]
    for r in rows:groups.setdefault(tuple(r[k] for k in keys),[]).append(r)
    output=[]
    for key,group in groups.items():
        row=dict(zip(keys,key));row['seeds']=len({r['seed'] for r in group})
        total=sum(r['tested'] for r in group);row['tested']=total
        for field in ['alarms','baseline_tested','baseline_alarms','emitted','covered','decided','wrong','point_wrong30','fallback_ids','target_ids','numeric_guard_count']:
            if field in group[0]:row[field]=sum(r[field] for r in group)
        if 'alarms' in row:row['alarm_rate']=row['alarms']/total if total else None
        if 'baseline_tested' in row:row['matched_normal_fpr']=row['baseline_alarms']/row['baseline_tested'] if row['baseline_tested'] else None
        if 'emitted' in row:row['reception_rate']=total/row['emitted'] if row['emitted'] else None
        if 'abs_error_sum' in group[0]:
            row['mae_m']=sum(r['abs_error_sum'] for r in group)/total if total else None
            row['rmse_m']=math.sqrt(sum(r['squared_error_sum'] for r in group)/total) if total else None
            # Seed means are a descriptive spread, not a confidence interval.
            row['seed_mae_sd_m']=float(np.std([r['abs_error_sum']/r['tested'] for r in group if r['tested']],ddof=1))
        if 'covered' in row:
            row['interval_coverage']=row['covered']/total;row['undetermined_rate']=1-row['decided']/total
            row['wrong_rate_all']=row['wrong']/total;row['wrong_rate_decided']=row['wrong']/row['decided'] if row['decided'] else None
            row['mean_width_m']=sum(r['width_sum'] for r in group)/total
        if 'point_wrong30' in row:row['point_wrong30_rate']=row['point_wrong30']/total
        output.append(row)
    return output


def write_csv(path,rows):
    with path.open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,default=Path(__file__).with_name('sensitivity_config.json'))
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();cfg=json.loads(args.config.read_text());old=json.loads(Path(__file__).with_name('synthetic3d_config.json').read_text())
    if args.out.exists():parser.error('new output directory required; old runs preserved')
    args.out.mkdir(parents=True);(args.out/'config.json').write_text(json.dumps(cfg,indent=2)+'\n');(args.out/'async-base-config.json').write_text(json.dumps(old,indent=2)+'\n')
    status={'status':'running','completed_seed_studies':0};start=time.monotonic();results={}
    def checkpoint():(args.out/'status.json').write_text(json.dumps(status,indent=2)+'\n')
    checkpoint()
    jobs={'position':lambda seed:position_study(cfg,old,seed),'synchronous':lambda seed:synchronous_study(cfg,seed),
          'asynchronous':lambda seed:async_study(cfg,old,seed),'time':lambda seed:time_study(cfg,seed),
          'personalization':lambda seed:personalization_study(cfg,seed)}
    try:
        with threadpool_limits(limits=1):
            for study,job in jobs.items():
                rows=[]
                for seed in cfg['seeds']:
                    new=job(seed);rows.extend(new)
                    write_csv(args.out/f'{study}-seed-metrics.csv',rows)
                    status['completed_seed_studies']+=1;status['study']=study;status['seed']=seed;checkpoint()
                    with (args.out/'progress.jsonl').open('a') as f:f.write(json.dumps(dict(study=study,seed=seed,rows=len(new)))+'\n')
                    print(json.dumps(dict(study=study,seed=seed,rows=len(new))),flush=True)
                results[study]=aggregate(study,rows);write_csv(args.out/f'{study}-summary.csv',results[study])
        result={'scope':__doc__,'config':cfg,'summaries':results,'runtime':{'wall_seconds':time.monotonic()-start,
                'peak_process_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform=='darwin' else 1024),
                'platform':platform.platform(),'python':sys.version,'compute_threads':1},
                'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                'limitations':['Illustrative synthetic parameters, not calibrated UAV data',
                'Studies isolate different mechanisms and must not be pooled',
                'Sync uses same packet and common power; it changes the main asynchronous assumption',
                'OU results assume independently known anchor distance and matched time constant',
                'RID enrollment has independent true-distance labels; claimed RID is not identity authentication',
                'Personalization shrinkage uses matched nuisance variances, favorable assumption',
                'Calibration target FPR is not guaranteed held-out FPR; no real RF or ZKP']}
        (args.out/'summary.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
        status.update(status='complete',wall_seconds=result['runtime']['wall_seconds']);checkpoint()
    except BaseException as exc:
        status.update(status='failed',error=f'{type(exc).__name__}: {exc}');checkpoint();raise


if __name__=='__main__':main()
