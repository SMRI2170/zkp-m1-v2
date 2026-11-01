"""Reproduce three findings and isolate reception selection; synthetic data only.

No raw RF, GPS, keys or per-event private observations are written. Reuses the
predeclared Week26 generators. Serial execution, new output directories only.
"""
import os
for _key in ['OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS']:
    os.environ[_key] = '1'
import argparse
import csv
import hashlib
import json
from pathlib import Path
import resource
import sys
import time
import numpy as np
from simulate3d_independent import generate, receive
import event_scenarios as ev

EDGES = np.array([0., .5, 1., 1.5, 2., np.inf])

def histogram(values):
    # Alarm is strictly >1, matching the original detector. Exactly 1 belongs
    # to the non-alarm bin, so histogram and counts share the same boundary.
    groups = np.searchsorted(EDGES[1:-1], values, side='left')
    return np.bincount(groups, minlength=5)


def metrics(seed, study, case, mask, alarm, emitted, **extra):
    n, k = int(np.count_nonzero(mask)), int(np.count_nonzero(mask & alarm))
    return dict(seed=seed, study=study, case=case, emitted=emitted,
                eligible=n, alarms=k, conditional_alarm_rate=k/n if n else None,
                all_event_alarm_rate=k/emitted if emitted else None, **extra)


def joint_scores(base, received_normal, received_joint, normal_score, joint_score):
    paired = received_normal & received_joint
    delta = float(np.max(np.abs(normal_score[paired]-joint_score[paired]))) if paired.any() else None
    return paired, delta


def single(cfg, old, seed):
    cal, base = generate(old, seed, 'calibration'), generate(old, seed, 'test')
    cm, cr = receive(cal, old, 'mixed'); normal_mask, normal_r = receive(base, old, 'mixed')
    b = 10*old['path_loss_exponent']
    cal_u = cr[cm]+b*np.log10(cal['d_claim'][cm])
    center = float(np.median(cal_u))
    threshold = float(np.quantile(np.abs(cal_u-center), 1-cfg['fpr_calibration_target']))
    normal_score = np.abs(normal_r+b*np.log10(base['d_claim'])-center)
    normal_alarm = normal_score > threshold
    rows, hist = [], []
    for label, selected in [('20-40m', (base['d_true']>=20)&(base['d_true']<40)),
                            ('80-120m', (base['d_true']>=80)&(base['d_true']<120))]:
        eligible=normal_mask & selected
        for case, claim in [('normal',base['d_claim']),('position30',base['d_claim']+30)]:
            score=np.abs(normal_r+b*np.log10(claim)-center)
            rows.append(metrics(seed,'position30',case,eligible,score>threshold,int(selected.sum()),range_bin=label))
            for index, count in enumerate(histogram(score[eligible]/threshold)):
                hist.append(dict(seed=seed,study='position30',case=case,range_bin=label,bin=index,count=int(count),total=int(eligible.sum())))
    claim=base['d_claim']+100
    changed={k:v.copy() for k,v in base.items()}
    offset=b*np.log10(base['d_claim']/claim)
    changed['raw']+=offset
    joint_mask,joint_r=receive(changed,old,'mixed')
    joint_score=np.abs(joint_r+b*np.log10(claim)-center)
    position_score=np.abs(normal_r+b*np.log10(claim)-center)
    paired, delta=joint_scores(base,normal_mask,joint_mask,normal_score,joint_score)
    full=np.ones(len(normal_mask),bool)
    for cohort, mask in [('all_received_normal',normal_mask),('all_received_joint',joint_mask),('paired',paired)]:
        cases=[('normal',normal_score)] if cohort=='all_received_normal' else [('joint100',joint_score)] if cohort=='all_received_joint' else [('normal',normal_score),('position100',position_score),('joint100',joint_score)]
        for case, score in cases:
            rows.append(metrics(seed,'power100',case,mask,score>threshold,len(full),cohort=cohort))
    for case,score in [('normal',normal_score),('position100',position_score),('joint100',joint_score)]:
        for index,count in enumerate(histogram(score[paired]/threshold)):
            hist.append(dict(seed=seed,study='power100',case=case,range_bin='paired',bin=index,count=int(count),total=int(paired.sum())))
    raw_u=base['raw']-base['bias_est']+b*np.log10(base['d_claim'])
    changed_u=changed['raw']-base['bias_est']+b*np.log10(claim)
    algebra_delta=float(np.max(np.abs(raw_u-changed_u)))
    assert algebra_delta<1e-10
    assert delta is None or delta<=old['rssi_quantization_db']+1e-10
    return rows,hist,dict(seed=seed,threshold_db=threshold,paired_count=int(paired.sum()),
        dropped_only_after_attack=int((normal_mask&~joint_mask).sum()),
        newly_received_after_attack=int((~normal_mask&joint_mask).sum()),
        maximum_paired_quantized_score_delta_db=delta,maximum_unquantized_residual_delta_db=algebra_delta,
        power_change_min_db=float(offset.min()),power_change_max_db=float(offset.max()))


def common(cfg,seed):
    cal,test=ev.generate(cfg,seed,0),ev.generate(cfg,seed,1)
    cm,tm=ev.mask_for(cal,'full',5),ev.mask_for(test,'full',5)
    rows,hist=[],[]
    b=10*cfg['path_loss_exponent']
    for sd in [2,6]:
        cr,tr=ev.rssi(cal,cfg,sd),ev.rssi(test,cfg,sd)
        cs,cp,_=ev.profile_score(cr,cal['dist'],cm,b)
        table=ev.thresholds(cs,cp,cfg)
        assert len(table)==1
        threshold=next(iter(table.values()))
        for delta in [0,30,100]:
            distance=ev.claimed_distances(test,cfg,delta)
            score,pattern,_=ev.profile_score(tr,distance,tm,b)
            usable,alarm=ev.decisions(score,pattern,table)
            shifted,_,_=ev.profile_score(tr+16,distance,tm,b)
            np.testing.assert_allclose(score,shifted,atol=1e-10)
            rows.append(metrics(seed,'common5',f'position{delta}',usable,alarm,score.size,
                                noise_sd_db=sd,threshold_db=threshold))
            for index,count in enumerate(histogram(score[usable]/threshold)):
                hist.append(dict(seed=seed,study='common5',case=f'position{delta}',range_bin=f'sd{sd}',bin=index,count=int(count),total=int(usable.sum())))
    return rows,hist


def aggregate(rows,keys):
    groups={}
    for r in rows:groups.setdefault(tuple(r.get(k,'') for k in keys),[]).append(r)
    result=[]
    for key,group in groups.items():
        row=dict(zip(keys,key),seed_count=len({r['seed'] for r in group}))
        for k in ['emitted','eligible','alarms','count','total']:
            if k in group[0]:row[k]=sum(r[k] for r in group)
        if 'eligible' in row:
            row['conditional_alarm_rate']=row['alarms']/row['eligible'] if row['eligible'] else None
            row['all_event_alarm_rate']=row['alarms']/row['emitted'] if row['emitted'] else None
        if 'count' in row:row['fraction']=row['count']/row['total'] if row['total'] else None
        result.append(row)
    return result


def save_csv(path,rows):
    columns=list(dict.fromkeys(k for r in rows for k in r))
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=columns);w.writeheader();w.writerows(rows)


def audit_saved(rows,root):
    with (root/'week26/results/mac-sensitivity-20261101-v2/position-summary.csv').open() as f:
        previous=list(csv.DictReader(f))
    for r in rows:
        if r['study']=='position30':
            delta='0' if r['case']=='normal' else '30'
            p=next(p for p in previous if p['delta_m']==delta and p['direction']=='out' and p['attack']=='position_only' and p['range_bin']==r['range_bin'])
        elif r['study']=='power100' and r['cohort']!='paired':
            delta,attack=('0','position_only') if r['case']=='normal' else ('100','joint_unbounded')
            p=next(p for p in previous if p['delta_m']==delta and p['direction']=='out' and p['attack']==attack and p['range_bin']=='all')
        else:continue
        assert r['eligible']==int(p['tested']) and r['alarms']==int(p['alarms'])
    saved=json.loads((root/'week26/results/mac-event-scenarios-20261101/summary.json').read_text())
    for r in rows:
        if r['study']=='common5':
            case='normal' if r['case']=='position0' else r['case']
            p=next(p for p in saved['cases'] if p['mode']=='full' and p['noise_sd_db']==r['noise_sd_db'] and p['case']==case)
            assert abs(r['conditional_alarm_rate']-p['conditional_alarm_fraction'])<1e-12


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);args=p.parse_args()
    if args.out.exists():p.error('new output directory required')
    root=Path(__file__).resolve().parents[2];here=Path(__file__).resolve().parent
    cfg=json.loads((here/'sensitivity_config.json').read_text());old=json.loads((here/'synthetic3d_config.json').read_text())
    ecfg=json.loads((here/'event_scenarios_config.json').read_text())
    args.out.mkdir(parents=True);start=time.monotonic()
    (args.out/'status.json').write_text('{"status":"running"}\n')
    rows,hist,diagnostics=[],[],[]
    try:
        for seed in cfg['seeds']:
            rr,hh,dd=single(cfg,old,seed);rows.extend(rr);hist.extend(hh);diagnostics.append(dd)
        for seed in ecfg['seeds']:
            rr,hh=common(ecfg,seed);rows.extend(rr);hist.extend(hh)
        summary=aggregate(rows,['study','case','range_bin','cohort','noise_sd_db'])
        hist_summary=aggregate(hist,['study','case','range_bin','bin'])
        audit_saved(summary,root)
        examples=[]
        rng=np.random.default_rng(202611020)
        d=rng.uniform(20,120,10);a=-42+rng.normal(0,4,10)
        for i,(dist,power) in enumerate(zip(d,a)):
            normal=power-20*np.log10(dist);fake=power+20*np.log10(4)-20*np.log10(dist*4)
            examples.append(dict(event=i+1,distance_a_m=float(dist),distance_b_m=float(dist*4),rssi_a_dbm=float(normal),rssi_b_dbm=float(fake)))
        save_csv(args.out/'metrics-seed.csv',rows);save_csv(args.out/'metrics-summary.csv',summary)
        save_csv(args.out/'histogram-summary.csv',hist_summary);save_csv(args.out/'paired-diagnostics.csv',diagnostics)
        save_csv(args.out/'counterexample-example.csv',examples)
        provenance=[here/name for name in ['explain_three_results.py','simulate3d_independent.py','event_scenarios.py','synthetic3d_config.json','sensitivity_config.json','event_scenarios_config.json']]
        result=dict(scope=__doc__,metrics=summary,histograms=hist_summary,paired_diagnostics=diagnostics,
                    counterexample=examples,config_single=old,sensitivity=cfg,config_common=ecfg,
                    source_hashes={str(f.relative_to(root)):hashlib.sha256(f.read_bytes()).hexdigest() for f in provenance},
                    wall_seconds=time.monotonic()-start,peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform=='darwin' else 1024),
                    checks=['saved position counts reproduced exactly','saved common5 rates reproduced','unquantized compensation exact','paired quantization error bounded by 1dB'],
                    limitations=['All inputs synthetic; no UAV RF performance claim','No GPS truth acquired; generators provide labels','Common5 assumes known correspondence and propagation; no NLOS','Power100 attack knows receiver and channel model and has unbounded control','Histogram pools seeds for display; packets are not independent trials'])
        (args.out/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
        (args.out/'status.json').write_text(json.dumps({'status':'complete','wall_seconds':result['wall_seconds']})+'\n')
        print(json.dumps({'status':'complete','rows':len(summary),'wall_seconds':result['wall_seconds'],'peak_rss_bytes':result['peak_rss_bytes']}))
    except BaseException as exc:
        (args.out/'status.json').write_text(json.dumps({'status':'failed','error':f'{type(exc).__name__}: {exc}'})+'\n');raise

if __name__=='__main__':main()
