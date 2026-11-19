#!/usr/bin/env python3
"""Finite destructive-permission experiment, preserving app data.

Only runs if FINE/COARSE are already granted and receiver stopped. Revokes these
permissions, then restores the original grants in finally. No uninstall, data clear,
permission bypass, RF emission, scan-setting or battery-setting changes.
All raw evidence including UI/location dumps stays in private captures/.
"""
import argparse,json,os,re,time,sqlite3
from pathlib import Path
from evaluate_pixel import Device,PKG,private_output
from smoke_device_persistence import wake_app,read_run,merge_database_snapshots,analyze_database
from permission_evidence import permission_granted,active_location_requests,stored_fix_providers,recover_private_snapshot,known_play_store_crash_close

PERMISSIONS=('ACCESS_FINE_LOCATION','ACCESS_COARSE_LOCATION')

def execute(device,out,seconds):
    result={'completion':'running','phases':[],'controlled_rf_source':False,'gps_truth_verified':False}
    def store(name,value):
        path=out/name
        with path.open('w') as f:
            if isinstance(value,str):f.write(value)
            else:json.dump(value,f,ensure_ascii=False,indent=2)
        path.chmod(0o600)
    def save():store('result-private.json',result)
    def package():return device.shell('dumpsys','package',PKG)
    def ui(name):
        for attempt in range(4):
            device.shell('uiautomator','dump',device.ui_path);device.shell('chmod','600',device.ui_path)
            value=device.shell('cat',device.ui_path);store(name+'-'+str(attempt)+'.xml',value)
            close=known_play_store_crash_close(value)
            if close is None:return value
            if attempt==3:raise RuntimeError('Repeated external crash dialogs; stop rather than disable unrelated apps')
            device.shell('input','tap',str((close[0]+close[2])//2),str((close[1]+close[3])//2))
            result['external_play_store_dialogs_closed']=result.get('external_play_store_dialogs_closed',0)+1;save()
        raise RuntimeError('UI unavailable')
    def tap_control(label):
        import xml.etree.ElementTree as ET
        deadline=time.monotonic()+25
        while time.monotonic()<deadline:
            tree=ET.fromstring(ui('control'))
            nodes=[n for n in tree.iter('node') if n.get('package')==PKG and n.get('text')==label and n.get('enabled')=='true']
            if len(nodes)==1:
                x1,y1,x2,y2=map(int,re.findall(r'\d+',nodes[0].get('bounds','')))
                device.shell('input','tap',str((x1+x2)//2),str((y1+y2)//2));return
        raise RuntimeError('Enabled app control unavailable')
    def snapshot(name):
        if 'ServiceRecord{' in device.shell('dumpsys','activity','services',PKG):raise RuntimeError('Live DB snapshot forbidden')
        device.shell('am','force-stop',PKG)
        paths=device.shell('run-as',PKG,'find','files/captures/database','-type','f').splitlines()
        paths=sorted(p for p in paths if p=='files/captures/database/observations.sqlite' or re.fullmatch(r'files/captures/database/segments/segment-[0-9]{6}-[a-f0-9-]+\.sqlite',p))
        if not paths:raise RuntimeError('No prior DB; pre-existing data required')
        dest=out/(name+'-sources');dest.mkdir(mode=0o700);sources=[]
        all_files=device.shell('run-as',PKG,'find','files/captures/database','-type','f').splitlines()
        recovered=out/(name+'-recovered');recovered.mkdir(mode=0o700)
        for i,p in enumerate(paths):
            path=dest/(str(i)+'.sqlite')
            path.write_bytes(device.run('exec-out','run-as',PKG,'cat',p,binary=True));path.chmod(0o600)
            journal=None
            if p+'-journal' in all_files:
                journal=dest/(str(i)+'.sqlite-journal');journal.write_bytes(device.run('exec-out','run-as',PKG,'cat',p+'-journal',binary=True));journal.chmod(0o600)
            derived=recover_private_snapshot(path,journal,recovered/(str(i)+'.sqlite'));sources.append((p,derived))
        merge_database_snapshots(sources,out/(name+'.sqlite'))
    initial=package();store('package-before.txt',initial)
    if any(permission_granted(initial,p) is not True for p in PERMISSIONS):raise RuntimeError('Both permissions must already be granted; no new grants allowed')
    if 'ServiceRecord{' in device.shell('dumpsys','activity','services',PKG):raise RuntimeError('Existing receiver left untouched')
    awake='mWakefulness=Awake' in device.shell('dumpsys','power')
    changed=False;started=False
    snapshot('before');save()
    try:
        wake_app(device);tap_control('受信開始');started=True;tap_control('記録開始')
        run=read_run(device,None);store('run-before.txt',run)
        phase={'name':'granted_before_revoke','start_us':device.time_us(),'samples':[]};result['phases'].append(phase)
        time.sleep(seconds)
        location=device.shell('dumpsys','location');store('location-active-before.txt',location)
        phase['active_location_requests']=active_location_requests(location,PKG);phase['end_us']=device.time_us();save()
        # No live copy: after revoke retain DB plus rollback journal, recover a separate copy.
        changed=True
        for permission in PERMISSIONS:device.shell('pm','revoke',PKG,'android.permission.'+permission)
        time.sleep(2)
        denied=package();store('package-denied.txt',denied)
        result['permissions_denied']=all(permission_granted(denied,p) is False for p in PERMISSIONS)
        result['receiver_absent_after_revoke']='ServiceRecord{' not in device.shell('dumpsys','activity','services',PKG)
        snapshot('denied')
        result['preservation_at_revoke']=analyze_database(out/'before.sqlite',out/'denied.sqlite',[])
        wake_app(device);denied_ui=ui('denied-open')
        if '未許可' not in denied_ui:
            tap_control('受信開始');denied_ui=ui('denied-start')
        result['permission_explanation_visible']='未許可' in denied_ui
        result['receiver_absent_on_denied_ui']='ServiceRecord{' not in device.shell('dumpsys','activity','services',PKG)
        device.shell('input','keyevent','KEYCODE_BACK');save()
        for permission in PERMISSIONS:device.shell('pm','grant',PKG,'android.permission.'+permission)
        restored=package();store('package-restored.txt',restored)
        result['original_grants_restored']=all(permission_granted(restored,p) is True for p in PERMISSIONS)
        wake_app(device);tap_control('受信開始');tap_control('記録開始')
        new_run=read_run(device,run);result['new_run_after_manual_restart']=new_run!=run
        phase={'name':'granted_after_restore','start_us':device.time_us(),'samples':[]};result['phases'].append(phase)
        time.sleep(seconds)
        location=device.shell('dumpsys','location');store('location-active-restored.txt',location)
        phase['active_location_requests']=active_location_requests(location,PKG);phase['end_us']=device.time_us()
        service=device.shell('dumpsys','activity','services',PKG);store('service-restored.txt',service)
        result['foreground_service_after_restore']='isForeground=true' in service
        tap_control('記録停止');tap_control('受信停止');started=False;time.sleep(1)
        snapshot('after')
        result['database']=analyze_database(out/'before.sqlite',out/'after.sqlite',result['phases'])
        with sqlite3.connect((out/'after.sqlite').resolve().as_uri()+'?mode=ro',uri=True) as db:
            db.execute('ATTACH DATABASE ? AS old',((out/'before.sqlite').resolve().as_uri()+'?mode=ro',))
            fixes=[json.loads(r[0]) for r in db.execute('SELECT b.raw_json FROM receiver_fixes b LEFT JOIN old.receiver_fixes a ON a.id=b.id WHERE a.id IS NULL')]
        result['new_stored_fix_providers']=stored_fix_providers(fixes)
        result['completion']='completed'
    except Exception as e:
        result['completion']='failed';result['failure_type']=type(e).__name__;save();raise
    finally:
        errors=[]
        if changed:
            for permission in PERMISSIONS:
                try:device.shell('pm','grant',PKG,'android.permission.'+permission)
                except Exception:errors.append('permission_restore_failed')
        try:
            if started:
                # This test started the receiver. Force-stop is bounded to this app and preserves DB.
                device.shell('am','force-stop',PKG)
            final=package();store('package-final.txt',final)
            result['cleanup']={'permissions_restored':all(permission_granted(final,p) is True for p in PERMISSIONS),'receiver_stopped':'ServiceRecord{' not in device.shell('dumpsys','activity','services',PKG),'errors':errors}
            if not awake:device.shell('input','keyevent','KEYCODE_SLEEP')
            device.shell('rm','-f',device.ui_path)
        except Exception:result['cleanup']={'errors':errors+['cleanup_check_failed']}
        save()
    checks=['permissions_denied','receiver_absent_after_revoke','permission_explanation_visible','receiver_absent_on_denied_ui','original_grants_restored','new_run_after_manual_restart','foreground_service_after_restore']
    accepted=all(result.get(k) is True for k in checks) and result['database']['old_rows_unchanged'] and result['preservation_at_revoke']['old_rows_unchanged'] and result['cleanup'].get('permissions_restored') and result['cleanup'].get('receiver_stopped') and not result['cleanup'].get('errors')
    if not accepted:
        result['completion']='failed_acceptance';save();raise RuntimeError('Acceptance failed; inspect private result and cleanup')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--serial',required=True);parser.add_argument('--output',required=True,type=Path);parser.add_argument('--phase-seconds',type=int,default=20)
    args=parser.parse_args()
    if not 20<=args.phase_seconds<=60:parser.error('phase-seconds must be 20..60')
    os.umask(0o077);out=private_output(args.output)
    result=execute(Device(args.serial),out,args.phase_seconds)
    print(json.dumps({'completion':result['completion'],'cleanup':result.get('cleanup')},ensure_ascii=False))

if __name__=='__main__':main()
