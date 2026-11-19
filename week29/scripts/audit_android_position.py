#!/usr/bin/env python3
"""Issue91: audit phone fixes and RID associations; no independent location truth assumed."""
import argparse
import collections
import csv
import hashlib
import json
import math
import os
import sqlite3
from pathlib import Path

from analyze_confirmed_drone import horizontal_distance
from analyze_b_snapshot import percentile
from audit_field_time import describe


def valid_fix(f):
    fields=[f.get('latitude'),f.get('longitude'),f.get('accuracy_m'),f.get('fix_elapsed_us')]
    return (all(isinstance(x,(float,int)) and not isinstance(x,bool) and math.isfinite(x) for x in fields)
            and -90<=fields[0]<=90 and -180<=fields[1]<=180 and fields[2]>=0 and fields[3]>0)


def fix_key(boot,f):return (str(boot or ''),f.get('fix_elapsed_us'),f.get('provider'))


def association(r,index):
    if r.get('cache_stale') is True:return 'STALE_WIFI_OBSERVATION'
    if r.get('cache_stale') is not False:return 'WIFI_FRESHNESS_UNKNOWN'
    fix=r.get('receiver_position') or {}
    if fix.get('match_status')!='MATCHED':return str(fix.get('match_status') or 'POSITION_MISSING')
    if not valid_fix(fix):return 'INVALID_FIX'
    if fix.get('mock') is not False:return 'MOCK_OR_UNKNOWN'
    observed=r.get('monotonic_time_us')
    if not isinstance(observed,(float,int)) or isinstance(observed,bool) or not math.isfinite(observed) or observed<=0:return 'OBSERVED_TIME_UNKNOWN'
    delta=fix['fix_elapsed_us']-observed
    if abs(delta)>2_000_000:return 'DELTA_OVER_2_SECONDS'
    if fix.get('scan_delta_us')!=delta:return 'DELTA_FIELD_MISMATCH'
    boot=str(r.get('boot_scope') or '')
    if not boot or boot.startswith('unknown-'):return 'BOOT_UNKNOWN'
    hits=index.get(fix_key(boot,fix),[])
    if len(hits)!=1:return 'STANDALONE_FIX_MISSING_OR_AMBIGUOUS'
    standalone=hits[0]
    if not valid_fix(standalone) or standalone.get('mock') is not False:return 'INVALID_STANDALONE_FIX'
    if any(abs(standalone[k]-fix[k])>1e-8 for k in ['latitude','longitude','accuracy_m']):return 'FIX_CONTENT_MISMATCH'
    return 'ELIGIBLE_TIME_POSITION'


def eligible(quality,distance,accuracy,max_accuracy,ratio):
    return (quality=='ELIGIBLE_TIME_POSITION' and distance is not None and distance>0
            and accuracy is not None and accuracy<=max_accuracy and accuracy/distance<=ratio)


def movement(fixes,max_gap_s=10):
    groups=collections.defaultdict(list)
    for f in fixes:
        if valid_fix(f):groups[(str(f.get('boot_scope') or ''),f.get('provider'))].append(f)
    intervals=[];steps=[];speeds=[];excluded=0
    for rows in groups.values():
        rows.sort(key=lambda x:x['fix_elapsed_us'])
        for a,b in zip(rows,rows[1:]):
            delta=(b['fix_elapsed_us']-a['fix_elapsed_us'])/1e6
            if delta<=0:continue
            intervals.append(delta)
            if delta>max_gap_s:excluded+=1;continue
            distance=horizontal_distance(a['latitude'],a['longitude'],b['latitude'],b['longitude'])
            steps.append(distance);speeds.append(distance/delta)
    return intervals,steps,speeds,excluded


def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def write_csv(path,rows):
    with path.open('w',newline='') as f:
        if rows:
            keys=sorted(set().union(*(x.keys() for x in rows)))
            w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rows)


def main():
    p=argparse.ArgumentParser();p.add_argument('--config',type=Path,required=True)
    p.add_argument('--private-output',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();os.umask(0o077)
    if not a.private_output.resolve().is_relative_to(Path(__file__).resolve().parents[2]/'captures'):
        raise ValueError('Row-level position output must remain in ignored captures/')
    for d in [a.private_output,a.output]:d.mkdir(parents=True,exist_ok=True)
    config=json.loads(a.config.read_text());ident=json.loads(Path(config['identity_file']).read_text())['claimed_id']
    summary={'scope':'all preserved app DB rows, including preparation/test periods; target RID subset reported separately',
        'accuracy_is_os_report_not_true_error':True,'independent_stationary_truth':'NOT_EVALUABLE_no_ledger',
        'independent_position_error':'NOT_EVALUABLE_no_truth','three_dimensional_range':'NOT_EVALUABLE_vertical_consistency_unverified',
        'calendar_alignment':'candidate_only','nodes':{},'code_sha256':digest(Path(__file__))}
    sensitivity=[];private_rows=[];inputs=[];plot_samples={};timeline=[]
    for source in config['sources']:
        label=source['node'];path=Path(source['database']);before=digest(path);inputs.append(dict(source=label,path=str(path),sha256=before))
        refs={}
        for line in Path(source['reference_jsonl']).open():
            x=json.loads(line);r=x['reference']
            if r.get('reference_decode_ok') and bytes.fromhex(r.get('id_hex','')).rstrip(b'\0').decode(errors='replace')==ident:
                refs[x['capture']['odid_payload_hex']]=r
        db=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)
        if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('input integrity failed')
        fixes=[json.loads(raw) for (raw,) in db.execute('SELECT raw_json FROM receiver_fixes')]
        index=collections.defaultdict(list)
        for f in fixes:index[fix_key(f.get('boot_scope'),f)].append(f)
        providers=collections.Counter(str(f.get('provider')) for f in fixes);mocks=collections.Counter(str(f.get('mock')) for f in fixes)
        accuracies=[f['accuracy_m'] for f in fixes if valid_fix(f)]
        intervals,steps,speeds,gaps=movement(fixes)
        statuses=collections.Counter();target_statuses=collections.Counter();raw_statuses=collections.Counter();targets=[]
        time_rows=collections.defaultdict(list)
        for (raw,) in db.execute('SELECT raw_json FROM observations'):
            r=json.loads(raw);fix=r.get('receiver_position') or {};quality=association(r,index)
            statuses[quality]+=1;raw_statuses[str(fix.get('match_status') or 'POSITION_MISSING')]+=1
            boot=str(r.get('boot_scope') or '')
            if boot and not boot.startswith('unknown-') and isinstance(r.get('monotonic_time_us'),(int,float)):
                time_rows[boot].append((r['monotonic_time_us']/1e6,quality))
            reference=refs.get(r.get('odid_payload_hex'))
            if reference is None:continue
            target_statuses[quality]+=1;dist=None
            if quality=='ELIGIBLE_TIME_POSITION' and reference.get('location_valid'):
                dist=horizontal_distance(fix['latitude'],fix['longitude'],reference['claimed_latitude'],reference['claimed_longitude'])
            accuracy=fix.get('accuracy_m')
            item=dict(node=label,quality=quality,claimed_horizontal_distance_m=dist,accuracy_m=accuracy,
                fix_delta_s=abs(fix['fix_elapsed_us']-r['monotonic_time_us'])/1e6 if valid_fix(fix) and r.get('monotonic_time_us') is not None else None,
                received_at_utc=r.get('received_at_utc'),observed_us=r.get('monotonic_time_us'),
                boot_scope=r.get('boot_scope'),rssi_dbm=r.get('rssi_dbm'),
                receiver_latitude=fix.get('latitude'),receiver_longitude=fix.get('longitude'),
                claimed_latitude=reference.get('claimed_latitude'),claimed_longitude=reference.get('claimed_longitude'),
                phone_altitude_m=fix.get('altitude_ellipsoid_m'),drone_geo_altitude_m=reference.get('claimed_altitude_geo_m'),
                drone_height_m=reference.get('claimed_height_m'))
            targets.append(item);private_rows.append(item)
        total=sum(statuses.values());n=len(targets)
        for i,(boot,rows) in enumerate(sorted(time_rows.items()),1):
            start=min(t for t,q in rows);bins=collections.defaultdict(collections.Counter)
            for t,q in rows:bins[int((t-start)//300)][q]+=1
            for bucket,counts in sorted(bins.items()):
                count=sum(counts.values());good=counts.get('ELIGIBLE_TIME_POSITION',0)
                timeline.append(dict(node=label,anonymous_boot=f'G{i}',elapsed_bin_start_min=bucket*5,
                    rows=count,time_position_eligible_rows=good,eligible_fraction=good/count,
                    scope='all stored observations, no assertion of continuous capture'))
        for max_accuracy in [3,5,10,20]:
            for ratio in [.1,.25,.5,1.0]:
                kept=sum(eligible(x['quality'],x['claimed_horizontal_distance_m'],x['accuracy_m'],max_accuracy,ratio) for x in targets)
                sensitivity.append(dict(node=label,max_accuracy_m=max_accuracy,max_accuracy_over_claim_distance=ratio,
                    target_rows=n,retained_rows=kept,retained_fraction=kept/n if n else None,interpretation='exploratory horizontal claim-distance eligibility, not accuracy or TPR'))
        summary['nodes'][label]=dict(observation_rows=total,association_status_counts=dict(statuses),app_position_status_counts=dict(raw_statuses),
            target_rows=n,target_quality_counts=dict(target_statuses),
            standalone_fixes=len(fixes),valid_fix_rows=sum(valid_fix(f) for f in fixes),providers=dict(providers),mock_flags=dict(mocks),
            all_fix_os_accuracy_m=describe(accuracies),target_os_accuracy_m=describe([x['accuracy_m'] for x in targets if x['quality']=='ELIGIBLE_TIME_POSITION']),
            target_fix_delta_s=describe([x['fix_delta_s'] for x in targets if x['quality']=='ELIGIBLE_TIME_POSITION']),
            fix_update_interval_s=describe(intervals),apparent_step_m=describe(steps),apparent_speed_m_s=describe(speeds),
            speed_exceedance_counts={str(v):sum(x>v for x in speeds) for v in [2,5,10,20]},
            speed_exceedance_is_not_gps_error_proof=True,step_pairs_excluding_gaps_over_10s=len(speeds),
            excluded_long_gap_pairs=gaps,distance_target_scope='RID claim plus phone GPS, not independent true range',
            input_unchanged=before==digest(path))
        if not summary['nodes'][label]['input_unchanged']:raise ValueError('source changed during analysis')
        plot_samples[label]=dict(accuracy=[x['accuracy_m'] for x in targets if x['quality']=='ELIGIBLE_TIME_POSITION'],
                                 delta=[x['fix_delta_s'] for x in targets if x['quality']=='ELIGIBLE_TIME_POSITION'])
        db.close()
    (a.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    write_csv(a.output/'eligibility-sensitivity.csv',sensitivity)
    write_csv(a.output/'association-time-bins.csv',timeline)
    write_csv(a.private_output/'target-position-quality-private.csv',private_rows)
    (a.private_output/'inputs-private.json').write_text(json.dumps(inputs,indent=2)+'\n')
    # Row level distances, coordinates, times remain private. Public figures use anonymous counts only.
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.font_manager import FontProperties
    plt.rcParams.update({'font.family':FontProperties(fname='/System/Library/Fonts/ヒラギノ角ゴシック W7.ttc').get_name(),'axes.unicode_minus':False})
    labels=list(summary['nodes']);fig,axes=plt.subplots(1,2,figsize=(13,4.8))
    for ax,target in zip(axes,[False,True]):
        good=[];held=[]
        for label in labels:
            s=summary['nodes'][label];states=s['target_quality_counts'] if target else s['association_status_counts']
            n=s['target_rows'] if target else s['observation_rows'];g=states.get('ELIGIBLE_TIME_POSITION',0)
            good.append(g/n*100 if n else 0);held.append((n-g)/n*100 if n else 0)
        ax.bar(labels,good,label='時刻・自己位置の照合条件を通過',color='#1768aa')
        ax.bar(labels,held,bottom=good,label='保留・対象外',color='#c7cbd0')
        for i,label in enumerate(labels):
            n=summary['nodes'][label]['target_rows' if target else 'observation_rows'];ax.text(i,102,f'n={n}' if n else '対象なし',ha='center')
        ax.set(ylim=(0,112),ylabel='各保存行を分母とする割合 [%]',title='対象実機IDの観測だけ' if target else '全保存観測：実験外の記録も含む')
    axes[0].legend(loc='lower left');fig.tight_layout();fig.savefig(a.output/'01_position_association.png',dpi=170);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(12,4.5))
    for label,values in plot_samples.items():
        for ax,key in zip(axes,['accuracy','delta']):
            vals=sorted(values[key])
            if vals:ax.step(vals,[(i+1)/len(vals) for i in range(len(vals))],where='post',label=f'{label} n={len(vals)}')
    axes[0].set(xlabel='OSが申告した水平精度 [m]',ylabel='累積割合',title='実際の測位誤差を測った値ではない')
    axes[1].set(xlabel='観測と測位の時刻差の絶対値 [秒]',ylabel='累積割合',title='対象RIDと自己位置の同端末内時刻対応')
    for ax in axes:ax.grid(alpha=.2);ax.legend()
    fig.tight_layout();fig.savefig(a.output/'02_target_accuracy_and_time.png',dpi=170);plt.close(fig)
    fig,ax=plt.subplots(figsize=(10,5))
    for j,label in enumerate(labels):
        rows=[x for x in sensitivity if x['node']==label and x['max_accuracy_over_claim_distance']==.25]
        if not summary['nodes'][label]['target_rows']:continue
        ax.plot([x['max_accuracy_m'] for x in rows],[x['retained_fraction']*100 for x in rows],'o-',label=f"{label} n={rows[0]['target_rows']}")
    ax.set(xlabel='許容するOS水平精度の上限 [m]',ylabel='対象RID保存行のうち条件を通過 [%]',
        title='探索的な採用条件：accuracy／申告水平距離 <= 0.25\n真位置精度や検出率を示すグラフではない',xticks=[3,5,10,20],ylim=(0,105))
    zeros=[f"{label}: 0/{summary['nodes'][label]['target_rows']}" for label in labels
           if summary['nodes'][label]['target_rows'] and all(x['retained_rows']==0 for x in sensitivity
               if x['node']==label and x['max_accuracy_over_claim_distance']==.25)]
    if zeros:ax.text(.03,.15,'全閾値で保留：'+'、'.join(zeros),transform=ax.transAxes)
    ax.legend();ax.grid(alpha=.2);fig.tight_layout();fig.savefig(a.output/'03_eligibility_sensitivity.png',dpi=170);plt.close(fig)
    fig,axes=plt.subplots(len(labels),1,figsize=(11,8),squeeze=False)
    for ax,label in zip(axes[:,0],labels):
        rows=[x for x in timeline if x['node']==label]
        for boot in sorted({x['anonymous_boot'] for x in rows}):
            subset=[x for x in rows if x['anonymous_boot']==boot]
            ax.scatter([x['elapsed_bin_start_min'] for x in subset],[x['eligible_fraction']*100 for x in subset],s=18,label=boot)
        ax.set(title=label,xlabel='起動区分内の最初の観測から [分]：5分窓',ylabel='照合条件通過 [%]',ylim=(-5,105));ax.grid(alpha=.2)
        if rows:ax.legend()
    fig.suptitle('全保存観測の自己位置対応：過去の試験も含む／記録のない窓は描画しない')
    fig.tight_layout();fig.savefig(a.output/'04_association_over_time.png',dpi=170);plt.close(fig)
    print(json.dumps({k:dict(target_rows=v['target_rows'],target_quality=v['target_quality_counts'],fix_rows=v['standalone_fixes']) for k,v in summary['nodes'].items()},indent=2))


if __name__=='__main__':main()
