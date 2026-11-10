#!/usr/bin/env python3
"""Bounded, resumable-evidence ADB experiment. Never changes scan throttling or grants permissions.
Start a suitable controlled RF source separately. This script does not emit RF.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid
import xml.etree.ElementTree as ET

PKG = 'org.smri.ridobserver.kmp'
ROOT = Path(__file__).resolve().parents[3]


class Device:
    def __init__(self, serial):
        self.prefix = ['adb', '-s', serial]
        self.ui_path = '/data/local/tmp/rid-eval-'+uuid.uuid4().hex+'.xml'
    def run(self, *args, binary=False):
        r = subprocess.run(self.prefix+list(args), capture_output=True, timeout=25)
        if r.returncode:
            raise RuntimeError('ADB operation failed; private output retained, check device connection')
        return r.stdout if binary else r.stdout.decode()
    def shell(self, *args):
        return self.run('shell', *args)
    def time_us(self):
        return int(float(self.shell('cat','/proc/uptime').split()[0])*1e6)
    def tap(self, label):
        self.shell('uiautomator','dump', self.ui_path)
        tree = ET.fromstring(self.shell('cat',self.ui_path))
        for n in tree.iter('node'):
            if n.get('text') == label:
                x1,y1,x2,y2 = map(int,re.findall(r'\d+',n.get('bounds','')))
                self.shell('input','tap',str((x1+x2)//2),str((y1+y2)//2))
                return
        raise RuntimeError('Required UI control unavailable; unlock phone and pre-grant app permissions in Settings')
    def runs(self):
        output = self.shell('run-as',PKG,'ls','files/captures')
        return set(re.findall(r'(?m)^[0-9a-f-]{36}$',output))
    def copy(self, run, name, dest):
        data = self.run('exec-out','run-as',PKG,'cat',f'files/captures/{run}/{name}',binary=True)
        fd = os.open(dest,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'wb') as f: f.write(data)


def private_output(path):
    path = Path(os.path.abspath(path))
    if not any(path.is_relative_to(ROOT/p) for p in ['captures','uav/captures']):
        raise ValueError('output must be under repository captures/')
    parent = ROOT
    for part in path.relative_to(ROOT).parts:
        parent = parent/part
        if parent.is_symlink():raise ValueError('symlink output rejected')
        if parent == path:
            parent.mkdir(mode=0o700,exist_ok=False)
        else:
            parent.mkdir(mode=0o700,exist_ok=True)
        if parent.stat().st_mode & 0o077:raise ValueError('capture directories must be owner-only')
    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--serial')
    parser.add_argument('--phase-seconds',type=int,default=1800)
    parser.add_argument('--source-kind',required=True,choices=['test_beacon','real_drone','unknown'])
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if not 30 <= args.phase_seconds <= 7200:parser.error('phase-seconds must be 30..7200')
    devices=subprocess.check_output(['adb','devices','-l'],text=True)
    candidates=[l.split()[0] for l in devices.splitlines() if ' device ' in l and 'model:Pixel_8 ' in l]
    serial=args.serial or (candidates[0] if len(candidates)==1 else None)
    if serial not in candidates:raise RuntimeError('Exactly one selected, authorized Pixel 8 is required')
    device=Device(serial)
    output=private_output(args.output)
    # These prerequisites are verified, never silently granted or weakened.
    package=device.shell('dumpsys','package',PKG)
    for permission in ['ACCESS_FINE_LOCATION','POST_NOTIFICATIONS']:
        if not re.search(r'android.permission.'+permission+r': granted=true',package):
            raise RuntimeError('Grant precise location and notifications to the app before running')
    throttle=device.shell('settings','get','global','wifi_scan_throttle_enabled').strip()
    if throttle=='0':raise RuntimeError('Wi-Fi scan throttling is disabled; restore normal settings before baseline evaluation')
    plan={'source_type':'real_capture','source_kind':args.source_kind,'radio_transmitter_started_by_script':False,
          'phase_seconds_requested':args.phase_seconds,'scan_throttle_setting':throttle,
          'adb_additional_scan_requests':False,'os_release':device.shell('getprop','ro.build.version.release').strip(),
          'sdk':device.shell('getprop','ro.build.version.sdk').strip(),'phases':[],
          'completion':'running','stop_method':'Activity buttons; notification-stop tested separately'}
    planfile=output/'phases.json'
    def save():
        fd=os.open(planfile,os.O_CREAT|os.O_WRONLY|os.O_TRUNC,0o600)
        with os.fdopen(fd,'w') as f:json.dump(plan,f,indent=2);f.write('\n')
    save();recording_started=False;started_by_script=False
    try:
        device.shell('input','keyevent','KEYCODE_WAKEUP')
        device.shell('am','start','-n',PKG+'/.MainActivity')
        time.sleep(1)
        # Do not steal a pre-existing capture or force-stop the application.
        device.tap('受信開始');started_by_script=True;time.sleep(2)
        device.tap('記録開始');recording_started=True;time.sleep(1)
        run_text=device.shell('run-as',PKG,'cat','shared_prefs/receiver.xml')
        m=re.search(r'<string name="last_run">([0-9a-f-]{36})</string>',run_text)
        if not m:raise RuntimeError('Capture run was not created')
        run=m.group(1)
        print('Experiment started: foreground / background / screen_off; private evidence is saved incrementally.',flush=True)
        for name in ['foreground','background','screen_off']:
            if name=='background':device.shell('input','keyevent','KEYCODE_HOME')
            if name=='screen_off':device.shell('input','keyevent','KEYCODE_SLEEP')
            phase={'name':name,'start_us':device.time_us(),'end_us':device.time_us(),'finished':False}
            plan['phases'].append(phase);save()
            deadline=time.monotonic()+args.phase_seconds
            while time.monotonic()<deadline:
                time.sleep(min(15,max(0,deadline-time.monotonic())))
                phase['end_us']=device.time_us();save()
                # Persist host copies even if a later USB connection fails.
                for file in ['observations.jsonl','events.jsonl']:
                    tmp=output/(file+'.partial')
                    data=device.run('exec-out','run-as',PKG,'cat',f'files/captures/{run}/{file}',binary=True)
                    fd=os.open(tmp,os.O_CREAT|os.O_WRONLY|os.O_TRUNC,0o600)
                    with os.fdopen(fd,'wb') as f:f.write(data)
            phase['finished']=True;save();print(name+' completed',flush=True)
        plan['completion']='phases_completed'
    except (Exception,KeyboardInterrupt) as exc:
        plan['completion']='failed_or_interrupted';plan['error_type']=type(exc).__name__
        raise
    finally:
        try:
            if not started_by_script:raise RuntimeError('No receiver started by this script; existing session left untouched')
            device.shell('input','keyevent','KEYCODE_WAKEUP')
            device.shell('am','start','-n',PKG+'/.MainActivity');time.sleep(1)
            if recording_started:device.tap('記録停止')
            device.tap('受信停止')
            plan['cleanup']='stopped_by_ui'
            if recording_started:
                for name in ['observations.jsonl','events.jsonl','summary.csv']:
                    device.copy(run,name,output/name)
        except Exception:
            plan['cleanup']='unconfirmed_check_device_notification_and_stop_manually'
        save()
        try:device.shell('rm',device.ui_path)
        except Exception:pass
    print('Evaluation finished. Run analyze_capture.py on this capture directory.',flush=True)

if __name__=='__main__':
    try:main()
    except Exception as exc:
        print(f'Evaluation not completed: {type(exc).__name__}: {exc}',file=sys.stderr)
        sys.exit(2)
