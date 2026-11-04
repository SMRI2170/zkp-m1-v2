"""Held-out-session normal SNR checks with constant and horizontal-range proxies.

No attacks are injected. Geometry uses payload coordinates and has no UAV height.
"""
import argparse,csv,hashlib,itertools,json,re
from collections import defaultdict
from pathlib import Path
import numpy as np
from audit_loraiq import audit as source_audit
from snr_four_station import select_groups,centered,time_windows,FIELDS


def horizontal_ranges(position,receivers):
    p=np.radians(np.asarray(position,dtype=float));r=np.radians(np.asarray(receivers,dtype=float))
    if p.ndim!=2 or p.shape[1]!=2 or r.shape!=(4,2) or not np.isfinite(p).all() or not np.isfinite(r).all():raise ValueError('Invalid coordinates')
    dlat=p[:,None,0]-r[None,:,0];dlon=p[:,None,1]-r[None,:,1]
    a=np.sin(dlat/2)**2+np.cos(p[:,None,0])*np.cos(r[None,:,0])*np.sin(dlon/2)**2
    distance=2*6371000*np.arcsin(np.sqrt(np.clip(a,0,1)))
    if np.any(distance<=0):raise ValueError('Zero horizontal range cannot be logged')
    return distance


def log_features(distance):
    d=np.asarray(distance,dtype=float)
    if d.ndim!=2 or d.shape[1]!=4 or not np.isfinite(d).all() or np.any(d<=0):raise ValueError('Invalid range matrix')
    return centered(np.log10(d))


def load(raw):
    verified=source_audit(raw)
    text=(raw/'rrh_locations.md').read_text();receivers=[]
    blocks=re.findall(r'### RRH(\d):\s*(.*?)(?=### RRH|\Z)',text,re.S)
    by_id={int(i):v for i,v in blocks}
    if set(by_id)!={1,2,3,4}:raise ValueError('Invalid receiver location metadata')
    for i in range(1,5):
        vals=[]
        for name in ['Latitude','Longitude']:
            m=re.search(name+r':\s*([-+]?\d+(?:\.\d+)?)',by_id[i])
            if m is None:raise ValueError('Missing receiver coordinate')
            vals.append(float(m[1]))
        receivers.append(vals)
    with (raw/'dataset.csv').open() as f:rows=list(csv.DictReader(f))
    arrays,cohort=select_groups(rows);groups=defaultdict(list)
    for r in rows:
        if r['area_type'] in ('drone_los','drone_nlos'):groups[r['name'],r['transmission_idx']].append(r)
    positions=defaultdict(dict)
    for (session,_),g in groups.items():
        if len(g)!=4 or {r['rrh_idx'] for r in g}!=set('1234') or any(not r['latitude'] or not r['longitude'] for r in g):continue
        if any(len({r[k] for r in g})!=1 for k in FIELDS):continue
        time=float(np.median([float(r['rx_timestamp_full'])+float(r['rx_timestamp_frac']) for r in g]))
        if time in positions[session]:raise ValueError('Ambiguous coordinate-time correspondence')
        positions[session][time]=[float(g[0]['latitude']),float(g[0]['longitude'])]
    result={}
    for index,(session,a) in enumerate(sorted(arrays.items()),1):
        if len(positions[session])!=len(a['t']):raise ValueError('Cohort mismatch')
        d=horizontal_ranges([positions[session][t] for t in a['t']],receivers)
        result[f'S{index}']=dict(name=session,t=a['t'],y=centered(a['s']),x=log_features(d),areas=a['areas'])
    return result,verified,cohort


def fit(sessions,method):
    if method not in ('constant','horizontal_geometry'):raise ValueError('Unknown model')
    # Equal total weight per training session, regardless of packet counts.
    mx=np.mean([s['x'].mean(axis=0) for s in sessions],axis=0)
    my=np.mean([s['y'].mean(axis=0) for s in sessions],axis=0)
    numerator=np.mean([np.mean(np.sum((s['x']-mx)*(s['y']-my),axis=1)) for s in sessions])
    denominator=np.mean([np.mean(np.sum((s['x']-mx)**2,axis=1)) for s in sessions])
    if method=='horizontal_geometry' and denominator<=1e-12:raise ValueError('Slope is not identifiable from training geometry')
    slope=float(numerator/denominator) if method=='horizontal_geometry' else 0.
    bias=my-slope*mx;bias-=bias.mean()
    return dict(method=method,slope_db_per_log10=slope,fitted_n=-slope/10 if method=='horizontal_geometry' else None,
        decaying_slope=(slope<0) if method=='horizontal_geometry' else None,station_offsets_db=bias.tolist())


def predict(model,x):return model['slope_db_per_log10']*x+np.asarray(model['station_offsets_db'])


def scores(model,s):
    residual=s['y']-predict(model,s['x'])
    return np.sqrt(np.mean(residual**2,axis=1))


def evaluate(model,calibration,target):
    c=scores(model,calibration);v=scores(model,target);threshold=float(np.quantile(c,.95))
    cw=time_windows(calibration['t']);tw=time_windows(target['t'])
    cs=np.array([np.median(c[mask]) for _,mask in cw]);ts=np.array([np.median(v[mask]) for _,mask in tw])
    wt=float(np.quantile(cs,.95)) if len(cs) else None
    return dict(calibration_frames=len(c),evaluation_frames=len(v),threshold_db=threshold,
        calibration_normal_alarm_rate=float(np.mean(c>threshold)),normal_alarm_rate=float(np.mean(v>threshold)),
        centered_snr_rmse_db=float(np.sqrt(np.mean(v**2))),median_score_db=float(np.median(v)),score_p95_db=float(np.quantile(v,.95)),
        calibration_windows=len(cw),evaluation_windows=len(tw),window_threshold_db=wt,
        normal_window_alarm_rate=float(np.mean(ts>wt)) if len(ts) and wt is not None else None)


def analyze(raw):
    sessions,verified,cohort=load(raw);los=[k for k,v in sessions.items() if v['areas']==['drone_los']]
    nlos=[k for k,v in sessions.items() if v['areas']==['drone_nlos']]
    if len(los)!=4 or len(nlos)!=2:raise ValueError('Unexpected domain/session counts')
    rows=[];parameters=[];fold=0
    for training in itertools.combinations(los,2):
        others=[s for s in los if s not in training]
        train=[sessions[s] for s in training]
        xmin=np.min(np.vstack([s['x'] for s in train]),axis=0);xmax=np.max(np.vstack([s['x'] for s in train]),axis=0)
        for cal in others:
            fold+=1;held=next(s for s in others if s!=cal)
            for method in ['constant','horizontal_geometry']:
                model=fit(train,method)
                parameters.append(dict(fold=fold,training_sessions=','.join(training),calibration_session=cal,heldout_los_session=held,**model))
                for target in [held]+nlos:
                    s=sessions[target]
                    outside=np.any((s['x']<xmin)|(s['x']>xmax),axis=1)
                    rows.append(dict(fold=fold,training_sessions=','.join(training),calibration_session=cal,evaluation_session=target,
                        domain='LoS_holdout' if target==held else 'NLoS_transfer',method=method,
                        feature_component_range_outside_fraction=float(outside.mean()),**evaluate(model,sessions[cal],s)))
    aggregates=[]
    for method in ['constant','horizontal_geometry']:
        for domain in ['LoS_holdout','NLoS_transfer']:
            selected=[r for r in rows if r['method']==method and r['domain']==domain]
            by_session=defaultdict(list)
            for r in selected:by_session[r['evaluation_session']].append(r)
            valid_windows=[r for r in selected if r['normal_window_alarm_rate'] is not None]
            aggregates.append(dict(method=method,domain=domain,evaluation_rows=len(selected),evaluation_sessions=len(by_session),
                session_equal_mean_normal_alarm_rate=float(np.mean([np.mean([r['normal_alarm_rate'] for r in group]) for group in by_session.values()])),
                session_equal_mean_rmse_db=float(np.mean([np.mean([r['centered_snr_rmse_db'] for r in group]) for group in by_session.values()])),
                row_alarm_rate_min=min(r['normal_alarm_rate'] for r in selected),row_alarm_rate_max=max(r['normal_alarm_rate'] for r in selected),
                window_evaluable_rows=len(valid_windows),window_evaluable_sessions=len({r['evaluation_session'] for r in valid_windows}),
                mean_evaluable_window_alarm_rate=float(np.mean([r['normal_window_alarm_rate'] for r in valid_windows])) if valid_windows else None))
    code=[Path(__file__),Path(__file__).with_name('snr_four_station.py'),Path(__file__).with_name('audit_loraiq.py')]
    return dict(source_url=verified['source_url'],source_sha256=verified['inputs']['dataset.csv']['sha256'],
        receiver_location_sha256=verified['inputs']['rrh_locations.md']['sha256'],cohort=cohort,
        session_inventory=[dict(session=k,source_session_name=v['name'],domain=v['areas'][0],frames=len(v['t'])) for k,v in sessions.items()],
        config=dict(training='2 LoS sessions, equal session weight',calibration='1 separate LoS session, 95th percentile of normal scores',
            evaluation='remaining LoS session plus both NLoS sessions, never used for fit or thresholds',folds=12,
            feature='centered log10 horizontal haversine ranges; UAV altitude unavailable',
            score='RMS of four centered-SNR prediction residuals in dB',window='10s, >=5 frames; separate normal median-score threshold',
            seed=None),
        limitations=['No attacks; all alarm rates concern presumed-normal measured data',
            'Payload-derived positions are used as annotations, not independent or authenticated truth',
            'Horizontal-range approximation and fitted slope are not true 3D path loss or hardware calibration',
            'Folds share sessions and NLoS data are reused; no independent-packet/fold confidence intervals',
            'No NLoS training/calibration: only two sparse NLoS sessions, assessed as transfer stress',
            'Feature component min/max check is a proxy, not proof of geographic interpolation',
            'Same-frame four-station observations do not solve arbitrary-power asynchronous single-RSSI identification'],
        parameters=parameters,rows=rows,aggregates=aggregates,
        code_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in code})


def save(x,out):
    if out.exists():raise ValueError('Use a fresh output directory')
    out.mkdir(parents=True);(out/'summary.json').write_text(json.dumps(x,indent=2,allow_nan=False)+'\n')
    for name in ['rows','aggregates']:
        with (out/(name+'.csv')).open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(x[name][0]),lineterminator='\n');w.writeheader();w.writerows(x[name])

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--raw',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    x=analyze(a.raw);save(x,a.out);print(json.dumps(x['aggregates'],indent=2))
