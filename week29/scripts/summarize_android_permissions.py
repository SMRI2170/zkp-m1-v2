#!/usr/bin/env python3
"""Publish only whitelisted aggregate permission-study evidence, never raw dumps."""
import argparse,csv,json,re
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"experiments/kmp-rid-observer/scripts"))
from permission_evidence import permission_granted

def summarize(root):
    output=[]
    for label in ('Android-1','Android-2'):
        path=root/label
        raw=json.loads((path/'result-private.json').read_text())
        db=raw.get('database',{});denied=raw.get('preservation_at_revoke',{})
        initial_completion=raw['completion']
        denied_text=(path/'package-denied.txt').read_text()
        raw['permissions_denied']=all(permission_granted(denied_text,p) is False for p in ('ACCESS_FINE_LOCATION','ACCESS_COARSE_LOCATION'))
        checks=('permissions_denied','receiver_absent_after_revoke','permission_explanation_visible','receiver_absent_on_denied_ui','original_grants_restored','new_run_after_manual_restart','foreground_service_after_restore')
        valid=all(raw.get(k) is True for k in checks) and db.get('old_rows_unchanged') is True and denied.get('old_rows_unchanged') is True and raw.get('cleanup',{}).get('permissions_restored') is True and raw.get('cleanup',{}).get('receiver_stopped') is True and not raw.get('cleanup',{}).get('errors')
        completion='completed' if valid and len(raw['phases'])==2 and all('end_us' in p for p in raw['phases']) else initial_completion
        flags=[]
        for name in ('package-before.txt','package-final.txt'):
            text=(path/name).read_text()
            flags.append({p:(m.group(1) if (m:=re.search(r'android\.permission\.'+p+r': granted=\w+, flags=\[([^\]]*)\]',text)) else None) for p in ('ACCESS_FINE_LOCATION','ACCESS_COARSE_LOCATION')})
        output.append(dict(node=label,completion=completion,original_execution_completion=initial_completion,denial_reanalyzed_from_retained_dump=initial_completion!=completion,permission_flags_unchanged=(flags[0]==flags[1] if all(v is not None for f in flags for v in f.values()) else None),
            **{k:raw.get(k) for k in ('external_play_store_dialogs_closed','permissions_denied','receiver_absent_after_revoke','permission_explanation_visible','receiver_absent_on_denied_ui','original_grants_restored','new_run_after_manual_restart','foreground_service_after_restore','new_stored_fix_providers','cleanup')},
            baseline_rows=db.get('old_rows'),final_rows=db.get('total_rows'),new_rows=db.get('new_rows'),
            baseline_rows_preserved_at_revoke=denied.get('old_rows_unchanged'),baseline_fixes_preserved_at_revoke=denied.get('old_standalone_fixes_unchanged'),
            baseline_rows_preserved_at_finish=db.get('old_rows_unchanged'),baseline_fixes_preserved_at_finish=db.get('old_standalone_fixes_unchanged'),integrity_check=db.get('integrity_check'),
            phases=[dict(name=p['name'],duration_s=(p['end_us']-p['start_us'])/1e6,active_location_requests=p['active_location_requests']) for p in raw['phases']]))
    return dict(source='real_android_permission_experiment',real_drone_used=False,controlled_rf_source=False,devices='two ASUS_Z017DA Android 7.0 API24; v0.15',
                limitations=['No physical RF PDR or target RID comparison','No natural Doze or outdoor GNSS test','No proof that every queued write survives process death','UI guide, not system permission-dialog button, tested after revoke'],devices_results=output)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--private-input',required=True,type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    result=summarize(a.private_input);a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    fields=('node','completion','permissions_denied','original_grants_restored','new_run_after_manual_restart','foreground_service_after_restore','baseline_rows','final_rows','baseline_rows_preserved_at_finish','baseline_fixes_preserved_at_finish','integrity_check','gps_fixes','network_fixes')
    with a.output.with_suffix('.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields,lineterminator="\n");writer.writeheader()
        for row in result['devices_results']:
            counts=row['new_stored_fix_providers'] or {}
            writer.writerow({**{k:row.get(k) for k in fields[:-2]},'gps_fixes':counts.get('gps',0),'network_fixes':counts.get('network',0)})
