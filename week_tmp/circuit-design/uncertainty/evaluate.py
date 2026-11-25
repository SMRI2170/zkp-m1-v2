#!/usr/bin/env python3
"""Read-only field metadata audit + fixed-model uncertainty sensitivity. No spoof truth claimed."""
import argparse,collections,csv,hashlib,json,math,os,sqlite3,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'week29/scripts'))
from build_quality_manifest import load_selection,private_path
from evaluate_claim_attacks import split_time,prediction,compensation
HORIZONTAL={1:18520,2:7408,3:3704,4:1852,5:926,6:555.6,7:185.2,8:92.6,9:30,10:10,11:3,12:1}
VERTICAL={1:150,2:45,3:25,4:10,5:3,6:1}

def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def number(v):
    if isinstance(v,bool):return None
    try:r=float(v)
    except (TypeError,ValueError):return None
    return r if math.isfinite(r) else None

def accuracy_codes(payload):
    b=bytes.fromhex(payload)
    if len(b)<3 or b[:2]!=b'\xf0\x19' or not 1<=b[2]<=9 or len(b)!=3+25*b[2]:raise ValueError('Not exact version-0 pack')
    locations=[]
    for i in range(b[2]):
        m=b[3+25*i:3+25*(i+1)]
        if m[0]&15:raise ValueError('Mixed/non-v0 pack')
        if m[0]>>4==1:locations.append(m)
    if len(locations)!=1:raise ValueError('Ambiguous/missing location')
    m=locations[0]
    return [m[19]&15,m[19]>>4,m[20]>>4,m[23]&15]

def radii(codes):
    h,v,b,t=codes
    return dict(horizontal_m=HORIZONTAL.get(h),vertical_m=VERTICAL.get(v),baro_m=VERTICAL.get(b),time_s=t/10 if 1<=t<=15 else None)

def distance_bounds(distance,error):
    if not all(math.isfinite(x) and x>=0 for x in [distance,error]):raise ValueError('Invalid distance/error')
    return max(0,distance-error),distance+error

def interval_decision(rssi,lower,upper,a,n,threshold):
    # The interval is conditional on assumed error radii, not a calibrated confidence interval.
    if not all(math.isfinite(x) for x in [rssi,lower,upper,a,n,threshold]) or n<=0 or threshold<0 or lower<0 or upper<lower:raise ValueError('Invalid model interval')
    if lower<=0:return 'hold' # no log(0), and do not silently truncate to a near-field radius
    p_low=prediction(upper,a,n);p_high=prediction(lower,a,n)
    if rssi<p_low-threshold or rssi>p_high+threshold:return 'alarm'
    if p_high-threshold<=rssi<=p_low+threshold:return 'consistent'
    return 'hold'

def slant_bounds(horizontal,delta_height,herror,verror):
    if not all(math.isfinite(x) and x>=0 for x in [horizontal,herror,verror]) or not math.isfinite(delta_height):raise ValueError('Invalid geometry')
    lo,hi=distance_bounds(horizontal,herror);z=abs(delta_height)
    return math.hypot(lo,max(0,z-verror)),math.hypot(hi,z+verror)

def stats(values):
    x=sorted(v for v in values if v is not None and math.isfinite(v))
    def q(p):
        if not x:return None
        z=(len(x)-1)*p;i=int(z);return x[i]+(x[min(i+1,len(x)-1)]-x[i])*(z-i)
    return dict(n=len(x),min=min(x) if x else None,median=q(.5),p90=q(.9),max=max(x) if x else None)

def write_csv(p,rows):
    with p.open('w',newline='') as f:
        if rows:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def main():
    pa=argparse.ArgumentParser();pa.add_argument('--raw-config',type=Path,required=True);pa.add_argument('--positions-config',type=Path,required=True)
    pa.add_argument('--selection-manifest',type=Path,required=True);pa.add_argument('--reference-probe',type=Path,required=True)
    pa.add_argument('--output',type=Path,required=True);pa.add_argument('--private-output',type=Path,required=True);args=pa.parse_args()
    os.umask(0o077);private_path(args.private_output)
    if args.output.exists() or args.private_output.exists():raise ValueError('Fresh output directories required')
    rawconf=json.loads(private_path(args.raw_config,existing=True).read_text());conf=json.loads(private_path(args.positions_config,existing=True).read_text())
    source_hashes={};audit={};meta={};packs=[];expected=[]
    ident=json.loads(private_path(rawconf['identity_file'],existing=True).read_text())['claimed_id']
    for source in rawconf['sources']:
        node=source['node'];dp=private_path(source['database'],existing=True);rp=private_path(source['reference_jsonl'],existing=True)
        for p in [dp,rp]:source_hashes[str(p)]=digest(p)
        refs={}
        for line in rp.open():
            x=json.loads(line);r=x['reference']
            if r.get('reference_decode_ok') and bytes.fromhex(r.get('id_hex','')).rstrip(b'\0').decode(errors='replace')==ident:
                refs[x['capture']['odid_payload_hex']]=r
        db=sqlite3.connect(dp.resolve().as_uri()+'?mode=ro',uri=True)
        counts=collections.Counter();fixes=0
        for raw, in db.execute('select raw_json from receiver_fixes'):
            f=json.loads(raw);fixes+=1
            for k in ['latitude','longitude','accuracy_m','altitude_ellipsoid_m','vertical_accuracy_m','altitude_accuracy_m','fix_elapsed_us']:
                counts[k]+=number(f.get(k)) is not None
        target=collections.Counter();codes=collections.Counter();hacc=[];ages=[];time_bounds=[]
        for raw, in db.execute('select raw_json from observations'):
            o=json.loads(raw);payload=o.get('odid_payload_hex');r=refs.get(payload)
            if not r or not r.get('location_valid'):continue
            code=accuracy_codes(payload);packs.append(payload);expected.append(code);codes[tuple(code)]+=1
            fix=o.get('receiver_position') or {};rr=radii(code)
            for k in ['latitude','longitude','accuracy_m','altitude_ellipsoid_m','vertical_accuracy_m','altitude_accuracy_m','fix_elapsed_us']:
                target[k]+=number(fix.get(k)) is not None
            hacc.append(number(fix.get('accuracy_m')))
            delta=number(fix.get('scan_delta_us'));ages.append(abs(delta)/1e6 if delta is not None else None)
            time_bounds.append(number(o.get('time_uncertainty_ms')))
            key=(node,str(o.get('boot_scope') or ''),str(o.get('monotonic_time_us')))
            if key in meta:raise ValueError('Ambiguous per-node observation key')
            meta[key]=dict(**rr,codes=code,receiver_vertical_accuracy_m=number(fix.get('vertical_accuracy_m')),time_uncertainty_ms=number(o.get('time_uncertainty_ms')))
        db.close()
        audit[node]=dict(fix_rows=fixes,fix_nonnull=dict(counts),target_rows=sum(codes.values()),target_nonnull=dict(target),
            rid_accuracy_codes=[dict(horizontal=k[0],vertical=k[1],baro=k[2],time=k[3],rows=v,reported=radii(k)) for k,v in codes.items()],
            target_receiver_horizontal_accuracy_m=stats(hacc),fix_age_s=stats(ages),clock_uncertainty_ms=stats(time_bounds))
    run=subprocess.run([str(args.reference_probe.resolve())],input='\n'.join(packs)+'\n',text=True,capture_output=True,check=True)
    actual=[json.loads(x) for x in run.stdout.splitlines()]
    if actual!=expected:raise ValueError('Accuracy extraction disagrees with pinned v0 C reference')
    positions=private_path(conf['positions'],existing=True);source_hashes[str(positions)]=digest(positions)
    manifest=private_path(args.selection_manifest,existing=True);source_hashes[str(manifest)]=digest(manifest)
    with positions.open() as f:allrows=list(csv.DictReader(f))
    selected=load_selection(manifest,positions,allrows)
    rows=[]
    for r in selected:
        if r['node']!='Pixel':continue
        row=dict(source=r,boot=r['boot_scope'],time=float(r['observed_us'])/1e6,distance=float(r['claimed_horizontal_distance_m']),rssi=float(r['rssi_dbm']))
        row['metadata']=meta[(r['node'],r['boot_scope'],str(int(float(r['observed_us']))))]
        rows.append(row)
    train,cal,test=split_time(rows)
    baseline_path=ROOT/'week29/results/issue96-attacks-a/summary.json';base=json.loads(baseline_path.read_text());a=base['model_intercept_dbm'];n=base['horizontal_proxy_n'];tau=base['threshold_db']
    baseline=sum(abs(r['rssi']-prediction(r['distance'],a,n))>tau for r in test)
    if [len(train),len(cal),len(test),baseline]!=[52,26,27,13]:raise ValueError('Frozen baseline changed')
    scenarios=[dict(name='point',k=0,rid=False,speed=0,extra=0)]
    scenarios += [dict(name=f'phone_x{k}',k=k,rid=False,speed=0,extra=0) for k in [1,2,3]]
    scenarios += [dict(name=f'phone_x{k}_rid_reported',k=k,rid=True,speed=0,extra=0) for k in [1,2,3]]
    scenarios += [dict(name=f'phone_x1_rid_speed{v}_clock{t}',k=1,rid=True,speed=v,extra=t) for v in [5,15] for t in [0,.5,2]]
    paired=[];summary=[]
    for scenario in scenarios:
        for attack in ['unmodified','claim_away_50m','claim_away_50m_ideal_power']:
            counter=collections.Counter()
            for i,row in enumerate(test):
                d=row['distance'];md=row['metadata'];src=row['source'];changed=d+(50 if attack!='unmodified' else 0)
                rssi=row['rssi']+(compensation(d,changed,n) if attack.endswith('ideal_power') else 0)
                assumed_error=scenario['k']*float(src['accuracy_m'])
                if scenario['rid']:assumed_error+=md['horizontal_m']
                assumed_error+=scenario['speed']*(float(src['fix_delta_s'])+(md['time_s'] or 0)+scenario['extra'])
                low,high=distance_bounds(changed,assumed_error);status=interval_decision(rssi,low,high,a,n,tau);counter[status]+=1
                paired.append(dict(row_index=i,scenario=scenario['name'],attack=attack,distance_low_m=low,distance_high_m=high,status=status,assumed_radius_m=assumed_error))
            summary.append(dict(scenario=scenario['name'],attack=attack,n=len(test),consistent=counter['consistent'],alarm=counter['alarm'],hold=counter['hold'],alarm_fraction=counter['alarm']/len(test),hold_fraction=counter['hold']/len(test)))
    geometry=[]
    for ev in [1,3,5,10,20,50]:
        widths=[]
        for row in test:
            src=row['source'];dh=number(src.get('drone_geo_altitude_m'));oh=number(src.get('phone_altitude_m'))
            if dh is None or oh is None:continue
            lo,hi=slant_bounds(row['distance'],dh-oh,float(src['accuracy_m'])+row['metadata']['horizontal_m'],ev+row['metadata']['vertical_m'])
            widths.append(hi-lo)
        geometry.append(dict(assumed_phone_vertical_radius_m=ev,rid_reported_vertical_radius_m=10,assumed_common_altitude_datum=True,**stats(widths)))
    for p,h in source_hashes.items():
        if digest(p)!=h:raise ValueError('Source changed')
    args.private_output.mkdir(parents=True,mode=0o700);args.output.mkdir(parents=True)
    write_csv(args.private_output/'paired-intervals-private.csv',paired)
    (args.private_output/'input-hashes-private.json').write_text(json.dumps(source_hashes,indent=2))
    result=dict(scope='real RSSI/positions; synthetic claim/power changes; assumed uncertainty-radius sensitivity, not true spoof TPR/FPR',nodes=audit,
        reference_accuracy_code_rows=len(actual),reference_accuracy_code_matches=len(actual),reference_commit='6b046f4af56b25ffc04dc5130c3308c697bab89c',
        frozen_split=[len(train),len(cal),len(test)],unmodified_point_alarms=baseline,
        actual_3d_error_evaluation='NOT_EVALUABLE_receiver_vertical_accuracy_and_common_datum_unverified',
        actual_clock_error_evaluation='NOT_EVALUABLE_RID_epoch_and_clock_offset_not_verified',
        independent_position_error='NOT_EVALUABLE_no_independent_truth',
        conditional_sensitivity='OS 68% radius multiplied by 1/2/3; not guaranteed confidence levels. RID radii self-reported, attacker-controlled.',
        geometry_scope='hypothetical common altitude datum and assumed phone vertical radii; no RSSI classifier applied in 3D',
        original_hashes_unchanged=True,code_sha256=digest(__file__),baseline_summary_sha256=digest(baseline_path))
    (args.output/'audit-summary.json').write_text(json.dumps(result,indent=2)+'\n');write_csv(args.output/'sensitivity.csv',summary);write_csv(args.output/'height-sensitivity.csv',geometry)
    plot(args.output,summary,geometry)
    print(json.dumps(dict(audit_rows=len(actual),frozen_evaluation=len(test),baseline_alarms=baseline,scenarios=len(scenarios),outputs=str(args.output))))

def plot(output,rows,geometry):
    import matplotlib;matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,3,figsize=(13,4.5),sharey=True)
    for ax,attack in zip(axes,['unmodified','claim_away_50m','claim_away_50m_ideal_power']):
        selected=[next(r for r in rows if r['attack']==attack and r['scenario']==name) for name in ['point','phone_x1','phone_x2','phone_x3']]
        for status,color in [('alarm','#b44d4d'),('hold','#e0a93a'),('consistent','#285b8e')]:ax.plot(range(4),[r[status]/r['n']*100 for r in selected],marker='o',label=status,color=color)
        ax.set(title=attack.replace('_',' '),xlabel='Phone reported horizontal radius multiplier',xticks=range(4),ylim=(0,105));ax.grid(alpha=.2)
    axes[0].set_ylabel('Fraction of the same 27 records [%]');axes[-1].legend();fig.suptitle('Conditional radius sensitivity; real RSSI + synthetic attacks; not spoof TPR/FPR')
    fig.tight_layout();fig.savefig(output/'01_horizontal_uncertainty.png',dpi=170);plt.close(fig)
    fig,ax=plt.subplots(figsize=(10,4.8));names=['point','phone_x1_rid_reported','phone_x1_rid_speed5_clock0','phone_x1_rid_speed15_clock0','phone_x1_rid_speed15_clock2']
    for attack in ['unmodified','claim_away_50m','claim_away_50m_ideal_power']:
        vals=[next(r for r in rows if r['attack']==attack and r['scenario']==name) for name in names]
        ax.plot(range(len(names)),[r['alarm_fraction']*100 for r in vals],marker='o',label=attack)
    ax.set(xticks=range(len(names)),xticklabels=['Point','Phone + RID','+ 5 m/s','+ 15 m/s','+ clock 2 s'],ylabel='Alarm fraction [%]',ylim=(0,105),title='Conditional position/time budgets; alignment and speed are assumed')
    ax.legend(fontsize=8);ax.grid(alpha=.2);fig.tight_layout();fig.savefig(output/'02_time_budget_sensitivity.png',dpi=170);plt.close(fig)
    fig,ax=plt.subplots(figsize=(8,4.5));x=[g['assumed_phone_vertical_radius_m'] for g in geometry]
    for key,label in [('median','median'),('p90','90th percentile')]:ax.plot(x,[g[key] for g in geometry],marker='o',label=label)
    ax.set(xlabel='Assumed phone vertical radius [m]',ylabel='Possible slant-distance interval width [m]',title='Geometry sensitivity ONLY: common height datum assumed, not verified');ax.legend();ax.grid(alpha=.2)
    fig.tight_layout();fig.savefig(output/'03_height_uncertainty_assumed.png',dpi=170);plt.close(fig)

if __name__=='__main__':main()
