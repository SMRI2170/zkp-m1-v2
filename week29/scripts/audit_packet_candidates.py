#!/usr/bin/env python3
"""Issue95: content/time candidates, never physical-packet confirmation from scan caches."""
import argparse
import collections
import itertools
import json
import os
from pathlib import Path

from audit_field_time import epoch,sha
from audit_android_position import write_csv
from audit_rid_intervals import time_status


def classify(left,right,offset_a,offset_b,window_s,shift_b_s=0):
    """Conservative scan-content classification; no sender-clock or RF frame evidence."""
    if not left or not right:return 'unmatched',[]
    if offset_a is None or offset_b is None:return 'ambiguous',[]
    edges=[]
    for i,a in enumerate(left):
        for j,b in enumerate(right):
            if a['bssid']!=b['bssid'] or a['frequency']!=b['frequency']:continue
            # A range over alternative clock models is not a probability interval.
            low=a['utc']-b['utc']+offset_a[0]-offset_b[1]-shift_b_s
            high=a['utc']-b['utc']+offset_a[1]-offset_b[0]-shift_b_s
            if low<=window_s and high>=-window_s:edges.append((i,j))
    if not edges:return 'unmatched',[]
    if len(left)>1 or len(right)>1 or len(edges)>1:return 'ambiguous',edges
    return 'candidate',edges


def main():
    p=argparse.ArgumentParser();p.add_argument('--config',type=Path,required=True);p.add_argument('--clock-summary',type=Path,required=True)
    p.add_argument('--private-output',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();os.umask(0o077)
    if not a.private_output.resolve().is_relative_to(Path(__file__).resolve().parents[2]/'captures'):raise ValueError('Private ledgers stay in captures/')
    for d in [a.private_output,a.output]:d.mkdir(parents=True,exist_ok=True)
    cfg=json.loads(a.config.read_text());ident=json.loads(Path(cfg['identity_file']).read_text())['claimed_id']
    clocks=json.loads(a.clock_summary.read_text())['candidates'];offsets={}
    for node in {x['node'] for x in clocks}:
        choices=[x for x in clocks if x['node']==node and x.get('offset_to_anchor_low_s') is not None]
        if len(choices)==1:offsets[node]=(choices[0]['offset_to_anchor_low_s'],choices[0]['offset_to_anchor_high_s'])
    nodes={};features=[];inputs=[]
    fields=['bssid','vendor_content_digest','odid_counter','beacon_tsf_us','sequence_control','monotonic_time_us',
            'received_at_utc','boot_scope','cache_stale','time_uncertainty_ms','physical_packet_match']
    for source in cfg['sources']:
        node=source['node'];path=Path(source['reference_jsonl']);before=sha(path);rows=[];counts=collections.Counter();seen=set();total=0
        for line in path.open():
            x=json.loads(line);d=x['reference'];r=x['capture']
            if not (d.get('reference_decode_ok') and bytes.fromhex(d.get('id_hex','')).rstrip(b'\0').decode(errors='replace')==ident):continue
            total+=1
            for field in fields:
                if r.get(field) is not None:counts[field]+=1
            if time_status(r)!='ELIGIBLE_TIME':continue
            key=(r.get('boot_scope'),r.get('bssid'),r.get('frequency_mhz'),r.get('monotonic_time_us'),r.get('vendor_content_digest'),r.get('odid_payload_hex'))
            if key in seen:continue
            seen.add(key);rows.append(dict(utc=epoch(r['received_at_utc']),mono=r['monotonic_time_us']/1e6,
                boot=r.get('boot_scope'),payload=r.get('odid_payload_hex'),bssid=r.get('bssid'),frequency=r.get('frequency_mhz'),rssi=r.get('rssi_dbm')))
        if before!=sha(path):raise ValueError('Input changed')
        inputs.append(dict(node=node,path=str(path),sha256=before));nodes[node]=rows
        features.extend(dict(node=node,field=f,non_null_rows=counts[f],target_rows=total) for f in fields)
    summary=dict(code_sha256=sha(Path(__file__)),confirmed_physical_packets=0,clock_alignment_verified=False,
        pair_results=[],rssi_difference='NOT_EVALUABLE_no_confirmed_same_transmission',
        cancellation_of_unknown_power='NOT_EVALUABLE_common_transmission_unverified',
        note='candidate clock intervals are alternative-model ranges, not statistical confidence intervals')
    ledger=[];sensitivity=[]
    for left,right in itertools.combinations(nodes,2):
        aa=collections.defaultdict(list);bb=collections.defaultdict(list)
        for r in nodes[left]:aa[r['payload']].append(r)
        for r in nodes[right]:bb[r['payload']].append(r)
        common=sorted(set(aa)&set(bb));pair=f'{left} / {right}'
        summary['pair_results'].append(dict(pair=pair,shared_content_types=len(common),left_only_content_types=len(set(aa)-set(bb)),right_only_content_types=len(set(bb)-set(aa))))
        for window in [.1,1,5,30,60]:
            for shift in [-5,0,5]:
                counts=collections.Counter()
                for payload in common:
                    status,edges=classify(aa[payload],bb[payload],offsets.get(left),offsets.get(right),window,shift)
                    counts[status]+=1
                    if window==5 and shift==0:ledger.append(dict(pair=pair,payload=payload,status=status,left=aa[payload],right=bb[payload],compatible_pairs=edges))
                sensitivity.append(dict(pair=pair,window_s=window,relative_clock_shift_s=shift,shared_content_types=len(common),
                    matched_confirmed=0,candidate=counts['candidate'],ambiguous=counts['ambiguous'],unmatched=counts['unmatched']))
    write_csv(a.output/'field-availability.csv',features);write_csv(a.output/'window-sensitivity.csv',sensitivity)
    (a.private_output/'candidate-ledger-private.json').write_text(json.dumps(ledger,indent=2)+'\n')
    (a.private_output/'inputs-private.json').write_text(json.dumps(inputs,indent=2)+'\n')
    (a.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.font_manager import FontProperties
    plt.rcParams.update({'font.family':FontProperties(fname='/System/Library/Fonts/ヒラギノ角ゴシック W7.ttc').get_name(),'axes.unicode_minus':False})
    fig,ax=plt.subplots(figsize=(12,5))
    base=[x for x in sensitivity if x['window_s']==5 and x['relative_clock_shift_s']==0 and x['shared_content_types']]
    bottom=[0]*len(base)
    for key,label,color in [('candidate','一対一の内容・時刻候補','#1768aa'),('ambiguous','複数対応または時計不明','#d99532'),('unmatched','仮定した窓で対応なし','#b8bdc5')]:
        values=[x[key] for x in base];ax.bar([x['pair'] for x in base],values,bottom=bottom,label=label,color=color)
        bottom=[x+y for x,y in zip(bottom,values)]
    ax.set(ylabel='共有Pack内容の種類数：パケット数ではない',title='時計補正候補・5秒窓の場合：同一物理送信の確認は全て0件')
    ax.tick_params(axis='x',rotation=15);ax.legend();fig.tight_layout();fig.savefig(a.output/'01_candidate_classes.png',dpi=170);plt.close(fig)
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
