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


def pss_kib(text):
    for pattern in [r'(?m)^\s*TOTAL PSS:\s*(\d+)', r'(?m)^\s*TOTAL\s+(\d+)']:
        m=re.search(pattern,text)
        if m:return int(m.group(1))
    return None


def phase_counts(rows,start,end):
    # 100ms guard band around coarse /proc/uptime boundaries; never count cached/stale as fresh.
    selected=[r for r in rows if r.get('monotonic_time_us') is not None and
              start+100_000 <= r['monotonic_time_us'] < end-100_000]
    return dict(scan_records=len(selected),fresh_records=sum(not r['cache_stale'] for r in selected),
                heading_matched_records=sum((r.get('direction') or {}).get('missing_reason') is None
                    and (r.get('direction') or {}).get('phone_heading_magnetic_deg') is not None for r in selected))


def analyze_database(before,after,phases):
    with sqlite3.connect(before) as a,sqlite3.connect(after) as b:
        old=a.execute('select * from observations order by id').fetchall()
        old_ids={r[0] for r in old}
        current=b.execute('select * from observations order by id').fetchall()
        current_by_id={r[0]:r for r in current}
        same=all(current_by_id.get(r[0])==r for r in old)
        rows=[json.loads(raw) for id_,raw in b.execute('select id,raw_json from observations order by id') if id_ not in old_ids]
        result=dict(old_rows=len(old),total_rows=len(current),new_rows=len(rows),old_rows_unchanged=same,
                    integrity_check=b.execute('pragma integrity_check').fetchone()[0],
                    fresh_rows=sum(not r['cache_stale'] for r in rows),
                    raw_text_rows=b.execute("select count(*) from observations where text_line like '%raw_vendor_ie_hex=%'").fetchone()[0],
                    phases=[])
        for phase in phases:
            samples=[x['pss_kib'] for x in phase['samples'] if x['pss_kib'] is not None]
            result['phases'].append(dict(name=phase['name'],duration_s=(phase['end_us']-phase['start_us'])/1e6,
                foreground_service_all_samples=all(x['foreground_service'] for x in phase['samples']),
                samples=len(phase['samples']),pss_samples=len(samples),pss_mean_kib=sum(samples)/len(samples) if samples else None,
                pss_max_kib=max(samples) if samples else None,**phase_counts(rows,phase['start_us'],phase['end_us'])))
        return result


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
    args=p.parse_args()
    if not 20<=args.phase_seconds<=60:p.error('phase-seconds must be 20..60 (three bounded phases)')
    devices=subprocess.check_output(['adb','devices'],text=True)
    available=[line.split()[0] for line in devices.splitlines() if line.endswith('\tdevice')]
    serial=args.serial or (available[0] if len(available)==1 else None)
    if serial not in available:raise RuntimeError('Select exactly one authorized ADB device')
    d=Device(serial);out=private_output(args.output)
    if 'ServiceRecord{' in d.shell('dumpsys','activity','services',PKG):
        raise RuntimeError('Existing receiver left untouched; stop it before this test')
    original_awake='mWakefulness=Awake' in d.shell('dumpsys','power')
    plan=dict(source_kind='controlled_test_beacon_expected_not_started_by_script',
        completion='running',phases=[],rf_angle_accuracy='NOT_TESTED',original_screen_awake=original_awake)
    def save():
        (out/'plan.json').write_text(json.dumps(plan,indent=2)+'\n');(out/'plan.json').chmod(0o600)
    def copy_db(name):
        data=d.run('exec-out','run-as',PKG,'cat','files/captures/database/observations.sqlite',binary=True)
        f=out/name
        fd=os.open(f,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        with os.fdopen(fd,'wb') as stream:stream.write(data)
    def store(name,data):
        fd=os.open(out/name,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        with os.fdopen(fd,'wb') as stream:stream.write(data)
    copy_db('before.sqlite');started=False;recording=False;run=None;save()
    ui_dir=d.ui_path[:-4]
    try:
        d.shell('mkdir','-m','700',ui_dir);d.ui_path=ui_dir+'/screen.xml'
        prefs=ET.fromstring(d.shell('run-as',PKG,'cat','shared_prefs/receiver.xml'))
        previous=next((n.text for n in prefs.findall('string') if n.get('name')=='last_run'),None)
        wake_app(d)
        time.sleep(1);tap_enabled(d,'受信開始');started=True;tap_enabled(d,'記録開始');recording=True
        run=read_run(d,previous)
        for name in ['foreground','home_screen','screen_off']:
            if name=='home_screen':d.shell('input','keyevent','KEYCODE_HOME')
            if name=='screen_off':d.shell('input','keyevent','KEYCODE_SLEEP')
            phase=dict(name=name,start_us=d.time_us(),samples=[]);plan['phases'].append(phase);save()
            until=time.monotonic()+args.phase_seconds
            while time.monotonic()<until:
                service=d.shell('dumpsys','activity','services',PKG)
                memory=d.shell('dumpsys','meminfo',PKG)
                phase['samples'].append(dict(us=d.time_us(),foreground_service='isForeground=true' in service,
                    awake='mWakefulness=Awake' in d.shell('dumpsys','power'),pss_kib=pss_kib(memory)))
                save();time.sleep(min(5,max(0,until-time.monotonic())))
            phase['end_us']=d.time_us();save();print(name+' completed',flush=True)
        plan['completion']='phases_completed'
    except (Exception,KeyboardInterrupt) as exc:
        plan.update(completion='failed_or_interrupted',error_type=type(exc).__name__);raise
    finally:
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
                result=analyze_database(out/'before.sqlite',out/'after.sqlite',plan['phases'])
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
