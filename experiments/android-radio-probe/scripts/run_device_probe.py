"""Install this app and save a bounded physical-device RF run in ignored captures/.

Raw data never goes into tracked results; do not print serials, MACs or SSIDs.
Use a single USB-connected device (`adb -d`). Permission grants are limited to
this newly installed package; no system scan-throttle/location toggles.
"""
import argparse
import csv
import io
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

PACKAGE='org.smri.ridprobe'
DEVICE=None


def adb(*args, binary=False):
    select=['-s',DEVICE] if DEVICE else ['-d']
    result=subprocess.run(['adb',*select,*args],capture_output=True,check=True)
    return result.stdout if binary else result.stdout.decode().strip()


def private_write(path, payload):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'wb') as f:f.write(payload if isinstance(payload,bytes) else payload.encode())


def main():
    global DEVICE
    p=argparse.ArgumentParser();p.add_argument('--apk',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--seconds',type=int,default=25)
    p.add_argument('--device',help='ADB wireless IP:port or explicit transport serial; never written to public summaries')
    args=p.parse_args();DEVICE=args.device
    if 'captures' not in args.output.parts:raise ValueError('Use ignored captures/ for raw RF data')
    if subprocess.run(['git','check-ignore','--quiet','--',str(args.output)]).returncode!=0:
        raise ValueError('Raw output must be ignored by Git')
    if not 5<=args.seconds<=45:raise ValueError('Bounded smoke run must be 5..45 seconds')
    args.output.mkdir(parents=True,exist_ok=False,mode=0o700);os.chmod(args.output,0o700)
    private_write(args.output/'apk-info.json',json.dumps(dict(sha256=hashlib.sha256(args.apk.read_bytes()).hexdigest(),size_bytes=args.apk.stat().st_size),indent=2))
    print('Installing dedicated RID Radio Probe APK',flush=True)
    adb('install','-r',str(args.apk))
    permissions=['ACCESS_COARSE_LOCATION','ACCESS_FINE_LOCATION','BLUETOOTH_SCAN','BLUETOOTH_CONNECT','NEARBY_WIFI_DEVICES','RANGING']
    grant_results={}
    for name in permissions:
        try:adb('shell','pm','grant',PACKAGE,'android.permission.'+name);grant_results[name]='granted'
        except subprocess.CalledProcessError:grant_results[name]='grant_failed'
    adb('shell','am','force-stop',PACKAGE)
    adb('shell','am','start','-W','-n',PACKAGE+'/.MainActivity','--ez','auto_start','true','--ei','duration_s',str(args.seconds))
    print(f'App launched; bounded reception test {args.seconds}s',flush=True)
    time.sleep(args.seconds+2)
    name=adb('shell','run-as',PACKAGE,'cat','files/latest-session.txt')
    if not name.startswith('run-') or '/' in name:raise ValueError('Unexpected private session name')
    summary=adb('shell','run-as',PACKAGE,'cat',f'files/sessions/{name}/summary.json')
    observations=adb('shell','run-as',PACKAGE,'cat',f'files/sessions/{name}/observations.jsonl',binary=True)
    private_write(args.output/'summary.json',summary)
    private_write(args.output/'observations.jsonl',observations)
    private_write(args.output/'permission-results.json',json.dumps(grant_results,indent=2))
    s=json.loads(summary)
    table=io.StringIO(newline='');columns=['target_alias','kind','rid_syntax','frequency_mhz','status','n','bins','coverage_deg','peak_phone_heading_magnetic_deg','amplitude_db','directional_r2','residual_sd_db','calibrated','bearing_magnetic_deg']
    writer=csv.DictWriter(table,fieldnames=columns);writer.writeheader()
    for target in s['targets']:
        row={k:target['estimate'].get(k) for k in columns}
        row.update(target_alias=target['alias'],kind=target['kind'],rid_syntax=target['rid_syntax'],frequency_mhz=target['frequency_mhz'])
        writer.writerow(row)
    private_write(args.output/'estimates.csv',table.getvalue())
    # Counts only; even per-run hashed target labels stay in private evidence.
    safe={key:s[key] for key in ('model','android','sdk','running','active_duration_s','wifi_scan_requests','wifi_scan_accepted','wifi_unique_scan_timestamps',
        'wifi_fresh_broadcasts','wifi_information_elements','wifi_vendor_elements','wifi_rid_observations',
        'ble_packets','ble_rid_observations','heading_count','rotation_samples','fitted_targets','errors')}
    print(json.dumps(safe,ensure_ascii=False,indent=2),flush=True)
    print('Raw summary and observations retained owner-only in ignored captures/.',flush=True)
    if s['active_duration_s']<=0:raise RuntimeError('App did not enter recording; retained launch diagnostics are not an RF reception pass')


if __name__=='__main__':main()
