#!/usr/bin/env python3
"""Issue94: descriptive RSSI versus claimed horizontal distance, with explicit position gates."""
import argparse
import collections
import csv
import json
import math
import os
from pathlib import Path

from audit_android_position import eligible,write_csv
from audit_field_time import sha
from analyze_b_snapshot import percentile


def number(value):
    try:value=float(value)
    except (TypeError,ValueError):return None
    return value if math.isfinite(value) else None


def retained(row,max_accuracy=20,ratio=.25):
    return (eligible(row['quality'],number(row.get('claimed_horizontal_distance_m')),
            number(row.get('accuracy_m')),max_accuracy,ratio) and number(row.get('rssi_dbm')) is not None)


def summarize(rows):
    values=[number(x['rssi_dbm']) for x in rows];values=[x for x in values if x is not None]
    if not values:return dict(n=0)
    return dict(n=len(values),rssi_median_dbm=percentile(values,.5),rssi_p10_dbm=percentile(values,.1),
                rssi_p90_dbm=percentile(values,.9),rssi_min_dbm=min(values),rssi_max_dbm=max(values))


def main():
    p=argparse.ArgumentParser();p.add_argument('--positions',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--selection-manifest',type=Path)
    a=p.parse_args();os.umask(0o077);a.output.mkdir(parents=True,exist_ok=True)
    before=sha(a.positions)
    with a.positions.open() as f:rows=list(csv.DictReader(f))
    nodes=sorted({x['node'] for x in rows});selected=[x for x in rows if retained(x)]
    if a.selection_manifest:
        from build_quality_manifest import load_selection
        selected=load_selection(a.selection_manifest,a.positions,rows)
    summary=dict(source_sha256=before,code_sha256=sha(Path(__file__)),nodes={},
        quality_gate=dict(max_os_accuracy_m=20,max_accuracy_over_claimed_horizontal_distance=.25),
        distance='RID claim and associated phone GPS horizontal distance; not independent true distance',
        slant_distance='NOT_EVALUABLE_vertical_reference_unverified',
        fitted_path_loss_model='NOT_EXECUTED_independent_runs_and_power_controls_not_established',
        generalization_accuracy='NOT_EVALUABLE',b_distance='NOT_EVALUABLE_receiver_position_unknown')
    bins=[];heights=[]
    for node in nodes:
        allnode=[x for x in rows if x['node']==node];good=[x for x in selected if x['node']==node]
        summary['nodes'][node]=dict(target_rows=len(allnode),retained_rows=len(good),held_rows=len(allnode)-len(good),**summarize(good))
        for low,high in [(0,10),(10,20),(20,30),(30,50),(50,100),(100,200),(200,float('inf'))]:
            bucket=[x for x in good if low<=number(x['claimed_horizontal_distance_m'])<high]
            bins.append(dict(node=node,distance_low_m=low,distance_high_m=high if math.isfinite(high) else 'unbounded',**summarize(bucket)))
        for low,high in [(-1000,0),(0,10),(10,20),(20,40),(40,100),(100,10000)]:
            bucket=[x for x in good if number(x.get('drone_height_m')) is not None and low<=number(x['drone_height_m'])<high]
            heights.append(dict(node=node,height_low_m=low,height_high_m=high,**summarize(bucket)))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.font_manager import FontProperties
    plt.rcParams.update({'font.family':FontProperties(fname='/System/Library/Fonts/ヒラギノ角ゴシック W7.ttc').get_name(),'axes.unicode_minus':False})
    fig,axes=plt.subplots(1,2,figsize=(12,4.8))
    for node in nodes:
        good=[x for x in selected if x['node']==node]
        if not good:continue
        axes[0].scatter([number(x['claimed_horizontal_distance_m']) for x in good],[number(x['rssi_dbm']) for x in good],s=19,alpha=.7,label=f'{node} n={len(good)}')
        subsets=[x for x in bins if x['node']==node and x['n'] and isinstance(x['distance_high_m'],(int,float))]
        center=[(x['distance_low_m']+x['distance_high_m'])/2 for x in subsets]
        med=[x['rssi_median_dbm'] for x in subsets]
        axes[1].errorbar(center,med,yerr=[[v-x['rssi_p10_dbm'] for v,x in zip(med,subsets)],
                                       [x['rssi_p90_dbm']-v for v,x in zip(med,subsets)]],fmt='o',capsize=4,label=node)
        for c,x in zip(center,subsets):axes[1].annotate(f"n={x['n']}",(c,x['rssi_p90_dbm']),xytext=(0,7),textcoords='offset points',ha='center')
    for ax in axes:ax.set(xlabel='RID申告＋スマホGPSからの水平距離 [m]',ylabel='実測RSSI [dBm]');ax.grid(alpha=.2);ax.legend()
    axes[0].set_title('品質条件を通過した記録だけ');axes[1].set_title('距離帯別の中央値・10〜90分位：信頼区間ではない')
    fig.suptitle('申告距離とRSSIの記述統計：実際の距離推定精度・攻撃検出性能ではない')
    fig.tight_layout();fig.savefig(a.output/'01_claim_distance_rssi.png',dpi=170);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(12,4.8))
    for node in nodes:
        good=[x for x in selected if x['node']==node]
        if not good:continue
        heights_good=[x for x in good if number(x.get('drone_height_m')) is not None]
        axes[0].scatter([number(x['drone_height_m']) for x in heights_good],[number(x['rssi_dbm']) for x in heights_good],s=19,alpha=.7,label=f'{node} n={len(heights_good)}')
        byboot=collections.defaultdict(list)
        for x in good:byboot[x['boot_scope']].append(x)
        for values in byboot.values():
            start=min(number(x['observed_us']) for x in values)
            axes[1].scatter([(number(x['observed_us'])-start)/60e6 for x in values],[number(x['rssi_dbm']) for x in values],s=16,label=node)
    axes[0].set(xlabel='RID申告Height [m]：独立の高度真値ではない',ylabel='実測RSSI [dBm]',title='Heightは水平距離と別の因子として表示')
    axes[1].set(xlabel='採用記録の時計群内の最初から [分]',ylabel='実測RSSI [dBm]',title='時間変動：各点を独立な反復試験としない')
    for ax in axes:ax.grid(alpha=.2);ax.legend()
    fig.tight_layout();fig.savefig(a.output/'02_height_and_time.png',dpi=170);plt.close(fig)
    write_csv(a.output/'distance-bins.csv',bins);write_csv(a.output/'height-bins.csv',heights)
    summary['input_unchanged']=before==sha(a.positions)
    if not summary['input_unchanged']:raise ValueError('Input changed')
    (a.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
