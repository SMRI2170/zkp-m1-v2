"""PR3 sequential real-time-axis simulation and observation-regime audit."""
import argparse
from collections import defaultdict
import itertools
import json
import os
from pathlib import Path

from normalize import write_csv
from observations import asynchronous_view,detector_projection,unrestricted_single_rssi,same_packet_group,nonidentifiability_counterexample,translated_trajectory_counterexample,symmetric_multisite_counterexample
from scene import run_scene,RX_POSITIONS
from setup import ROOT,REPO


def summarize_views(rows,run_id,spec,prefixes):
    reports=[];receivers=list(RX_POSITIONS)
    for count in prefixes:
        view=asynchronous_view(rows,receivers,count)
        projected=detector_projection(view,run_id)
        decisions=unrestricted_single_rssi(projected)
        common=dict(source_run_id=run_id,model=spec['model'],gap_s=spec['gap_s'],offset_m=spec['offset_x_m'],tx_count=count)
        reports.append(dict(common,regime='asynchronous_one_rssi',receiver_subset=5,
                            rssi_values_per_packet_max=1,
                            selected_opportunities=count,received=sum(r['delivered'] for r in view),
                            valid_rssi=sum(r['rssi_dbm'] is not None for r in view),
                            undetermined=len(decisions),drss_eligible_frames=0,mlat_input_eligible_frames=0,
                            fpr=None,tpr=None,decision='UNDETERMINED'))
        frames=defaultdict(list)
        for r in sorted(rows,key=lambda r:(r['tx_time'],r['rx_node_id'])):
            frames[r['tx_event_id']].append(r)
        selected=list(frames.values())[:count]
        for number in [2,3,4,5]:
            chosen=set(receivers[:number]);valids=[]
            for frame in selected:
                projected=detector_projection([r for r in frame if r['rx_node_id'] in chosen],run_id,'same_physical_packet_comparison')
                valids.append(same_packet_group(projected))
            reports.append(dict(common,regime='same_physical_packet_comparison',receiver_subset=number,
                                rssi_values_per_packet_max=number,
                                selected_opportunities=count*number,received=sum(len(v) for v in valids),
                                valid_rssi=sum(len(v) for v in valids),undetermined=count,
                                drss_eligible_frames=sum(len(v)>=2 for v in valids),
                                mlat_input_eligible_frames=sum(len(v)>=4 for v in valids),
                                fpr=None,tpr=None,decision='DETECTOR_NOT_RUN'))
    return reports


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--raw-dir',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--workspace',type=Path,default=REPO/'.cache/issue70')
    p.add_argument('--smoke',action='store_true',help='10 actual packets separated by one hour before full run')
    a=p.parse_args();os.umask(0o077)
    if not a.raw_dir.resolve().is_relative_to((REPO/'captures').resolve()):p.error('Use ignored captures/')
    if a.raw_dir.exists() or a.out.exists():p.error('Use new output paths; preserve evidence')
    a.raw_dir.mkdir(parents=True,mode=0o700);a.out.mkdir(parents=True)
    cfg=json.loads((ROOT/'config/observations.json').read_text())
    if a.smoke:cfg.update(count=10,prefix_counts=[10],gaps_s=[3600],models=['fixed'],offsets_m=[0])
    (a.out/'configuration.json').write_text(json.dumps(cfg,indent=2)+'\n')
    cases=[];view_metrics=[]
    result=dict(dataset_source='simulation',stage='PR3',status='NOT_RUN',cases=cases,
                scope=cfg['sparse_time_scope'],limitations=['No calibrated spoof detector yet','M2 is an additional observation condition, not the original asynchronous solution'])
    for model,gap,offset in itertools.product(cfg['models'],cfg['gaps_s'],cfg['offsets_m']):
        case=('FixedNormal' if offset==0 else 'PositionOnly') if model=='fixed' else model.title()+('Normal' if offset==0 else 'Spoof')
        if model=='adaptive':case='AdaptiveSpoof' if offset else 'FixedNormal'
        run_id=f'{model}-gap{gap}-offset{offset}-n{cfg["count"]}-seed{cfg["seed"]}'
        cases.append(dict(source_run_id=run_id,status='NOT_RUN',model=model,gap_s=gap,offset_m=offset))
    try:
        result['status']='RUNNING'
        for case in cases:
            case['status']='RUNNING'
            (a.out/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
            model,gap,offset=case['model'],case['gap_s'],case['offset_m']
            label=('FixedNormal' if offset==0 else 'PositionOnly') if model=='fixed' else model.title()+('Normal' if offset==0 else 'Spoof')
            if model=='adaptive':label='AdaptiveSpoof' if offset else 'FixedNormal'
            spec=dict(case=label,model=model,gap_s=gap,count=cfg['count'],seed=cfg['seed'],offset_x_m=offset)
            rows,tx,audit=run_scene(spec,a.workspace.resolve(),a.raw_dir.resolve()/case['source_run_id'])
            case.update(audit,status='OBSERVATION_AUDITED')
            metrics=summarize_views(rows,case['source_run_id'],spec,cfg['prefix_counts'])
            view_metrics.extend(metrics)
            # Preserve detector-only projections separately; no true position,
            # power, attack labels, case names or seed enter detector inputs.
            view=asynchronous_view(rows,list(RX_POSITIONS),cfg['count'])
            projected=detector_projection(view,case['source_run_id'])
            private=a.raw_dir.resolve()/case['source_run_id']
            (private/'async-detector-input.json').write_text(json.dumps(projected)+'\n')
            write_csv(private/'async-decisions.csv',unrestricted_single_rssi(projected))
            write_csv(a.out/'view-metrics.csv',view_metrics)
            (a.out/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
        result['status']='PR3_OBSERVATION_AUDIT_PASSED'
    except Exception as error:
        result.update(status='PR3_FAILED',error=str(error))
        for case in cases:
            if case['status']=='RUNNING':case.update(status='FAILED_SEE_ERROR',error=str(error))
    counterexamples=[nonidentifiability_counterexample(n) for n in [10,100,1000,5000]]
    counterexamples.extend([translated_trajectory_counterexample(1000),symmetric_multisite_counterexample()])
    (a.out/'math-counterexamples.json').write_text(json.dumps(counterexamples,indent=2)+'\n')
    (a.out/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    write_csv(a.out/'case-summary.csv',cases)
    print(json.dumps(dict(status=result['status'],error=result.get('error'),cases=len(cases),completed=sum(c['status']=='OBSERVATION_AUDITED' for c in cases),view_rows=len(view_metrics)),indent=2))
    return 0 if result['status']=='PR3_OBSERVATION_AUDIT_PASSED' else 2


if __name__=='__main__':raise SystemExit(main())
