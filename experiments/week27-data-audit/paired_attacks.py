"""Paired position-claim / power-compensation stress test on real LoRa RSSI.

The moving UAV is the RECEIVER. Synthetic claims modify its receiver location
relative to a buried ground transmitter. This is a link-geometry proxy, not
Remote ID transmitter-position verification. Raw samples never leave captures.
"""
import argparse
import csv
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import zipfile
import numpy as np

DIRECTIONS = ('outward', 'inward', 'tangential')
SHIFTS = (10., 30., 50., 100.)
VARIANTS = ('normal', 'position_only', 'exact_compensation', 'bounded_3db', 'mismatched_n2')
REFERENCE = ('outward', 100.)
SCORE_EDGES = np.linspace(0., 6., 121)


def source_module():
    path=Path(__file__).resolve().parents[1]/'week26-rssi-privacy/recheck_lora.py'
    spec=importlib.util.spec_from_file_location('verified_lora_attacks',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def load_geometry(archive):
    source=source_module()
    groups, inventory, inputs=source.load(archive)  # hashes, fields, units and row counts verified first
    with zipfile.ZipFile(archive) as z:
        for condition,runs in groups.items():
            rows=list(csv.DictReader(io.StringIO(z.read(f'dataset/{condition}/data.csv').decode('utf-8-sig'))))
            for run_id,run in runs.items():
                subset=[r for r in rows if int(float(r['runID']))==run_id]
                stamps=np.array([float(r['timestamp[ms]'])/1000 for r in subset])
                if not np.array_equal(stamps,run['t']):raise ValueError('Geometry and RSSI row alignment failed')
                run['z']=np.array([float(r['height[m]'])+float(r['depth[m]']) for r in subset])
                horizontal_distance(run['d'],run['z'])
    return source,groups,inventory,inputs


def horizontal_distance(distance, vertical):
    distance=np.asarray(distance,dtype=float);vertical=np.asarray(vertical,dtype=float)
    if distance.shape!=vertical.shape or not np.isfinite(distance).all() or not np.isfinite(vertical).all():
        raise ValueError('Invalid geometry arrays')
    if np.any(distance<=0) or np.any(vertical<0):raise ValueError('Invalid geometric distance')
    squared=distance**2-vertical**2
    if np.any(squared < -1e-8):raise ValueError('Vertical separation exceeds slant range')
    return np.sqrt(np.maximum(squared,0.))


def claimed_distance(distance, vertical, shift, direction):
    """Local per-packet horizontal claim displacement; no coordinates fabricated."""
    if not np.isfinite(shift) or shift<0:raise ValueError('Invalid shift')
    h=horizontal_distance(distance,vertical);z=np.asarray(vertical)
    if direction=='outward':
        claim=np.hypot(h+shift,z);eligible=np.ones(len(h),dtype=bool)
    elif direction=='inward':
        eligible=h>shift  # do not cross the beacon and still call it an inward claim
        claim=np.hypot(np.where(eligible,h-shift,h),z)
    elif direction=='tangential':
        claim=np.sqrt(h*h+shift*shift+z*z);eligible=np.ones(len(h),dtype=bool)
    else:raise ValueError('Unknown direction')
    return claim,eligible


def scores(model, measured_rssi, true_distance, claim_distance, attacker_slope=None, power_limit=None):
    """Return new arrays; retain the actual RSSI and its real residual as baseline."""
    model=np.asarray(model,dtype=float);r=np.asarray(measured_rssi,dtype=float)
    d=np.asarray(true_distance,dtype=float);q=np.asarray(claim_distance,dtype=float)
    if model.shape!=(2,) or model[1]>=0 or not np.isfinite(model).all():raise ValueError('Invalid detector model')
    if r.shape!=d.shape or d.shape!=q.shape or not np.isfinite(r).all() or not np.isfinite(d).all() or not np.isfinite(q).all() or np.any(d<=0) or np.any(q<=0):raise ValueError('Invalid paired samples')
    slope=model[1] if attacker_slope is None else float(attacker_slope)
    if not np.isfinite(slope) or slope>=0:raise ValueError('Invalid attacker slope')
    power=slope*np.log10(q/d)
    if power_limit is not None:
        if not np.isfinite(power_limit) or power_limit<0:raise ValueError('Invalid power bound')
        power=np.clip(power,-power_limit,power_limit)
    normal_signed=r-(model[0]+model[1]*np.log10(d))
    attacked_signed=(r+power)-(model[0]+model[1]*np.log10(q))
    return np.abs(normal_signed),np.abs(attacked_signed),power


def variant_scores(model,r,d,q,variant):
    if variant=='normal':return scores(model,r,d,d)
    if variant=='position_only':return scores(model,r,d,q,power_limit=0.)
    if variant=='exact_compensation':return scores(model,r,d,q)
    if variant=='bounded_3db':return scores(model,r,d,q,power_limit=3.)
    if variant=='mismatched_n2':return scores(model,r,d,q,attacker_slope=-20.)
    raise ValueError('Unknown attack')


def analyze(archive):
    source,groups,inventory,inputs=load_geometry(archive)
    metrics=[];distribution={v:[] for v in VARIANTS};normal_ref=None
    for condition,runs in groups.items():
        if len(runs)!=3:continue
        ids=sorted(runs)
        for fold in range(3):
            train,cal,test=[runs[ids[(fold+i)%3]] for i in range(3)]
            model=source.fit_model(train)
            threshold=float(np.quantile(np.abs(cal['r']-source.expected(model,cal['d'])),.95))
            if not np.isfinite(threshold) or threshold<=0:raise ValueError('Invalid normal calibration threshold')
            original=test['r'].copy()
            for direction in DIRECTIONS:
                for shift in SHIFTS:
                    claim,eligible=claimed_distance(test['d'],test['z'],shift,direction)
                    count=int(eligible.sum())
                    base=dict(condition=condition,fold=fold,training_run=ids[fold],calibration_run=ids[(fold+1)%3],evaluation_run=ids[(fold+2)%3],
                              direction=direction,claim_horizontal_shift_m=shift,detector_n=float(-model[1]/10),threshold_db=threshold,
                              received_packets=len(eligible),eligible_packets=count,geometry_deferred_packets=int((~eligible).sum()),
                              eligible_fraction=float(eligible.mean()))
                    if count==0:
                        for variant in VARIANTS:metrics.append(dict(**base,variant=variant,alarm_rate=None,baseline_alarm_rate=None,
                            new_alarms_fraction=None,lost_alarms_fraction=None,alarm_disagreements=None,mean_score_db=None,
                            score_p95_db=None,median_abs_power_delta_db=None,p95_abs_power_delta_db=None,
                            required_power_beyond_3db_fraction=None,max_score_difference_from_normal_db=None))
                        continue
                    r=test['r'][eligible];d=test['d'][eligible];q=claim[eligible]
                    required=model[1]*np.log10(q/d)
                    for variant in VARIANTS:
                        normal,attack,power=variant_scores(model,r,d,q,variant)
                        nflag=normal>threshold;aflag=attack>threshold
                        row=dict(**base,variant=variant,alarm_rate=float(aflag.mean()),baseline_alarm_rate=float(nflag.mean()),
                                 new_alarms_fraction=float(np.mean(aflag & ~nflag)),lost_alarms_fraction=float(np.mean(nflag & ~aflag)),
                                 alarm_disagreements=int(np.count_nonzero(nflag!=aflag)),mean_score_db=float(attack.mean()),
                                 score_p95_db=float(np.quantile(attack,.95)),median_abs_power_delta_db=float(np.median(np.abs(power))),
                                 p95_abs_power_delta_db=float(np.quantile(np.abs(power),.95)),
                                 required_power_beyond_3db_fraction=float(np.mean(np.abs(required)>3.)),
                                 max_score_difference_from_normal_db=float(np.max(np.abs(attack-normal))))
                        metrics.append(row)
                        if (direction,shift)==REFERENCE:
                            cdf=np.searchsorted(np.sort(attack/threshold),SCORE_EDGES[1:],side='right')/count
                            distribution[variant].append(dict(cdf=cdf,
                                                              overflow=int(np.sum(attack/threshold>SCORE_EDGES[-1])),count=count))
                    if not np.array_equal(test['r'],original):raise AssertionError('Measured RSSI was modified')
    aggregate=[]
    for direction in DIRECTIONS:
        for shift in SHIFTS:
            for variant in VARIANTS:
                rows=[r for r in metrics if r['direction']==direction and r['claim_horizontal_shift_m']==shift and r['variant']==variant]
                valid=[r for r in rows if r['alarm_rate'] is not None]
                record=dict(direction=direction,claim_horizontal_shift_m=shift,variant=variant,
                            folds_total=len(rows),folds_evaluable=len(valid),
                            eligible_received_packets=sum(r['eligible_packets'] for r in rows),
                            geometry_deferred_packets=sum(r['geometry_deferred_packets'] for r in rows),
                            mean_eligible_fraction=float(np.mean([r['eligible_fraction'] for r in rows])))
                for key in ('alarm_rate','baseline_alarm_rate','new_alarms_fraction','lost_alarms_fraction',
                            'mean_score_db','score_p95_db','median_abs_power_delta_db','p95_abs_power_delta_db',
                            'required_power_beyond_3db_fraction'):
                    record['mean_'+key]=float(np.mean([r[key] for r in valid])) if valid else None
                record['total_alarm_disagreements']=sum(r['alarm_disagreements'] for r in valid)
                record['max_score_difference_from_normal_db']=max((r['max_score_difference_from_normal_db'] for r in valid),default=None)
                aggregate.append(record)
    cdf={v:dict(mean_fold_cdf=np.mean([r['cdf'] for r in rows],axis=0).tolist(),
                overflow_samples=sum(r['overflow'] for r in rows),received_samples=sum(r['count'] for r in rows)) for v,rows in distribution.items()}
    return dict(scope='Real LoRa RSSI plus synthetic receiver-UAV position claims/power changes; not Remote ID evidence',
        source_url=source.URL,source_sha256=source.SHA256,source_members=inputs,
        raw_observations=sum(i['rows'] for i in inventory),conditions=len(groups),run_groups=len(inventory),
        comparison_conditions=len({r['condition'] for r in metrics}),folds=48,
        config=dict(directions=DIRECTIONS,horizontal_shift_m=SHIFTS,variants=VARIANTS,bounded_power_delta_db=3.,
                    mismatched_attacker_n=2.,threshold='Separate normal calibration run absolute-residual 95th percentile',
                    model='Training-only OLS intercept and log-distance slope',split='Three cyclic train/calibration/evaluation run roles per condition',
                    seed=None,randomness='None: paired deterministic transforms',reference_direction=REFERENCE[0],reference_shift_m=REFERENCE[1]),
        provenance=dict(measured='Original RSSI/time and UAV position/altitude, fixed transmitter location',
                        derived='Flat-terrain slant-distance proxy and normal fitted model',
                        synthetic='Per-packet local radial/tangential receiver-UAV claim displacement and additive received-power delta'),
        assumptions=['The original UAV is a receiver, the buried ground node a transmitter; roles are not swapped',
                     'Synthetic power changes would belong to the ground transmitter, not a measured drone transmitter attack',
                     'Exact compensation uses detector slope and true/claimed range every packet: an oracle construction',
                     'Additive dB stress retains received packets; changes in RF reception, interference and saturation are NOT simulated',
                     'Inward displacement cannot pass the beacon; otherwise geometry is deferred, and all variants share this mask',
                     'Tangential displacement is in a local per-packet frame, not a constant map translation',
                     'No direction sensor, independent multi-site observations, or trajectory-consistency check is introduced',
                     'Shared run folds are descriptive; packets and folds are not independent confidence-interval trials'],
        aggregate=aggregate,fold_metrics=metrics,
        normalized_score_distribution=dict(edges=SCORE_EDGES.tolist(),reference=list(REFERENCE),by_variant=cdf))


def save(report,out):
    if out.exists():raise ValueError('Use a fresh output directory')
    out.mkdir(parents=True)
    (out/'summary.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    for name,key in [('fold-metrics.csv','fold_metrics'),('aggregate.csv','aggregate')]:
        with (out/name).open('w',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(report[key][0]),lineterminator='\n')
            writer.writeheader();writer.writerows(report[key])
    files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),Path(__file__).with_name('normal_residuals.py'),Path(__file__).resolve().parents[1]/'week26-rssi-privacy/recheck_lora.py']}
    (out/'code-hashes.json').write_text(json.dumps(files,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--archive',type=Path,required=True);p.add_argument('--out',type=Path,required=True);args=p.parse_args()
    report=analyze(args.archive);save(report,args.out)
    print(json.dumps([r for r in report['aggregate'] if (r['direction'],r['claim_horizontal_shift_m'])==REFERENCE],indent=2))
