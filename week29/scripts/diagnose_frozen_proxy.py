#!/usr/bin/env python3
"""Explain a frozen proxy's failure; never tune on evaluation or report true FPR."""
import collections,json,math,statistics
from evaluate_claim_attacks import split_time,fit,prediction,changed_distance,compensation
from analyze_b_snapshot import percentile
from build_quality_manifest import reasons,number


def transitions(pairs,threshold):
    count=collections.Counter((b>threshold,a>threshold) for b,a in pairs)
    return dict(n=len(pairs),quiet_to_quiet=count[(False,False)],quiet_to_alarm=count[(False,True)],
        alarm_to_quiet=count[(True,False)],alarm_to_alarm=count[(True,True)])


def merge_small_blocks(records,min_n=5):
    """Consecutive descriptive groups, not independent runs or IID resamples."""
    if not records:return []
    buckets=collections.defaultdict(list);start=records[0]['time']
    for r in records:buckets[int((r['time']-start)//30)].append(r)
    groups=[];pending=[]
    for key in sorted(buckets):
        pending.extend(buckets[key])
        if len(pending)>=min_n:groups.append(pending);pending=[]
    if pending:
        if groups:groups[-1].extend(pending)
        else:return []
    return groups


def selection_sensitivity(rows,deltas=(20,50,100)):
    output=[]
    for node in sorted({r['node'] for r in rows}):
        group=[r for r in rows if r['node']==node]
        for delta in deltas:
            changed=[]
            for r in group:
                d=number(r.get('claimed_horizontal_distance_m'))
                baseline=not reasons(r)
                alternate={**r,'claimed_horizontal_distance_m':str(d+delta)} if d is not None and d>0 else r
                changed.append((baseline,not reasons(alternate)))
            output.append(dict(node=node,synthetic_away_shift_m=delta,total_rows=len(group),baseline_selected=sum(a for a,b in changed),
                after_claim_change_selected=sum(b for a,b in changed),newly_admitted=sum(not a and b for a,b in changed),
                newly_held=sum(a and not b for a,b in changed),scope='quality-gate sensitivity only; frozen model selection unchanged'))
    return output


def diagnose(selected,all_rows,baseline_summary,private_output):
    data=[dict(distance=float(r['claimed_horizontal_distance_m']),rssi=float(r['rssi_dbm']),time=float(r['observed_us'])/1e6,boot=r['boot_scope']) for r in selected if r['node']=='Pixel']
    train,cal,test=split_time(data);a,n=fit(train)
    threshold=percentile([abs(r['rssi']-prediction(r['distance'],a,n)) for r in cal],.95)
    if [len(train),len(cal),len(test)]!=[baseline_summary['counts'][k] for k in ('train','calibration','evaluation')]:raise ValueError('Frozen split differs')
    for key,value in [('model_intercept_dbm',a),('horizontal_proxy_n',n),('threshold_db',threshold)]:
        if not math.isclose(value,baseline_summary[key],rel_tol=1e-12,abs_tol=1e-12):raise ValueError('Frozen model or threshold differs')
    low,high=min(r['distance'] for r in train),max(r['distance'] for r in train)
    parts=[];private_rows=[]
    for name,rows in [('train',train),('calibration',cal),('evaluation',test)]:
        signed=[r['rssi']-prediction(r['distance'],a,n) for r in rows];scores=list(map(abs,signed))
        parts.append(dict(partition=name,n=len(rows),alarm_count=sum(s>threshold for s in scores),alarm_fraction=sum(s>threshold for s in scores)/len(rows),
            signed_residual_median_db=statistics.median(signed),signed_residual_q25_db=percentile(signed,.25),signed_residual_q75_db=percentile(signed,.75),
            absolute_residual_median_db=statistics.median(scores),outside_training_distance_count=sum(not low<=r['distance']<=high for r in rows)))
        private_rows.extend(dict(partition=name,ordinal=i,**r,predicted_rssi_dbm=prediction(r['distance'],a,n),signed_residual_db=s,score_db=abs(s)) for i,(r,s) in enumerate(zip(rows,signed)))
    baseline_alarms=sum(abs(r['rssi']-prediction(r['distance'],a,n))>threshold for r in test)
    if not math.isclose(baseline_alarms/len(test),baseline_summary['normal_assumed_alarm_rate'],abs_tol=1e-12):raise ValueError('Baseline alarms differ from frozen evaluation')
    modes=('claim_only','constant_plus6','constant_minus6','time_varying6','model_matched_unbounded','n2_cap1','n2_cap3','n2_cap6','n2_cap10')
    attack_summary=[];events=[]
    for direction in ('away','toward','transverse'):
        for delta in (20,50,100):
            for mode in modes:
                pairs=[];outside=0;max_error=0
                for i,r in enumerate(test):
                    d=changed_distance(r['distance'],delta,direction)
                    if d is None:
                        events.append(dict(ordinal=i,direction=direction,shift_m=delta,mode=mode,status='HELD_claim_crosses_receiver',threshold_db=threshold));continue
                    dp=0
                    if mode=='constant_plus6':dp=6
                    elif mode=='constant_minus6':dp=-6
                    elif mode=='time_varying6':dp=6*math.sin(2*math.pi*(r['time']-test[0]['time'])/60)
                    elif mode=='model_matched_unbounded':dp=compensation(r['distance'],d,n)
                    elif mode.startswith('n2_cap'):dp=compensation(r['distance'],d,2,int(mode.split('cap')[1]))
                    residual=r['rssi']-prediction(r['distance'],a,n);changed=r['rssi']+dp-prediction(d,a,n)
                    pairs.append((abs(residual),abs(changed)));outside+=not low<=d<=high
                    if mode=='model_matched_unbounded':max_error=max(max_error,abs(residual-changed))
                    events.append(dict(ordinal=i,direction=direction,shift_m=delta,mode=mode,status='EVALUATED_CONDITIONAL_PROXY',
                        rssi_dbm=r['rssi'],claimed_horizontal_distance_m=r['distance'],modified_distance_m=d,synthetic_power_added_db=dp,
                        baseline_score_db=abs(residual),changed_score_db=abs(changed),threshold_db=threshold,baseline_alarm=abs(residual)>threshold,changed_alarm=abs(changed)>threshold,
                        training_support='outside' if not low<=d<=high else 'inside',time_scope='same phone/boot only',physical_packet_identity='UNVERIFIED',truth='RID claim assumed, independent truth unavailable'))
                attack_summary.append(dict(direction=direction,shift_m=delta,mode=mode,total_evaluation_rows=len(test),evaluated_rows=len(pairs),held_rows=len(test)-len(pairs),
                    outside_training_distance_rows=outside,**transitions(pairs,threshold),max_matched_residual_error_db=max_error if mode=='model_matched_unbounded' and pairs else None))
    blocks=[]
    for i,g in enumerate(merge_small_blocks(test)):
        count=sum(abs(r['rssi']-prediction(r['distance'],a,n))>threshold for r in g)
        blocks.append(dict(block='B'+str(i+1),n=len(g),baseline_alarm_count=count,baseline_alarm_fraction=count/len(g),independent_run=False))
    # Do not publish small individual observation sets as per-event evidence.
    if blocks and sum(x['n'] for x in blocks)!=len(test):raise ValueError('Block denominator mismatch')
    summary=dict(stage='issue96',status='EXECUTED_FAILURE_DIAGNOSIS',adoption='NOT_SUPPORTED',
        scope='real RSSI and unmodified RID claims; synthetic claim/power changes; no independently labelled FPR/TPR',
        counts=dict(eligible=len(data),train=len(train),calibration=len(cal),evaluation=len(test),purged=len(data)-len(train)-len(cal)-len(test)),
        frozen_model=dict(intercept_dbm=a,horizontal_proxy_n=n,threshold_db=threshold,training_claimed_horizontal_distance_m=[low,high]),
        evaluation_baseline_alarm_count=baseline_alarms,evaluation_rows=len(test),evaluation_baseline_alarm_fraction=baseline_alarms/len(test),
        partitions=parts,descriptive_blocks=blocks,independent_runs_established=False,confidence_interval='NOT_EVALUABLE_no_independent_runs',
        threshold_tuned_on_evaluation=False,frozen_selection_changed=False,synthetic_conditions=len(attack_summary),
        rf_power_control_executed=False,physical_receive_loss_simulated=False)
    (private_output/'proxy-events-private.json').write_text(json.dumps(events,indent=2)+'\n')
    (private_output/'proxy-partitions-private.json').write_text(json.dumps(private_rows,indent=2)+'\n')
    return summary,attack_summary,selection_sensitivity(all_rows),events
