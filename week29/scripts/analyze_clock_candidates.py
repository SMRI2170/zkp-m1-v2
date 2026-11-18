#!/usr/bin/env python3
"""Explore constant clock-offset hypotheses; never establish a true packet/date match."""
import argparse
import collections
import csv
import datetime as dt
import json
import os
import sqlite3
from pathlib import Path

from audit_field_time import describe,epoch,unwrap_next


def paths_to_anchor(graph,start,anchor):
    result=[]
    def walk(node,path,low,high):
        if node==anchor:result.append(dict(path=path,offset_low_s=low,offset_high_s=high));return
        for nxt,lo,hi in graph.get(node,[]):
            if nxt not in path:walk(nxt,path+[nxt],low+lo,high+hi)
    walk(start,[start],0,0)
    return result


def overlaps_window(time,low,high,start,end):
    return time+high>=start and time+low<end


def active_release_path(path,active):
    return bool(active) and Path(str(active)).name in Path(path).parts


def main():
    p=argparse.ArgumentParser();p.add_argument('--audit-private',type=Path,required=True)
    p.add_argument('--audit-output',type=Path,required=True)
    p.add_argument('--config',type=Path,required=True);p.add_argument('--anchor-group',required=True)
    a=p.parse_args();os.umask(0o077)
    if not a.audit_private.resolve().is_relative_to(Path(__file__).resolve().parents[2]/'captures'):
        raise ValueError('Private ledgers must remain in captures/')
    status=json.loads((a.audit_output/'status.json').read_text())
    if not status['completed']:raise ValueError('Audit has not completed')
    summary=json.loads((a.audit_output/'summary.json').read_text())
    matches=json.loads((a.audit_private/'content-matches-private.json').read_text())
    observations=[json.loads(l) for l in (a.audit_private/'target-observations-private.jsonl').open()]
    graph=collections.defaultdict(list);byedge=collections.defaultdict(list)
    for x in matches:byedge[(x['group_a'],x['group_b'])].extend(x['utc_offset_candidates_s'])
    for (ga,gb),offsets in byedge.items():
        if not offsets:continue
        graph[ga].append((gb,min(offsets),max(offsets)))
        graph[gb].append((ga,-max(offsets),-min(offsets)))
    cfg=json.loads(a.config.read_text());start,end=map(epoch,cfg['field_utc'])
    groups={x['clock_group']:x for x in summary['clock_groups']}
    if a.anchor_group not in groups:raise ValueError('unknown anchor')
    # Calendar of anchor remains a hypothesis, even if it currently agrees with host time.
    candidates=[];ledgers=[]
    for label,group in groups.items():
        paths=paths_to_anchor(graph,label,a.anchor_group)
        if not paths:
            candidates.append(dict(clock_group=label,status='NOT_EVALUABLE_no_content_path'));continue
        low=min(x['offset_low_s'] for x in paths);high=max(x['offset_high_s'] for x in paths)
        rows=[x for x in observations if x['clock_group']==label]
        times=[x['utc'] for x in rows if x['utc'] is not None]
        first,last=min(times)+low,max(times)+high
        item=dict(clock_group=label,node=group['node'],status='candidate_constant_offset_calendar_hypothesis',
                  simple_paths=len(paths),offset_to_anchor_low_s=low,offset_to_anchor_high_s=high,
                  candidate_first_utc=dt.datetime.fromtimestamp(first,dt.timezone.utc).isoformat(),
                  candidate_last_utc=dt.datetime.fromtimestamp(last,dt.timezone.utc).isoformat(),
                  possibly_in_field_window=sum(overlaps_window(t,low,high,start,end) for t in times),
                  fully_inside_under_this_model=sum(start<=t+low and t+high<end for t in times),
                  field_assignment_verified=False,interval_is_confidence_interval=False)
        candidates.append(item);ledgers.append(dict(clock_group=label,paths=paths))
    # Separate repeated kernel-observation content from unique UTC save occurrences.
    target_dedup={};rid_checks={}
    for label in groups:
        rows=[x for x in observations if x['clock_group']==label]
        keys={(x['mono'],x['payload']) if x['mono'] is not None else ('unknown',x['key']) for x in rows}
        target_dedup[label]=dict(saved_records=len(rows),same_monotonic_and_pack_keys=len(keys),
                                 repeated_monotonic_content_records=len(rows)-len(keys))
        rows=sorted((x for x in rows if x['mono'] is not None),key=lambda x:x['mono'])
        residuals=[]
        if rows:
            previous=rows[0]['reference']['claimed_seconds_within_hour'];lastmono=rows[0]['mono']
            for x in rows[1:]:
                elapsed=x['mono']-lastmono;current=unwrap_next(previous,x['reference']['claimed_seconds_within_hour'],elapsed)
                residuals.append(current-previous-elapsed);previous=current;lastmono=x['mono']
        rid_checks[label]=dict(unwrap_step_minus_monotonic_s=describe(residuals),
                              calendar_not_inferred=True,unwrap_is_nearest_elapsed_hypothesis=True)
    # Record which release was active at collection, keeping actual release names private.
    manifest=json.loads((a.audit_private/'file-manifest-private.json').read_text());scopes=[]
    for source in cfg['sources']:
        base=Path(source['snapshot']).parent
        if source['kind']!='pi':continue
        inv=json.loads((base/'inventory-private.json').read_text());active=inv.get('active_release')
        if not active and (base/'cause-evidence/deployed-private.json').exists():
            active=json.loads((base/'cause-evidence/deployed-private.json').read_text()).get('release')
        for release in sorted({x['release'] for x in manifest if x['node']==source['node']}):
            matching=[x for x in manifest if x['node']==source['node'] and x['release']==release]
            scopes.append(dict(node=source['node'],scope=release,
                active_at_original_collection=any(active_release_path(x['path'],active) for x in matching),
                collection_time_not_experiment_time=True))
    public=dict(anchor_group=a.anchor_group,anchor_calendar_verified_for_experiment=False,
                offset_model='constant per clock correspondence, content-equality hypotheses',
                interval_meaning='envelope of all observed content-pair offsets across simple paths; not a statistical CI',
                candidates=candidates,target_record_semantics=target_dedup,rid_monotonic_checks=rid_checks,
                scopes=scopes,independent_calendar_anchors_verified=0)
    db=sqlite3.connect((a.audit_private/'audit-private.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
    availability=[]
    for source in cfg['sources']:
        n,boots,positions,no_utc,no_mono=db.execute('''SELECT COUNT(*),COALESCE(SUM(boot<>''),0),
             COALESCE(SUM(receiver_position),0),COALESCE(SUM(utc IS NULL),0),COALESCE(SUM(mono IS NULL),0)
             FROM observations WHERE node=?''',(source['node'],)).fetchone()
        base=Path(source['snapshot']).parent;invpath=base/'inventory-private.json'
        inv=json.loads(invpath.read_text()) if invpath.exists() else {}
        current_boot=bool(inv.get('boot_id')) if isinstance(inv,dict) else False
        availability.append(dict(node=source['node'],canonical_observations=n,
            rows_with_recorded_boot_scope=boots,receiver_position_present_rows=positions,
            missing_utc_rows=no_utc,missing_monotonic_rows=no_mono,
            boot_id_available_at_collection=current_boot,
            historical_boot_assignment_verified=False,independent_truth_available_for_experiment=False,
            transmitter_total_known=False))
    db.close();public['input_availability']=availability
    (a.audit_output/'clock-candidates.json').write_text(json.dumps(public,indent=2)+'\n')
    with (a.audit_output/'candidate-windows.csv').open('w',newline='') as f:
        keys=sorted(set().union(*(x.keys() for x in candidates)))
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(candidates)
    with (a.audit_output/'input-availability.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(availability[0]));w.writeheader();w.writerows(availability)
    (a.audit_private/'clock-path-ledger-private.json').write_text(json.dumps(ledgers,indent=2)+'\n')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.font_manager import FontProperties
    font=FontProperties(fname='/System/Library/Fonts/ヒラギノ角ゴシック W7.ttc')
    plt.rcParams.update({'font.family':font.get_name(),'axes.unicode_minus':False})
    fig,ax=plt.subplots(figsize=(11,4.5))
    valid=[x for x in candidates if x.get('candidate_first_utc')]
    day=epoch('2026-11-16T00:00:00+09:00')
    ax.axvspan((start-day)/3600,(end-day)/3600,color='#dcebdc',label='ユーザー申告の実験時間帯')
    for i,x in enumerate(valid):
        offset=(x['offset_to_anchor_low_s']+x['offset_to_anchor_high_s'])/2
        times=sorted(r['utc'] for r in observations if r['clock_group']==x['clock_group'] and r['utc'] is not None)
        runs=[]
        for t in times:
            if not runs or t-runs[-1][-1]>60:runs.append([])
            runs[-1].append(t)
        for run in runs:
            lo=(run[0]+offset-day)/3600;hi=(run[-1]+offset-day)/3600
            ax.plot([lo,hi],[i,i],lw=7,color='#cb8a23',solid_capstyle='butt')
    ax.set(yticks=range(len(valid)),yticklabels=[x['clock_group'] for x in valid],
           xlabel='11月16日 日本時間 [時]：ASUS-2の記録時計を仮採用',
           title='時刻対応候補（実時刻の確定ではない）\n橙線は記録区間：60秒超の空白は接続しない',xlim=(13.5,18.5))
    ax.grid(axis='x',alpha=.25);ax.legend(loc='upper left');fig.tight_layout()
    fig.savefig(a.audit_output/'candidate-time-windows.png',dpi=170);plt.close(fig)
    print(json.dumps({'candidates':candidates,'record_semantics':target_dedup},indent=2))


if __name__=='__main__':main()
