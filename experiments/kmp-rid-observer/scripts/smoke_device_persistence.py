#!/usr/bin/env python3
"""Bounded real-device smoke test; start a controlled RF source separately.

No APK install, permission grants, scan-setting changes, DB deletion or RF emission.
Private evidence only under captures/. Not an RF direction accuracy test.
"""
import argparse
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import time
import xml.etree.ElementTree as ET

from evaluate_pixel import Device, PKG, private_output
from background_evidence import study_ids, target_counts, doze_verified, in_phase


def pss_kib(text):
    for pattern in [r'(?m)^\s*TOTAL PSS:\s*(\d+)', r'(?m)^\s*TOTAL\s+(\d+)']:
        m=re.search(pattern,text)
        if m:return int(m.group(1))
    return None


def phase_counts(rows,start,end):
    # 100ms guard band around coarse /proc/uptime boundaries; never count cached/stale as fresh.
    selected=[r for r in rows if r.get('monotonic_time_us') is not None and
              start+100_000 <= r['monotonic_time_us'] < end-100_000]
    return dict(scan_records=len(selected),fresh_records=sum(r.get('cache_stale') is False for r in selected),
                heading_matched_records=sum((r.get('direction') or {}).get('missing_reason') is None
                    and (r.get('direction') or {}).get('phone_heading_magnetic_deg') is not None for r in selected))


def analyze_database(before,after,phases,target_id=None):
    with sqlite3.connect(Path(after).resolve().as_uri()+'?mode=ro',uri=True) as b:
        b.execute('ATTACH DATABASE ? AS old',(Path(before).resolve().as_uri()+'?mode=ro',))
        same=b.execute('SELECT COUNT(*) FROM (SELECT * FROM old.observations EXCEPT SELECT * FROM main.observations)').fetchone()[0]==0
        rows=[]
        for (raw,) in b.execute('SELECT b.raw_json FROM main.observations b LEFT JOIN old.observations a ON a.id=b.id WHERE a.id IS NULL'):
            r=json.loads(raw);rows.append({k:r.get(k) for k in ['monotonic_time_us','cache_stale','direction','receiver_position','claimed_uas_ids','rid_messages','rssi_dbm','vendor_content_digest']})
        result=dict(old_rows=b.execute('SELECT COUNT(*) FROM old.observations').fetchone()[0],
                    total_rows=b.execute('SELECT COUNT(*) FROM main.observations').fetchone()[0],new_rows=len(rows),old_rows_unchanged=same,
                    integrity_check=b.execute('pragma integrity_check').fetchone()[0],
                    fresh_rows=sum(r.get('cache_stale') is False for r in rows),
                    raw_text_rows=b.execute("select count(*) from observations where text_line like '%raw_vendor_ie_hex=%'").fetchone()[0],
                    phases=[])
        fixes=[]
        available=b.execute("SELECT 1 FROM sqlite_master WHERE name='receiver_fixes'").fetchone() is not None and b.execute("SELECT 1 FROM old.sqlite_master WHERE name='receiver_fixes'").fetchone() is not None
        if available:
            fixes=[json.loads(raw) for (raw,) in b.execute('SELECT b.raw_json FROM main.receiver_fixes b LEFT JOIN old.receiver_fixes a ON a.id=b.id WHERE a.id IS NULL')]
        result['standalone_fix_stream_available']=available
        result['old_standalone_fixes_unchanged']=b.execute('SELECT COUNT(*) FROM (SELECT * FROM old.receiver_fixes EXCEPT SELECT * FROM main.receiver_fixes)').fetchone()[0]==0 if available else None
        for phase in phases:
            samples=[x['pss_kib'] for x in phase['samples'] if x['pss_kib'] is not None]
            result['phases'].append(dict(name=phase['name'],duration_s=(phase['end_us']-phase['start_us'])/1e6,
                foreground_service_all_samples=all(x['foreground_service'] for x in phase['samples']),
                samples=len(phase['samples']),pss_samples=len(samples),pss_mean_kib=sum(samples)/len(samples) if samples else None,
                pss_max_kib=max(samples) if samples else None,**phase_counts(rows,phase['start_us'],phase['end_us'])))
            selected=[r for r in rows if r.get('monotonic_time_us') is not None and phase['start_us']+100000<=r['monotonic_time_us']<phase['end_us']-100000]
            target=[r for r in selected if target_id and target_id in study_ids(r)]
            result['phases'][-1].update(target_records=len(target) if target_id else None,target_fresh_records=sum(r.get('cache_stale') is False for r in target) if target_id else None,target_distinct_vendor_contents=len({r.get('vendor_content_digest') for r in target if r.get('vendor_content_digest') and r.get('cache_stale') is False}) if target_id else None,attached_position_matched=sum((r.get('receiver_position') or {}).get('match_status')=='MATCHED' for r in selected),standalone_fixes_stored=sum(in_phase(r.get('fix_elapsed_us'),phase['start_us'],phase['end_us']) for r in fixes) if available else None)
        return result


def merge_database_snapshots(sources,destination):
    """Private derived comparison DB; retain each source DB and avoid cross-segment ID collisions."""
    with sqlite3.connect(destination) as out:
        out.execute('CREATE TABLE observations(id TEXT PRIMARY KEY,raw_json TEXT,text_line TEXT,original_row TEXT)')
        out.execute('CREATE TABLE receiver_fixes(id TEXT PRIMARY KEY,raw_json TEXT)')
        for label,path in sources:
            with sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True) as db:
                if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise RuntimeError('Snapshot integrity failed')
                columns=[x[1] for x in db.execute('PRAGMA table_info(observations)')]
                for row in db.execute('SELECT * FROM observations ORDER BY id'):
                    values=dict(zip(columns,row))
                    out.execute('INSERT INTO observations VALUES(?,?,?,?)',
                        (label+'#'+str(values['id']),values['raw_json'],values['text_line'],json.dumps(values,sort_keys=True)))
                if db.execute("SELECT 1 FROM sqlite_master WHERE name='receiver_fixes'").fetchone():
                    for row_id,raw in db.execute('SELECT id,raw_json FROM receiver_fixes ORDER BY id'):
                        out.execute('INSERT INTO receiver_fixes VALUES(?,?)',(label+'#'+str(row_id),raw))
    os.chmod(destination,0o600)


def tap_enabled(device,label,timeout=20):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        device.shell('uiautomator','dump',device.ui_path)
        device.shell('chmod','600',device.ui_path)
        tree=ET.fromstring(device.shell('cat',device.ui_path))
        nodes=[n for n in tree.iter('node') if n.get('package')==PKG and n.get('text')==label and n.get('enabled')=='true']
        if len(nodes)==1:
            x1,y1,x2,y2=map(int,re.findall(r'\d+',nodes[0].get('bounds','')))
            device.shell('input','tap',str((x1+x2)//2),str((y1+y2)//2));return
        time.sleep(.5)
    raise RuntimeError('Enabled app control unavailable: '+label)


def read_run(device,previous,timeout=8):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        root=ET.fromstring(device.shell('run-as',PKG,'cat','shared_prefs/receiver.xml'))
        values=[n.text for n in root.findall('string') if n.get('name')=='last_run']
        if values and values[0]!=previous and re.fullmatch('[0-9a-f-]{36}',values[0]):return values[0]
        time.sleep(.5)
    raise RuntimeError('Recording not started; private evidence retained')


def wake_app(device):
    device.shell('input','keyevent','KEYCODE_WAKEUP')
    policy=device.shell('dumpsys','window','policy')
    # Only dismiss a non-credential swipe screen, never enter/disable/bypass a PIN.
    if re.search(r'(?m)^\s*showing=true\s*$',policy):
        if not re.search(r'(?m)^\s*secure=false\s*$',policy):
            raise RuntimeError('Unlock the credential-protected phone manually')
        device.shell('input','keyevent','KEYCODE_MENU')
    device.shell('am','start','-n',PKG+'/.MainActivity')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--serial');p.add_argument('--phase-seconds',type=int,default=30)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--source-kind',choices=['controlled','ambient'],default='controlled')
    p.add_argument('--include-forced-doze',action='store_true')
    p.add_argument('--target-id-file',type=Path)
    args=p.parse_args()
    if not 20<=args.phase_seconds<=60:p.error('phase-seconds must be 20..60 (three bounded phases)')
    devices=subprocess.check_output(['adb','devices'],text=True)
    available=[line.split()[0] for line in devices.splitlines() if line.endswith('\tdevice')]
    serial=args.serial or (available[0] if len(available)==1 else None)
    if serial not in available:raise RuntimeError('Select exactly one authorized ADB device')
    d=Device(serial);out=private_output(args.output)
    target=json.loads(args.target_id_file.read_text())['uas_id'] if args.target_id_file else None
    if args.include_forced_doze:
        battery=d.shell('dumpsys','battery');idle=d.shell('dumpsys','deviceidle')
        if 'UPDATES STOPPED' in battery or 'mForceIdle=true' in idle:raise RuntimeError('Existing battery/idle simulation left untouched')
    if 'ServiceRecord{' in d.shell('dumpsys','activity','services',PKG):
        raise RuntimeError('Existing receiver left untouched; stop it before this test')
    original_awake='mWakefulness=Awake' in d.shell('dumpsys','power')
    plan=dict(source_kind='controlled_test_beacon_expected_not_started_by_script' if args.source_kind=='controlled' else 'ambient_wifi_no_controlled_transmitter',
        completion='running',phases=[],rf_angle_accuracy='NOT_TESTED',original_screen_awake=original_awake)
    def save():
        (out/'plan.json').write_text(json.dumps(plan,indent=2)+'\n');(out/'plan.json').chmod(0o600)
    def copy_db(name):
        paths=d.shell('run-as',PKG,'find','files/captures/database','-type','f').splitlines()
        paths=[p for p in paths if p=='files/captures/database/observations.sqlite' or
               re.fullmatch(r'files/captures/database/segments/segment-[0-9]{6}-[a-f0-9-]+\.sqlite',p)]
        snapshot=out/(name+'-sources');snapshot.mkdir(mode=0o700)
        sources=[]
        for i,path in enumerate(sorted(paths)):
            data=d.run('exec-out','run-as',PKG,'cat',path,binary=True)
            f=snapshot/(str(i)+'.sqlite')
            fd=os.open(f,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
            with os.fdopen(fd,'wb') as stream:stream.write(data)
            sources.append((path,f))
        merge_database_snapshots(sources,out/name)
    def store(name,data):
        fd=os.open(out/name,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        with os.fdopen(fd,'wb') as stream:stream.write(data)
    copy_db('before.sqlite');started=False;recording=False;run=None;doze_requested=False;save()
    ui_dir=d.ui_path[:-4]
    try:
        d.shell('mkdir','-m','700',ui_dir);d.ui_path=ui_dir+'/screen.xml'
        prefs=ET.fromstring(d.shell('run-as',PKG,'cat','shared_prefs/receiver.xml'))
        previous=next((n.text for n in prefs.findall('string') if n.get('name')=='last_run'),None)
        wake_app(d)
        time.sleep(1);tap_enabled(d,'受信開始');started=True;tap_enabled(d,'記録開始');recording=True
        run=read_run(d,previous)
        names=['foreground','home_screen','screen_off']+(['forced_doze'] if args.include_forced_doze else [])
        for name in names:
            if name=='home_screen':d.shell('input','keyevent','KEYCODE_HOME')
            if name=='screen_off':d.shell('input','keyevent','KEYCODE_SLEEP')
            if name=='forced_doze':
                doze_requested=True
                d.shell('dumpsys','battery','unplug');response=d.shell('dumpsys','deviceidle','force-idle')
                idle=d.shell('dumpsys','deviceidle');plan['forced_doze_response']=response;plan['forced_doze_state_verified']=doze_verified(idle)
                if not plan['forced_doze_state_verified']:raise RuntimeError('Deep idle could not be verified; not a successful Doze test')
            phase=dict(name=name,start_us=d.time_us(),samples=[]);plan['phases'].append(phase);save()
            until=time.monotonic()+args.phase_seconds
            while time.monotonic()<until:
                service=d.shell('dumpsys','activity','services',PKG)
                memory=d.shell('dumpsys','meminfo',PKG)
                phase['samples'].append(dict(us=d.time_us(),foreground_service='isForeground=true' in service,
                    awake='mWakefulness=Awake' in d.shell('dumpsys','power'),deep_idle=doze_verified(d.shell('dumpsys','deviceidle')),pss_kib=pss_kib(memory)))
                save();time.sleep(min(5,max(0,until-time.monotonic())))
            phase['end_us']=d.time_us();save();print(name+' completed',flush=True)
        plan['completion']='phases_completed'
    except (Exception,KeyboardInterrupt) as exc:
        plan.update(completion='failed_or_interrupted',error_type=type(exc).__name__);raise
    finally:
        if doze_requested:
            try:
                d.shell('dumpsys','deviceidle','unforce');d.shell('dumpsys','battery','reset');plan['forced_doze_cleanup']='unforce_and_battery_reset'
            except Exception as exc:plan['forced_doze_cleanup']='UNCONFIRMED_'+type(exc).__name__
        if started:
            try:
                wake_app(d);time.sleep(1)
                if recording:
                    try:tap_enabled(d,'記録停止',timeout=8)
                    except Exception:plan['recording_stop_warning']='button_unavailable_receiver_stop_still_attempted'
                tap_enabled(d,'受信停止');time.sleep(2)
                if 'ServiceRecord{' in d.shell('dumpsys','activity','services',PKG):raise RuntimeError('Receiver stop unconfirmed')
                copy_db('after.sqlite');plan['cleanup']='stopped_by_ui'
                if run:
                    for name in ['observations.jsonl','events.jsonl','summary.csv']:
                        store(name,d.run('exec-out','run-as',PKG,'cat',f'files/captures/{run}/{name}',binary=True))
                d.shell('am','force-stop',PKG);d.shell('am','start','-n',PKG+'/.MainActivity');time.sleep(1)
                copy_db('restarted.sqlite')
                result=analyze_database(out/'before.sqlite',out/'after.sqlite',[p for p in plan['phases'] if 'end_us' in p],target_id=target)
                with sqlite3.connect(out/'after.sqlite') as a,sqlite3.connect(out/'restarted.sqlite') as b:
                    result['all_rows_unchanged_after_restart']=a.execute('select * from observations order by id').fetchall()==b.execute('select * from observations order by id').fetchall()
                store('validation.json',(json.dumps(result,indent=2)+'\n').encode())
                print(json.dumps(result),flush=True)
            except Exception as exc:
                plan.update(cleanup='unconfirmed_check_device',cleanup_error_type=type(exc).__name__)
        try:
            d.shell('rm','-f',d.ui_path);d.shell('rmdir',ui_dir)
        except Exception:pass
        if not original_awake:
            try:d.shell('input','keyevent','KEYCODE_SLEEP')
            except Exception:pass
        save()
    if plan.get('cleanup')!='stopped_by_ui':raise RuntimeError('Stop/cleanup unconfirmed; inspect private plan')


if __name__=='__main__':
    os.umask(0o077)
    main()
