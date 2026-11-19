#!/usr/bin/env python3
"""Recompute anonymous controlled-source/position counts from private phone DB snapshots."""
import argparse
import collections
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'experiments/kmp-rid-observer/scripts'))
from smoke_device_persistence import analyze_database
from background_evidence import target_counts,in_phase


def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda:f.read(1024**2),b''):h.update(chunk)
    return h.hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--private-input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();os.umask(0o077)
    if 'captures' not in a.private_input.resolve().parts or a.private_input.is_symlink():raise ValueError('Private captures input required')
    if a.output.exists():raise ValueError('Fresh public output required')
    target=json.loads((a.private_input/'study-marker-private.json').read_text())['uas_id'];nodes=[];hashes=[]
    for label in ['Android-1','Android-2']:
        root=a.private_input/label;plan=json.loads((root/'plan.json').read_text());phases=[x for x in plan['phases'] if 'end_us' in x]
        paths=[root/n for n in ['before.sqlite','after.sqlite','restarted.sqlite']];before=[digest(x) for x in paths]
        result=analyze_database(paths[0],paths[1],phases,target_id=target)
        with sqlite3.connect(paths[1].resolve().as_uri()+'?mode=ro',uri=True) as db:
            db.execute('ATTACH DATABASE ? AS old',(paths[0].resolve().as_uri()+'?mode=ro',))
            rows=[json.loads(raw) for (raw,) in db.execute('SELECT b.raw_json FROM main.observations b LEFT JOIN old.observations a ON a.id=b.id WHERE a.id IS NULL')]
            fixes=[json.loads(raw) for (raw,) in db.execute('SELECT b.raw_json FROM main.receiver_fixes b LEFT JOIN old.receiver_fixes a ON a.id=b.id WHERE a.id IS NULL')]
        for source,phase in zip(phases,result['phases']):
            phase.update(target_counts(rows,source['start_us'],source['end_us'],target))
            phase.update(screen_awake_all_samples=all(x['awake'] for x in source['samples']) if source['samples'] else None,
                         deep_idle_all_samples=all(x.get('deep_idle') for x in source['samples']) if source['samples'] else None)
            selected=[r for r in fixes if in_phase(r.get('fix_elapsed_us'),source['start_us'],source['end_us'])]
            phase['standalone_provider_counts']=dict(collections.Counter(r.get('provider') if r.get('provider') in ['gps','network','passive','fused'] else 'other' for r in selected))
        if before!=[digest(x) for x in paths]:raise ValueError('Snapshot changed during analysis')
        hashes.extend(dict(node=label,file=x.name,sha256=h) for x,h in zip(paths,before))
        result.update(node=label,model='ASUS_Z017DA',android='7.0',api=24,app_version='0.14-segmented-storage',
                      protocol_completed=plan['completion']=='phases_completed',cleanup=plan.get('cleanup'),
                      forced_doze_state_verified=plan.get('forced_doze_state_verified',False),forced_doze_cleanup=plan.get('forced_doze_cleanup'),
                      independent_gnss_accuracy_verified=False,real_drone_used=False,
                      analysis_correction='Android uses rid_messages[].uas_id; Pi claimed_uas_ids alone was insufficient')
        old=json.loads((root/'validation.json').read_text());result['all_rows_unchanged_after_restart']=old['all_rows_unchanged_after_restart'];nodes.append(result)
    (a.private_input/'analysis-input-hashes-private.json').write_text(json.dumps(hashes,indent=2)+'\n')
    a.output.mkdir(parents=True);(a.output/'summary.json').write_text(json.dumps(dict(nodes=nodes,source='controlled Pi Beacon with synthetic session ID and no Location',natural_doze_tested=False,usb_connected=True,battery_unplug_was_simulated=True,physical_packet_delivery_rate=None),indent=2)+'\n')
    import csv
    with (a.output/'phases.csv').open('x',newline='') as f:
        fields=['node','phase','duration_s','scan_records','fresh_records','target_records','target_fresh_records','target_distinct_vendor_contents','target_distinct_observation_timestamps','target_rssi_present_records','attached_position_matched','standalone_fixes_stored','foreground_service_all_samples','deep_idle_all_samples','pss_max_kib']
        w=csv.DictWriter(f,fieldnames=fields,lineterminator='\n');w.writeheader()
        for n in nodes:
            for phase in n['phases']:w.writerow(dict(node=n['node'],phase=phase['name'],**{k:phase[k] for k in fields if k not in ['node','phase']}))
    print(json.dumps([dict(node=n['node'],protocol_completed=n['protocol_completed'],phases=[{k:p[k] for k in ['name','target_fresh_records','target_distinct_vendor_contents','standalone_fixes_stored','deep_idle_all_samples']} for p in n['phases']]) for n in nodes]))


if __name__=='__main__':main()
