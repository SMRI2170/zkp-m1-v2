"""Same-frame four-station SNR differences; descriptive, not hardware calibration.

Public outputs contain aggregates only, never positions or individual packets.
"""
import argparse
from collections import Counter,defaultdict
import csv,hashlib,itertools,json
from pathlib import Path
import numpy as np
from audit_loraiq import audit as source_audit

PAIRS=list(itertools.combinations(range(4),2))
FIELDS=('latitude','longitude','payload_base64','sf','cr','fc','bandwidth','area','area_type')
WINDOW=10.
MIN_WINDOW=5
GAP=2.


def centered(snr):
    s=np.asarray(snr,dtype=float)
    if s.ndim!=2 or s.shape[1]!=4 or not np.isfinite(s).all():raise ValueError('Expected finite N x 4 SNR')
    return s-s.mean(axis=1,keepdims=True)


def select_groups(rows):
    grouped=defaultdict(list)
    for r in rows:
        if r['area_type'] in ('drone_los','drone_nlos'):grouped[(r['name'],r['transmission_idx'])].append(r)
    sessions=defaultdict(list);areas=defaultdict(set);reasons=Counter();overlap=Counter()
    for (session,_),g in grouped.items():
        ids=[r['rrh_idx'] for r in g]
        flags=dict(not_exactly_four=len(g)!=4 or set(ids)!=set('1234'),
            missing_position=any(not r['latitude'] or not r['longitude'] for r in g),
            inconsistent_identity=any(len({r[k] for r in g})!=1 for k in FIELDS))
        overlap.update(k for k,v in flags.items() if v)
        reason=next((k for k,v in flags.items() if v),None)
        if reason:reasons[reason]+=1;continue
        ordered=sorted(g,key=lambda r:r['rrh_idx'])
        t=np.array([float(r['rx_timestamp_full'])+float(r['rx_timestamp_frac']) for r in ordered])
        s=np.array([float(r['snr']) for r in ordered])
        if not np.isfinite(t).all() or not np.isfinite(s).all():raise ValueError('Nonfinite observations')
        sessions[session].append((float(np.median(t)),s,float(np.ptp(t))))
        areas[session].add(g[0]['area_type'])
    arrays={}
    for session,items in sorted(sessions.items()):
        items.sort(key=lambda v:v[0]);t=np.array([v[0] for v in items])
        if np.any(np.diff(t)<=0):raise ValueError('Ambiguous/nonincreasing frame reference times')
        arrays[session]=dict(t=t,s=np.array([v[1] for v in items]),spread=np.array([v[2] for v in items]),areas=sorted(areas[session]))
    return arrays,dict(total_uav_groups=len(grouped),exclusive_exclusions=dict(reasons),
        overlapping_exclusion_flags=dict(overlap),accepted_four_station_groups=sum(len(a['t']) for a in arrays.values()))


def describe(values):
    x=np.asarray(values,dtype=float)
    if not len(x) or not np.isfinite(x).all():raise ValueError('Invalid statistic input')
    q=np.quantile(x,[.05,.25,.5,.75,.95])
    return dict(n=len(x),mean_db=float(x.mean()),sd_db=float(x.std(ddof=1)) if len(x)>1 else None,
        p05_db=float(q[0]),p25_db=float(q[1]),median_db=float(q[2]),p75_db=float(q[3]),p95_db=float(q[4]),
        iqr_db=float(q[3]-q[1]))


def adjacent(t,x,gap=GAP):
    dt=np.diff(t);mask=(dt>0)&(dt<=gap);a=x[:-1][mask];b=x[1:][mask]
    correlation=float(np.corrcoef(a,b)[0,1]) if len(a)>=3 and np.std(a)>0 and np.std(b)>0 else None
    return dict(adjacent_pairs=int(mask.sum()),lag_one_correlation=correlation,
        median_adjacent_dt_s=float(np.median(dt[mask])) if mask.any() else None)


def time_windows(t,min_count=MIN_WINDOW,width=WINDOW):
    elapsed=t-t[0];index=np.floor(elapsed/width).astype(int);result=[]
    for k in np.unique(index):
        mask=index==k
        if mask.sum()>=min_count and (k+1)*width<=elapsed[-1]:result.append((int(k),mask))
    return result


def split_drift(t,values,min_count=20):
    duration=t[-1]-t[0];early=t<t[0]+duration/3;late=t>=t[0]+2*duration/3
    n0=int(early.sum());n1=int(late.sum())
    if min(n0,n1)<min_count:return dict(early_n=n0,late_n=n1,early_median_db=None,late_median_db=None,late_minus_early_db=None)
    a=float(np.median(values[early]));b=float(np.median(values[late]))
    return dict(early_n=n0,late_n=n1,early_median_db=a,late_median_db=b,late_minus_early_db=b-a)


def analyze(raw):
    verified=source_audit(raw)
    with (raw/'dataset.csv').open() as f:arrays,cohort=select_groups(list(csv.DictReader(f)))
    tables={k:[] for k in ['pair_stats','station_stats','histograms','time_windows','session_quality']}
    edges=np.arange(-80.,82.,2.)
    for sid,(session,a) in enumerate(arrays.items(),1):
        t=a['t'];s=a['s'];c=centered(s);windows=time_windows(t)
        identity=dict(session=f'S{sid}',source_session_name=session)
        tables['session_quality'].append(dict(**identity,n=len(t),duration_s=float(t[-1]-t[0]),
            reference_gap_over_2s=int(np.sum(np.diff(t)>GAP)),
            reference_dt_median_s=float(np.median(np.diff(t))),
            max_station_time_spread_s=float(a['spread'].max()),
            accepted_windows=len(windows),window_covered_frames=sum(int(mask.sum()) for _,mask in windows),
            area_types=','.join(a['areas'])))
        quantities=[('pair',f'{i+1}-{j+1}',s[:,i]-s[:,j]) for i,j in PAIRS]+[('station',str(i+1),c[:,i]) for i in range(4)]
        for kind,label,x in quantities:
            stats=dict(**identity,quantity=label,**describe(x),**adjacent(t,x),**split_drift(t,x))
            tables['pair_stats' if kind=='pair' else 'station_stats'].append(stats)
            hist,_=np.histogram(x,edges)
            if np.any(x<edges[0]) or np.any(x>edges[-1]):raise ValueError('Histogram range excludes data')
            for lo,hi,n in zip(edges[:-1],edges[1:],hist):
                tables['histograms'].append(dict(session=identity['session'],kind=kind,quantity=label,lower_db=float(lo),upper_db=float(hi),count=int(n)))
            for index,mask in windows:
                tables['time_windows'].append(dict(session=identity['session'],kind=kind,quantity=label,window_index=index,
                    elapsed_start_s=index*WINDOW,**describe(x[mask])))
    sessions=len(arrays);station_equal_means=[]
    for i in range(4):
        r=[v for v in tables['station_stats'] if v['quantity']==str(i+1)]
        station_equal_means.append(dict(station=str(i+1),session_equal_mean_centered_db=float(np.mean([v['mean_db'] for v in r])),
            session_median_min_db=min(v['median_db'] for v in r),session_median_max_db=max(v['median_db'] for v in r)))
    result=dict(source_url=verified['source_url'],source_sha256=verified['inputs']['dataset.csv']['sha256'],
        scope='SNR dB differences on strict same-frame four-station received UAV subset; not RSSI or hardware bias calibration',
        config=dict(window_seconds=WINDOW,min_frames_per_window=MIN_WINDOW,adjacent_max_gap_s=GAP,
                    drift='elapsed-time first third vs final third; >=20 frames in each',histogram_edges_db=edges.tolist()),
        cohort=cohort,sessions=sessions,station_session_equal_means=station_equal_means,
        definitions=dict(pair='SNR_i - SNR_j on same four-receiver frame',station='SNR_i - arithmetic mean of four SNR dB values on same frame',
            bias='Descriptive station-relative offset mixing propagation, noise floor, estimator and receiver effects; NOT hardware calibration',
            temporal='10-second elapsed bins with >=5 frames; gaps are not interpolated or filled',
            correlation='Adjacent accepted-frame pairs with positive gap <=2s, not fixed-lag seconds or independent samples'),
        limitations=['Complete-case selection of four observed receivers may favor stronger/more available links',
            'Transmitter positions are payload-derived; UAV height and independent truth are unavailable',
            'Motion/propagation differences confound station offset and temporal drift; hardware bias is not identified',
            'No assumption of constant/equal noise floors or fixed receiver gain is verified',
            'Six pair differences contain only three independent contrasts algebraically; no independent-trial inference',
            'No attack detection rate, RF packet loss rate, AoA, dBm RSSI or asynchronous single-packet solution evaluated'],
        tables=tables,
        code_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),Path(__file__).with_name('audit_loraiq.py')]})
    return result


def save(result,out):
    if out.exists():raise ValueError('Use a fresh output directory')
    out.mkdir(parents=True)
    (out/'summary.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    for key,rows in result['tables'].items():
        with (out/(key+'.csv')).open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--raw',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    result=analyze(a.raw);save(result,a.out)
    print(json.dumps({k:result[k] for k in ['cohort','sessions','station_session_equal_means']},indent=2))
