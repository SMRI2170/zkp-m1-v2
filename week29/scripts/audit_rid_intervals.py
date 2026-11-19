#!/usr/bin/env python3
"""Issue92: saved rows, repeated cache observations and changing RID contents are distinct."""
import argparse
import collections
import hashlib
import json
import math
import os
from pathlib import Path

from audit_field_time import clock_partitions,epoch,sha
from analyze_b_snapshot import percentile
from audit_android_position import write_csv


def stats(values):
    if not values:return {'n':0}
    return dict(n=len(values),min=min(values),median=percentile(values,.5),p95=percentile(values,.95),max=max(values))


def time_status(row):
    mono=row.get('monotonic_time_us')
    if epoch(row.get('received_at_utc')) is None:return 'UTC_UNKNOWN'
    if isinstance(mono,bool) or not isinstance(mono,(int,float)) or not math.isfinite(mono) or mono<=0:
        return 'MONOTONIC_UNKNOWN'
    return 'ELIGIBLE_TIME'


def analyze_group(rows):
    ordered=sorted(rows,key=lambda x:x['mono'])
    seen=set();unique=[]
    for x in ordered:
        key=(x['bssid'],x['frequency'],x['mono'],x['digest'],x['payload'])
        if key not in seen:seen.add(key);unique.append(x)
    intervals=[];changes=[];repeats=0
    bysource=collections.defaultdict(list)
    for x in unique:bysource[(x['bssid'],x['frequency'])].append(x)
    for records in bysource.values():
        previous_change=None
        for i,x in enumerate(records):
            if i and x['mono']>records[i-1]['mono']:intervals.append(x['mono']-records[i-1]['mono'])
            if not i or x['payload']!=records[i-1]['payload']:
                if previous_change is not None and x['mono']>previous_change:changes.append(x['mono']-previous_change)
                previous_change=x['mono']
            else:repeats+=1
    return dict(rows=len(rows),retained_observation_keys=len(unique),repeated_observation_keys=len(rows)-len(unique),
        distinct_pack_contents=len({x['payload'] for x in unique}),consecutive_same_pack_rows=repeats,
        content_change_events=len(unique)-repeats,
        within_group_span_s=ordered[-1]['mono']-ordered[0]['mono'] if ordered else None,
        cache_update_intervals_s=stats(intervals),pack_change_intervals_s=stats(changes),
        cache_update_intervals_at_most_60s=stats([x for x in intervals if x<=60]),
        cache_gaps_over_60s=sum(x>60 for x in intervals)),unique,intervals,changes


def main():
    p=argparse.ArgumentParser();p.add_argument('--config',type=Path,required=True)
    p.add_argument('--private-output',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();os.umask(0o077)
    if not a.private_output.resolve().is_relative_to(Path(__file__).resolve().parents[2]/'captures'):raise ValueError('Private inputs/records stay in captures/')
    for d in [a.private_output,a.output]:d.mkdir(parents=True,exist_ok=True)
    cfg=json.loads(a.config.read_text());ident=json.loads(Path(cfg['identity_file']).read_text())['claimed_id']
    summary=dict(nodes={},comparison_scope='descriptive only; placement, settings and capture windows not controlled',
        physical_packet_count_known=False,transmission_denominator_known=False,packet_delivery_rate='NOT_EVALUABLE',
        code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    aggregate=[];bins=[];private=[];plot_intervals={};inputs=[]
    for src in cfg['sources']:
        node=src['node'];selected=[];unknown=0;stale=0;fresh_unknown=0;holds=collections.Counter()
        path=Path(src['reference_jsonl']);before=sha(path)
        for line in path.open():
            x=json.loads(line);d=x['reference'];r=x['capture']
            if not (d.get('reference_decode_ok') and bytes.fromhex(d.get('id_hex','')).rstrip(b'\0').decode(errors='replace')==ident):continue
            t=epoch(r.get('received_at_utc'));m=r.get('monotonic_time_us')
            stale+=r.get('cache_stale') is True;fresh_unknown+=r.get('cache_stale') is None
            status=time_status(r)
            if status!='ELIGIBLE_TIME':unknown+=1;holds[status]+=1;continue
            selected.append(dict(node=node,utc=t,mono=m/1e6,boot=str(r.get('boot_scope') or ''),key=str(len(selected)),
                bssid=r.get('bssid'),frequency=r.get('frequency_mhz'),digest=r.get('vendor_content_digest'),
                payload=r.get('odid_payload_hex'),rssi=r.get('rssi_dbm')))
        groups=[];all_intervals=[];all_changes=[];group_index=0
        for label,boot,origin,rows in clock_partitions(selected):
            group_index+=1;label=f'G{group_index}'
            values,unique,intervals,changes=analyze_group(rows);groups.append(dict(clock_group=label,**values))
            all_intervals.extend(intervals);all_changes.extend(changes)
            start=min(x['mono'] for x in unique);bybin=collections.Counter(int((x['mono']-start)//60) for x in unique)
            for index,count in sorted(bybin.items()):bins.append(dict(node=node,clock_group=label,elapsed_min=index,observation_keys=count))
            private.extend(dict(x,clock_group=label) for x in unique)
        unchanged=before==sha(path)
        if not unchanged:raise ValueError('Input changed during interval audit')
        inputs.append(dict(node=node,path=str(path),sha256=before))
        summary['nodes'][node]=dict(valid_time_rows=len(selected),unknown_time_rows=unknown,time_hold_reasons=dict(holds),input_unchanged=unchanged,cache_stale_rows=stale,
            freshness_unknown_rows=fresh_unknown,clock_groups=groups,
            saved_rows=len(selected)+unknown,observation_keys=sum(x['retained_observation_keys'] for x in groups),
            repeated_observation_keys=sum(x['repeated_observation_keys'] for x in groups),
            distinct_pack_contents=len({x['payload'] for x in selected}),
            consecutive_same_pack_rows=sum(x['consecutive_same_pack_rows'] for x in groups),
            content_change_events=sum(x['content_change_events'] for x in groups),
            cache_update_intervals_s=stats(all_intervals),pack_change_intervals_s=stats(all_changes))
        plot_intervals[node]=(all_intervals,all_changes)
        for kind,values in [('cache_observation',all_intervals),('pack_content_change',all_changes)]:
            aggregate.extend(dict(node=node,kind=kind,interval_s=x,within_60s=x<=60) for x in values)
    (a.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    write_csv(a.private_output/'update-intervals.csv',aggregate);write_csv(a.output/'observation-time-bins.csv',bins)
    (a.private_output/'observations-private.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in private))
    (a.private_output/'inputs-private.json').write_text(json.dumps(inputs,indent=2)+'\n')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.font_manager import FontProperties
    plt.rcParams.update({'font.family':FontProperties(fname='/System/Library/Fonts/ヒラギノ角ゴシック W7.ttc').get_name(),'axes.unicode_minus':False})
    fig,axes=plt.subplots(1,2,figsize=(12,4.8))
    for node,(intervals,changes) in plot_intervals.items():
        for ax,data in zip(axes,[intervals,changes]):
            if not data:continue
            values=sorted(data);ax.step(values,[(i+1)/len(values) for i in range(len(values))],where='post',label=f'{node} n={len(values)}')
    for ax,title in zip(axes,['同じ時計群・送信元の観測更新','Pack内容が直前から変わった更新']):
        ax.set(xlabel='正の更新間隔 [秒]：対数軸',ylabel='累積割合',title=title,xscale='log');ax.grid(alpha=.2);ax.legend()
    fig.suptitle('実機RIDの更新間隔：機種性能の統制比較ではない／長い記録空白も含む')
    fig.tight_layout();fig.savefig(a.output/'01_update_interval_ecdf.png',dpi=170);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(12,4.5))
    nodes=list(summary['nodes']);xs=list(range(len(nodes)))
    for delta,key,label in [(-.25,'saved_rows','保存行'),(0,'observation_keys','観測時刻・内容キー'),(.25,'distinct_pack_contents','Pack内容種類')]:
        axes[0].bar([x+delta for x in xs],[summary['nodes'][k][key] for k in nodes],width=.25,label=label)
    axes[0].set(xticks=xs,xticklabels=nodes,ylabel='件数：独立パケット数ではない');axes[0].legend()
    for node,(intervals,changes) in plot_intervals.items():
        values=[x for x in intervals if x<=60]
        if values:axes[1].hist(values,bins=[0,1,2,5,10,20,30,60],histtype='step',label=f'{node} n={len(values)}')
    axes[1].set(xlabel='観測更新間隔 [秒]：60秒以下だけを別集計',ylabel='間隔の個数');axes[1].legend()
    fig.tight_layout();fig.savefig(a.output/'02_saved_rows_and_histogram.png',dpi=170);plt.close(fig)
    fig,axes=plt.subplots(len(nodes),1,figsize=(11,8),squeeze=False)
    for ax,node in zip(axes[:,0],nodes):
        rows=[x for x in bins if x['node']==node]
        for group in sorted({x['clock_group'] for x in rows}):
            r=[x for x in rows if x['clock_group']==group]
            ax.bar([x['elapsed_min'] for x in r],[x['observation_keys'] for x in r],width=.85,label=group)
        ax.set(title=node,xlabel='時計群内の最初の対象観測から [分]',ylabel='1分窓の観測キー数');ax.grid(alpha=.2)
        if rows:ax.legend()
    fig.suptitle('記録された観測の時間推移：記録なしを受信不能・電源断とは断定しない')
    fig.tight_layout();fig.savefig(a.output/'03_observation_timeline.png',dpi=170);plt.close(fig)
    print(json.dumps(summary['nodes'],indent=2))


if __name__=='__main__':main()
