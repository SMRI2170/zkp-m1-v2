#!/usr/bin/env python3
"""Explicit Pi study Beacon transmitter with live sensor snapshots, no invented coordinates."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time
import uuid
from flight_payload import build_ie
from start_marker import load_marker
from flight_sensors import atomic_json


def run(command):return subprocess.run(command,check=True,capture_output=True,text=True,timeout=8).stdout


def choose_channel(info):
    match=re.search(r'channel (\d+) \((\d+) MHz\)',info)
    if match:
        channel,freq=map(int,match.groups())
        if not 1<=channel<=13 or not 2412<=freq<=2472:raise ValueError('associated station must be 2.4GHz; no station channel changes')
        return channel,freq,'existing_radio_channel'
    return 6,2437,'standalone_default_no_reported_station_channel'


def read_snapshot(path):
    try:
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
        with os.fdopen(fd) as f:
            stat=os.fstat(f.fileno())
            if stat.st_uid!=os.getuid() or stat.st_mode&0o077 or stat.st_size>16384:raise ValueError('unsafe sensor snapshot')
            return json.load(f)
    except FileNotFoundError:return None


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--marker',type=Path,required=True)
    p.add_argument('--sensor',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--runtime',type=Path,required=True);p.add_argument('--duration',type=float,default=60)
    p.add_argument('--continuous',action='store_true');p.add_argument('--interval',type=float,default=.2)
    a=p.parse_args()
    if not .1<=a.interval<=1 or not 1<=a.duration<=3600:p.error('bounded duration 1..3600, interval .1..1')
    marker=load_marker(a.marker);os.umask(0o077)
    for directory in [a.output,a.runtime]:
        directory.mkdir(mode=0o700,parents=True,exist_ok=True)
        if directory.is_symlink() or directory.stat().st_mode&0o077:raise ValueError('owner-private directories required')
    if Path('/sys/class/net/ridtx0').exists():raise ValueError('ridtx0 already exists; retained for inspection')
    if subprocess.run(['pgrep','-x','hostapd'],stdout=subprocess.DEVNULL).returncode==0:raise ValueError('existing hostapd retained')
    iw='/usr/sbin/iw';ip='/usr/sbin/ip'
    link=run([iw,'dev','wlan0','link'])
    for _ in range(20):
        if 'Connected to ' in link:break
        time.sleep(.5);link=run([iw,'dev','wlan0','link'])
    info=run([iw,'dev','wlan0','info']) if 'Connected to ' in link else ''
    channel,frequency,channel_basis=choose_channel(info)
    stop=False
    def request_stop(*_):
        nonlocal stop
        stop=True
    for sig in [signal.SIGTERM,signal.SIGINT]:signal.signal(sig,request_stop)
    created=False;process=None;file=None;log=None;failed=False;sequence=0;started=time.monotonic();next_tick=started;file_started=0;next_budget=started
    status=dict(state='PREPARING',frequency_mhz=None,channel=None,configured_frequency_mhz=frequency,configured_channel=channel,channel_basis=channel_basis,
        configured_beacon_interval_tu=100,configured_payload_interval_s=a.interval,
        identity_verified=False,physical_packet_match='unconfirmed',temporary_ap_removed=False)
    atomic_json(a.output/'status.json',status)
    try:
        run([iw,'dev','wlan0','interface','add','ridtx0','type','__ap']);created=True
        time.sleep(1)
        run([ip,'link','set','ridtx0','down']);run([iw,'dev','ridtx0','set','type','__ap'])
        run([ip,'link','set','ridtx0','address',marker['tx_mac']]);run([ip,'link','set','ridtx0','up'])
        ie,_=build_ie(marker['uas_id'],0,None,time.monotonic())
        accept=a.runtime/'accept-macs';accept.write_text('')
        config='\n'.join(['interface=ridtx0','driver=nl80211','country_code=JP','ssid=PI-RID-RESEARCH',
            'hw_mode=g','channel='+str(channel),'beacon_int=100','ieee80211n=1','wmm_enabled=1',
            'auth_algs=1','macaddr_acl=1','accept_mac_file='+str(accept),'ctrl_interface='+str(a.runtime/'ctrl'),
            'vendor_elements='+ie.hex(),''])
        conf=a.runtime/'hostapd.conf';conf.write_text(config)
        log=(a.runtime/'hostapd.log').open('w')
        process=subprocess.Popen(['/usr/sbin/hostapd',str(conf)],stdout=log,stderr=subprocess.STDOUT)
        for _ in range(60):
            if process.poll() is not None:raise RuntimeError('hostapd startup failed; see private runtime log')
            if (a.runtime/'ctrl/ridtx0').exists():break
            if stop:raise RuntimeError('stopped before AP ready')
            time.sleep(.2)
        else:raise RuntimeError('hostapd control socket unavailable')
        actual=run([iw,'dev','ridtx0','info'])
        if not re.search(r'^\s*type AP\s*$',actual,re.M):raise RuntimeError('kernel AP mode missing')
        m=re.search(r'channel (\d+) \((\d+) MHz\)',actual)
        if m:status.update(channel=int(m[1]),frequency_mhz=int(m[2]),frequency_basis='kernel_interface_info_not_RF_analyzer')
        next_radio_check=time.monotonic()+1
        status['state']='TRANSMITTING';atomic_json(a.output/'status.json',status)
        while not stop and (a.continuous or time.monotonic()-started<a.duration):
            now=time.monotonic()
            if process.poll() is not None:raise RuntimeError('hostapd exited')
            if now>=next_radio_check:
                actual=run([iw,'dev','ridtx0','info']);m=re.search(r'channel (\d+) \((\d+) MHz\)',actual)
                if m:status.update(channel=int(m[1]),frequency_mhz=int(m[2]))
                next_radio_check=now+1
            if now>=next_budget:
                files=[f for f in a.output.rglob('*') if f.is_file()]
                if sum(f.stat().st_size for f in files)>128*1024**2 or len(files)>10000 or shutil.disk_usage(a.output).free<512*1024**2:raise RuntimeError('TX capture budget/headroom reached')
                next_budget=now+10
            sensor=read_snapshot(a.sensor);ie,meta=build_ie(marker['uas_id'],sequence,sensor,now)
            response=run(['/usr/sbin/hostapd_cli','-p',str(a.runtime/'ctrl'),'-i','ridtx0','set','vendor_elements',ie.hex()])
            if not response.strip() or response.strip().splitlines()[-1]!='OK':raise RuntimeError('hostapd payload update rejected')
            response=run(['/usr/sbin/hostapd_cli','-p',str(a.runtime/'ctrl'),'-i','ridtx0','update_beacon'])
            if not response.strip() or response.strip().splitlines()[-1]!='OK':raise RuntimeError('hostapd beacon application rejected')
            if file is None or now-file_started>=60:
                if file:file.close()
                fd=os.open(a.output/('sent-'+uuid.uuid4().hex+'.jsonl'),os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
                file=os.fdopen(fd,'w',buffering=1);file_started=now
            file.write(json.dumps(dict(sequence=sequence,host_monotonic_s=now,sensor_sequence=sensor.get('sequence') if sensor else None,sensor_session=sensor.get('sensor_session') if sensor else None,
                vendor_ie_hex=ie.hex(),vendor_content_digest=hashlib.sha256(ie[2:]).hexdigest(),**meta))+'\n');file.flush()
            status.update(state='TRANSMITTING',updates=sequence+1,**meta);atomic_json(a.output/'status.json',status)
            sequence+=1;next_tick+=a.interval;time.sleep(max(0,next_tick-time.monotonic()))
    except Exception as exc:
        failed=True;status['error_type']=type(exc).__name__;raise
    finally:
        if file:file.close()
        if process:
            process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill();process.wait()
        if log:log.close()
        if created:
            result=subprocess.run([iw,'dev','ridtx0','del'],capture_output=True,text=True,timeout=8)
            status['temporary_ap_removed']=result.returncode==0
        status['state']='FAILED' if failed else 'STOPPED';status['updates']=sequence;atomic_json(a.output/'status.json',status)


if __name__=='__main__':main()
