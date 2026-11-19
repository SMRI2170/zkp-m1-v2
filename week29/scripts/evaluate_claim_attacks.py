#!/usr/bin/env python3
"""Issue96: paired synthetic changes to real RSSI, conditional horizontal-model proxy only."""
import argparse
import collections
import csv
import json
import math
import os
import statistics
from pathlib import Path

from analyze_claim_distance_rssi import retained
from analyze_b_snapshot import percentile
from audit_android_position import write_csv
from audit_field_time import sha


def split_time(rows,embargo_s=10):
    ordered=sorted(rows,key=lambda x:x['time'])
    if len({x['boot'] for x in ordered})!=1:raise ValueError('Use a single explicitly selected boot, never merge clocks')
    n=len(ordered);train=ordered[:n//2];cal=ordered[n//2:n*3//4];test=ordered[n*3//4:]
    if not train or not cal or not test:raise ValueError('Insufficient temporal partitions')
    cal=[x for x in cal if x['time']-train[-1]['time']>embargo_s]
    # Purge relative to the original calibration boundary, including excluded cal rows.
    boundary=ordered[n*3//4-1]['time']
    test=[x for x in test if x['time']-boundary>embargo_s]
    return train,cal,test


def fit(rows):
    xs=[math.log10(x['distance']) for x in rows];ys=[x['rssi'] for x in rows]
    mx,my=statistics.mean(xs),statistics.mean(ys);var=sum((x-mx)**2 for x in xs)
    if var<=1e-12:raise ValueError('Training distances have no spread')
    slope=sum((x-mx)*(y-my) for x,y in zip(xs,ys))/var
    if slope>=0:raise ValueError('Nondecreasing fitted RSSI: no decreasing-distance proxy adopted')
    return my-slope*mx,-slope/10


def prediction(distance,intercept,n):
    if distance<=0 or n<=0:raise ValueError('Positive distance and exponent required')
    return intercept-10*n*math.log10(distance)


def changed_distance(distance,delta,direction):
    if direction=='away':return distance+delta
    if direction=='toward':return distance-delta if distance>delta else None
    if direction=='transverse':return math.hypot(distance,delta)
    raise ValueError('Unknown direction')


def compensation(before,after,n,cap=None):
    value=-10*n*math.log10(after/before)
    return max(-cap,min(cap,value)) if cap is not None else value


def main():
    p=argparse.ArgumentParser();p.add_argument('--positions',type=Path,required=True)
    p.add_argument('--selection-manifest',type=Path)
    p.add_argument('--node',default='Pixel');p.add_argument('--private-output',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();os.umask(0o077)
    if not a.private_output.resolve().is_relative_to(Path(__file__).resolve().parents[2]/'captures'):raise ValueError('Paired records stay in captures/')
    for d in [a.private_output,a.output]:d.mkdir(parents=True,exist_ok=True)
    before=sha(a.positions)
    with a.positions.open() as f:allrows=list(csv.DictReader(f))
    selected=[x for x in allrows if retained(x)]
    if a.selection_manifest:
        from build_quality_manifest import load_selection
        selected=load_selection(a.selection_manifest,a.positions,allrows)
    rows=[dict(distance=float(x['claimed_horizontal_distance_m']),rssi=float(x['rssi_dbm']),
               time=float(x['observed_us'])/1e6,boot=x['boot_scope']) for x in selected if x['node']==a.node]
    summary=dict(node=a.node,source_sha256=before,code_sha256=sha(Path(__file__)),
        measurement='real receiver RSSI and RID claim plus phone-GPS horizontal distance',
        baseline_assumption='unmodified RID claims treated as correct, not independent position truth',
        result_scope='conditional synthetic model-consistency proxy, not measured real spoof-detection performance',
        power_changes='post-processing RSSI addition, not RF power-control experiments',
        split='ordered 50/25/25 percent by records, 10-second temporal embargo, no random interleaving',
        independent_runs_known=False,bootstrap_ci='NOT_EVALUABLE_independent_runs_not_established',
        high_altitude_attack='NOT_EVALUABLE_vertical_consistency_unverified',
        multistation_cancellation='NOT_EVALUABLE_same_transmission_unverified',held_other_nodes='position quality or target data insufficient')
    try:
        train,cal,test=split_time(rows)
        summary['counts']=dict(quality_eligible=len(rows),train=len(train),calibration=len(cal),evaluation=len(test),purged=len(rows)-len(train)-len(cal)-len(test))
        if min(len(train),len(cal),len(test))<20:raise ValueError('Each temporal partition requires at least 20 records')
        intercept,n=fit(train)
    except ValueError as e:
        summary.update(status='NOT_EVALUABLE',reason=str(e))
        (a.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');return
    threshold=percentile([abs(x['rssi']-prediction(x['distance'],intercept,n)) for x in cal],.95)
    summary.update(status='EXECUTED_CONDITIONAL_PROXY',model_intercept_dbm=intercept,horizontal_proxy_n=n,threshold_db=threshold,
        calibration_quantile=.95,normal_assumed_alarm_rate=sum(abs(x['rssi']-prediction(x['distance'],intercept,n))>threshold for x in test)/len(test))
    summary['detector_adoption']='NOT_SUPPORTED_no_independent_runs_and_baseline_false_alarms_uncontrolled'
    summary['training_claimed_distance_range_m']=[min(x['distance'] for x in train),max(x['distance'] for x in train)]
    modes=['claim_only','constant_plus6','constant_minus6','time_varying6','model_matched_unbounded','n2_cap1','n2_cap3','n2_cap6','n2_cap10']
    results=[];private=[];blocks=[]
    start=test[0]['time']
    for direction in ['away','toward','transverse']:
        for delta in [20,50,100]:
            for mode in modes:
                paired=[]
                for i,x in enumerate(test):
                    new=changed_distance(x['distance'],delta,direction)
                    if new is None:continue
                    power=0
                    if mode=='constant_plus6':power=6
                    elif mode=='constant_minus6':power=-6
                    elif mode=='time_varying6':power=6*math.sin(2*math.pi*(x['time']-start)/60)
                    elif mode=='model_matched_unbounded':power=compensation(x['distance'],new,n)
                    elif mode.startswith('n2_cap'):power=compensation(x['distance'],new,2,int(mode.split('cap')[1]))
                    base=abs(x['rssi']-prediction(x['distance'],intercept,n))
                    score=abs(x['rssi']+power-prediction(new,intercept,n))
                    paired.append(dict(index=i,time_block=int((x['time']-start)//30),base_score_db=base,attack_score_db=score,
                        original_distance_m=x['distance'],modified_distance_m=new,power_added_db=power,
                        outside_training_distance=not summary['training_claimed_distance_range_m'][0]<=new<=summary['training_claimed_distance_range_m'][1],
                        baseline_alarm=base>threshold,attack_alarm=score>threshold))
                den=len(paired)
                byblock=collections.defaultdict(list)
                for x in paired:byblock[x['time_block']].append(x)
                result=dict(direction=direction,displacement_m=delta,power_mode=mode,total_evaluation_rows=len(test),
                    evaluated_rows=den,held_rows=len(test)-den,held_fraction=(len(test)-den)/len(test),
                    fpr_proxy_on_paired_baseline=sum(x['baseline_alarm'] for x in paired)/den if den else None,
                    tpr_proxy_on_synthetic_attack=sum(x['attack_alarm'] for x in paired)/den if den else None,
                    modified_distance_extrapolation_fraction=sum(x['outside_training_distance'] for x in paired)/den if den else None,
                    time_blocks_30s=len(byblock),independent_runs_established=False)
                results.append(result)
                for block,values in byblock.items():blocks.append(dict(direction=direction,displacement_m=delta,power_mode=mode,block=block,
                    n=len(values),baseline_alarm_fraction=sum(x['baseline_alarm'] for x in values)/len(values),attack_alarm_fraction=sum(x['attack_alarm'] for x in values)/len(values)))
                private.extend(dict(direction=direction,displacement_m=delta,power_mode=mode,**x) for x in paired)
    write_csv(a.output/'attack-summary.csv',results);write_csv(a.output/'time-block-rates.csv',blocks)
    write_csv(a.private_output/'paired-scores-private.csv',private)
    (a.private_output/'model-splits-private.json').write_text(json.dumps(dict(source=str(a.positions),sha256=before,train=train,calibration=cal,evaluation=test),indent=2)+'\n')
    summary['input_unchanged']=before==sha(a.positions)
    if not summary['input_unchanged']:raise ValueError('Input changed')
    (a.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.font_manager import FontProperties
    plt.rcParams.update({'font.family':FontProperties(fname='/System/Library/Fonts/ヒラギノ角ゴシック W7.ttc').get_name(),'axes.unicode_minus':False})
    fig,axes=plt.subplots(1,3,figsize=(15,4.5),sharey=True)
    labels={'away':'受信局から遠ざける','toward':'受信局へ近づける：局を越える移動は保留','transverse':'受信局への方向と直交させる'}
    for ax,direction in zip(axes,labels):
        for mode,label,style,marker in [('claim_only','申告変更のみ','-','o'),('constant_plus6','RSSI +6dB','--','s'),('constant_minus6','RSSI −6dB',':','^'),('model_matched_unbounded','同じモデルによる理想補償','-.','x')]:
            rs=[x for x in results if x['direction']==direction and x['power_mode']==mode and x['evaluated_rows']]
            ax.plot([x['displacement_m'] for x in rs],[100*x['tpr_proxy_on_synthetic_attack'] for x in rs],linestyle=style,marker=marker,label=label)
        ax.axhline(summary['normal_assumed_alarm_rate']*100,color='gray',ls='--',label='未改変の警報割合（全評価行）')
        ax.set(xlabel='合成位置変更の変位 [m]',title=labels[direction],xticks=[20,50,100],ylim=(-3,103));ax.grid(alpha=.2)
        if not any(x['evaluated_rows'] for x in results if x['direction']==direction):ax.text(.5,.3,'全条件で保留\n警報率0%という意味ではない',transform=ax.transAxes,ha='center')
    axes[0].set_ylabel('条件付きの合成攻撃警報割合 [%]');axes[-1].legend(fontsize=8,loc='best')
    fig.suptitle(f"実測RSSI＋合成変更：未改変でも {summary['normal_assumed_alarm_rate']*100:.1f}% 警報／検出器の採用根拠にはできない")
    fig.tight_layout();fig.savefig(a.output/'01_synthetic_attack_rates.png',dpi=170);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(12,4.5))
    for mode,label in [('claim_only','申告変更のみ'),('model_matched_unbounded','同じモデルによる理想補償')]:
        records=[x for x in private if x['direction']=='away' and x['displacement_m']==50 and x['power_mode']==mode]
        values=sorted(x['attack_score_db'] for x in records)
        if values:axes[0].step(values,[(i+1)/len(values) for i in range(len(values))],where='post',label=label)
    base=sorted(abs(x['rssi']-prediction(x['distance'],intercept,n)) for x in test)
    axes[0].step(base,[(i+1)/len(base) for i in range(len(base))],where='post',ls='--',label='未改変・申告を真と仮定')
    axes[0].axvline(threshold,color='gray',ls=':');axes[0].set(xlabel='絶対残差 [dB]',ylabel='累積割合',title='50m遠方偽装：同じ元観測による対比較');axes[0].legend(fontsize=8)
    for direction in ['away','transverse']:
        rs=[x for x in results if x['direction']==direction and x['displacement_m']==50 and x['power_mode'].startswith('n2_cap')]
        axes[1].plot([int(x['power_mode'].split('cap')[1]) for x in rs],[100*x['tpr_proxy_on_synthetic_attack'] for x in rs],'o-',label=labels[direction])
    axes[1].set(xlabel='攻撃者n=2の場合の合成補償上限 [±dB]',ylabel='合成攻撃警報割合 [%]',title='50m申告変更：RF受信欠落は再現していない',xticks=[1,3,6,10],ylim=(-3,103));axes[1].legend(fontsize=8)
    for ax in axes:ax.grid(alpha=.2)
    fig.tight_layout();fig.savefig(a.output/'02_scores_and_power_caps.png',dpi=170);plt.close(fig)
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
