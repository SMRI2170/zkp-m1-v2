"""Model-error/power-bound sensitivity with unchanged measured LoRa baseline.

Single-link receiver-position proxy; no Remote ID or new RF experiment.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import numpy as np
from paired_attacks import load_geometry, claimed_distance, variant_scores

SHIFTS=(10.,30.,50.,100.)
ATTACKER_N=np.round(np.arange(.5,5.01,.1),2)
RATIOS=np.round(np.arange(.25,1.751,.05),2)
CAPS=(0.,1.,2.,3.,4.,6.,8.,10.,12.,15.,20.,30.,None)
VARIANTS=('normal','position_only','exact_compensation','bounded_3db','mismatched_n2')
WINDOW_SECONDS=10.


def residual_shift(detector_n,attacker_n,true_range,claim_range,cap=None):
    d=np.asarray(true_range,dtype=float);q=np.asarray(claim_range,dtype=float)
    if detector_n<=0 or attacker_n<=0 or not np.isfinite([detector_n,attacker_n]).all():raise ValueError('Invalid exponent')
    if d.shape!=q.shape or not np.isfinite(d).all() or not np.isfinite(q).all() or np.any(d<=0) or np.any(q<=0):raise ValueError('Invalid ranges')
    log_ratio=np.log10(q/d)
    power=-10*attacker_n*log_ratio
    if cap is not None:
        if not np.isfinite(cap) or cap<0:raise ValueError('Invalid power cap')
        power=np.clip(power,-cap,cap)
    # Signed attacked residual = original signed residual + this shift.
    return 10*detector_n*log_ratio+power,power


def episodes(times,flags,gap=2.):
    times=np.asarray(times);flags=np.asarray(flags,dtype=bool)
    if times.shape!=flags.shape or not np.isfinite(times).all() or np.any(np.diff(times)<=0):raise ValueError('Invalid time series')
    count=0;lengths=[];durations=[];start=None;last=None;packets=0
    for i,(time,flag) in enumerate(zip(times,flags)):
        if start is not None and (not flag or time-last>gap):
            lengths.append(packets);durations.append(last-start);start=None
        if flag:
            if start is None:start=time;count+=1;packets=0
            packets+=1;last=time
    if start is not None:lengths.append(packets);durations.append(last-start)
    return dict(episodes=count,alarm_packets=int(flags.sum()),
                mean_packets_per_episode=float(np.mean(lengths)) if lengths else None,
                longest_episode_span_s=float(max(durations)) if durations else 0.)


def full_windows(times,width=WINDOW_SECONDS,gap=2.):
    """Complete non-overlapping past-data windows; never bridge a reception gap."""
    t=np.asarray(times,dtype=float)
    if width<=0 or gap<=0 or not np.isfinite(t).all() or np.any(np.diff(t)<=0):raise ValueError('Invalid windows')
    if not len(t):return []
    cuts=np.r_[0,np.flatnonzero(np.diff(t)>gap)+1,len(t)]
    windows=[]
    for start,end in zip(cuts[:-1],cuts[1:]):
        segment=t[start:end]
        count=int(np.floor((segment[-1]-segment[0])/width))
        for k in range(count):
            a=int(np.searchsorted(segment,segment[0]+k*width,side='left'))+start
            b=int(np.searchsorted(segment,segment[0]+(k+1)*width,side='left'))+start
            if b>a:windows.append((a,b))
    return windows


def window_scores(scores,windows):
    values=np.asarray(scores)
    return np.asarray([np.median(values[a:b]) for a,b in windows])


def rate(signed,shift,threshold):
    score=np.abs(signed+shift)
    return float(np.mean(score>threshold)),float(np.mean(shift)),float(np.sqrt(np.mean(shift**2)))


def summarize(rows,keys):
    grouped={}
    for row in rows:grouped.setdefault(tuple(row[k] for k in keys),[]).append(row)
    output=[]
    for key,group in grouped.items():
        by_condition={}
        for r in group:by_condition.setdefault(r['condition'],[]).append(r['alarm_rate'])
        means=[np.mean(v) for v in by_condition.values()]
        output.append(dict(**dict(zip(keys,key)),folds=len(group),received_packets=sum(r['received_packets'] for r in group),
            mean_alarm_rate=float(np.mean([r['alarm_rate'] for r in group])),
            mean_baseline_alarm_rate=float(np.mean([r['baseline_alarm_rate'] for r in group])),
            mean_excess_alarm_pp=float(np.mean([r['alarm_rate']-r['baseline_alarm_rate'] for r in group])*100),
            mean_signed_shift_db=float(np.mean([r['mean_signed_shift_db'] for r in group])),
            mean_rms_shift_db=float(np.mean([r['rms_shift_db'] for r in group])),
            condition_mean_alarm_min=float(min(means)),condition_mean_alarm_max=float(max(means))))
    return output


def analyze(archive):
    source,groups,inventory,_=load_geometry(archive)
    rows={'absolute_exponent':[],'relative_exponent':[],'power_cap':[],'joint':[],'temporal':[],'n2_explanation':[]}
    for condition,runs in groups.items():
        if len(runs)!=3:continue
        ids=sorted(runs)
        for fold in range(3):
            train,cal,test=[runs[ids[(fold+i)%3]] for i in range(3)]
            model=source.fit_model(train);nd=float(-model[1]/10)
            if nd<=0:raise ValueError('Non-decaying detector fit')
            threshold=float(np.quantile(np.abs(cal['r']-source.expected(model,cal['d'])),.95))
            signed=test['r']-source.expected(model,test['d']);baseline=float(np.mean(np.abs(signed)>threshold))
            base=dict(condition=condition,fold=fold,training_run=ids[fold],calibration_run=ids[(fold+1)%3],evaluation_run=ids[(fold+2)%3],
                      received_packets=len(signed),detector_n=nd,threshold_db=threshold,baseline_alarm_rate=baseline)
            for delta in SHIFTS:
                claim,mask=claimed_distance(test['d'],test['z'],delta,'outward')
                if not mask.all():raise ValueError('Outward cohort unexpectedly changed')
                def measure(attacker_n,cap):
                    shift,power=residual_shift(nd,attacker_n,test['d'],claim,cap)
                    alarm,mean,rms=rate(signed,shift,threshold)
                    return dict(alarm_rate=alarm,mean_signed_shift_db=mean,rms_shift_db=rms)
                for na in ATTACKER_N:
                    rows['absolute_exponent'].append(dict(**base,shift_m=delta,attacker_n=float(na),**measure(na,None)))
                for ratio in RATIOS:
                    rows['relative_exponent'].append(dict(**base,shift_m=delta,n_ratio=float(ratio),**measure(nd*ratio,None)))
                for cap in CAPS:
                    rows['power_cap'].append(dict(**base,shift_m=delta,cap_db=cap,**measure(nd,cap)))
                if delta==100.:
                    for ratio in RATIOS:
                        for cap in CAPS:
                            rows['joint'].append(dict(**base,n_ratio=float(ratio),cap_db=cap,**measure(nd*ratio,cap)))
                    shift,_=residual_shift(nd,2.,test['d'],claim)
                    normal_flag=np.abs(signed)>threshold;attack_flag=np.abs(signed+shift)>threshold
                    rows['n2_explanation'].append(dict(**base,attacker_n=2.,exponent_error=2.-nd,
                        log_range_ratio_mean=float(np.mean(np.log10(claim/test['d']))),
                        mean_signed_shift_db=float(np.mean(shift)),rms_shift_db=float(np.sqrt(np.mean(shift**2))),
                        baseline_residual_mean_db=float(signed.mean()),attacked_residual_mean_db=float((signed+shift).mean()),
                        alarm_rate=float(attack_flag.mean()),new_alarm_fraction=float(np.mean(attack_flag&~normal_flag)),
                        lost_alarm_fraction=float(np.mean(normal_flag&~attack_flag))))
            claim,_=claimed_distance(test['d'],test['z'],100.,'outward')
            cal_windows=full_windows(cal['t']);evaluation_windows=full_windows(test['t'])
            cal_window_scores=window_scores(np.abs(cal['r']-source.expected(model,cal['d'])),cal_windows)
            window_threshold=float(np.quantile(cal_window_scores,.95)) if len(cal_window_scores) else None
            for variant in VARIANTS:
                normal,attack,_=variant_scores(model,test['r'],test['d'],claim,variant)
                flag=attack>threshold;episode=episodes(test['t'],flag)
                ten_scores=window_scores(attack,evaluation_windows)
                window_alarm=float(np.mean(ten_scores>window_threshold)) if len(ten_scores) and window_threshold is not None else None
                normal_window_scores=window_scores(normal,evaluation_windows)
                baseline_window_alarm=float(np.mean(normal_window_scores>window_threshold)) if len(ten_scores) and window_threshold is not None else None
                rows['temporal'].append(dict(**base,variant=variant,packet_alarm_rate=float(flag.mean()),
                    calibration_complete_windows=len(cal_windows),evaluation_complete_windows=len(evaluation_windows),
                    window_threshold_db=window_threshold,window_median_alarm_rate=window_alarm,
                    baseline_window_alarm_rate=baseline_window_alarm,**episode))
    aggregates={k:summarize(rows[k],keys) for k,keys in [
        ('absolute_exponent',['shift_m','attacker_n']),('relative_exponent',['shift_m','n_ratio']),
        ('power_cap',['shift_m','cap_db']),('joint',['n_ratio','cap_db'])]}
    aggregates['temporal']=[]
    for variant in VARIANTS:
        group=[r for r in rows['temporal'] if r['variant']==variant]
        windows=[r for r in group if r['window_median_alarm_rate'] is not None]
        total_episodes=sum(r['episodes'] for r in group);total_alarm_packets=sum(r['alarm_packets'] for r in group)
        aggregates['temporal'].append(dict(variant=variant,folds=len(group),window_evaluable_folds=len(windows),
            mean_packet_alarm_rate=float(np.mean([r['packet_alarm_rate'] for r in group])),
            mean_window_median_alarm_rate=float(np.mean([r['window_median_alarm_rate'] for r in windows])) if windows else None,
            total_evaluation_windows=sum(r['evaluation_complete_windows'] for r in group),
            total_alarm_packets=total_alarm_packets,total_episodes=total_episodes,
            pooled_packets_per_episode=total_alarm_packets/total_episodes if total_episodes else None,
            mean_longest_episode_span_s=float(np.mean([r['longest_episode_span_s'] for r in group]))))
    result=dict(source_url=source.URL,source_sha256=source.SHA256,
        scope='Existing real LoRa RSSI with synthetic receiver-position/power perturbations; not Remote ID validation',
        config=dict(shifts_m=SHIFTS,attacker_n=ATTACKER_N.tolist(),n_ratio=RATIOS.tolist(),power_caps_db=CAPS,
                    direction='outward',joint_and_temporal_shift_m=100.,window_seconds=WINDOW_SECONDS,gap_break_seconds=2.,
                    window_score='Median of absolute packet residuals; own separate normal calibration 95th percentile',
                    split='Same training/calibration/evaluation run roles as paired_attacks.py',seed=None),
        signed_shift_equation='10*(n_detector-n_attacker)*log10(d_claim/d_true), before clipping power',
        raw_observations=sum(r['rows'] for r in inventory),evaluation_received_packets=116691,folds=48,
        aggregates=aggregates,fold_row_counts={k:len(v) for k,v in rows.items()},
        interpretation=['All sweep conditions use identical received evaluation samples and normal-only calibration',
            'Power caps are relative dB changes, not measured absolute EIRP limits',
            'Packet alarm rates and 10-second-window alarm rates have different denominators and thresholds',
            'Episodes are contiguous alarms split by a normal packet or a reception gap >2s; they are not independent events',
            'No independent-packet or independent-window confidence intervals are asserted; shared runs remain dependent',
            'Condition min/max are descriptive spread, not confidence bounds',
            'No RF sensitivity/censoring/interference change, multipath separation, or true UAV-transmitter multi-site RSSI experiment'])
    return result,rows


def save(result,rows,out):
    if out.exists():raise ValueError('Use a fresh output directory')
    out.mkdir(parents=True)
    (out/'summary.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    for key,values in rows.items():
        with (out/(key+'-fold.csv')).open('w',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(values[0]),lineterminator='\n');writer.writeheader();writer.writerows(values)
    for key,values in result['aggregates'].items():
        with (out/(key+'-aggregate.csv')).open('w',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(values[0]),lineterminator='\n');writer.writeheader();writer.writerows(values)
    files=[Path(__file__),Path(__file__).with_name('paired_attacks.py'),Path(__file__).resolve().parents[1]/'week26-rssi-privacy/recheck_lora.py']
    (out/'code-hashes.json').write_text(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in files},indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--archive',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    result,rows=analyze(a.archive);save(result,rows,a.out)
    print(json.dumps({'row_counts':result['fold_row_counts'],'power_100m':[r for r in result['aggregates']['power_cap'] if r['shift_m']==100.],
                      'temporal':result['aggregates']['temporal']},indent=2))
