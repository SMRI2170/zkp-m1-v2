#!/usr/bin/env python3
"""Explicitly installed boot receiver. Bounded segments, private storage, no RF transmitter."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'uav'))
from wifi_beacon_capture import private_output
from run_observer import read_config


def capacity(root,mem_kib,disk_free,used_bytes,files):
    # Reserve worst-case 3 x 20MiB + metadata for the NEXT segment.
    if mem_kib<192*1024:return 'MEMORY_HEADROOM_LOW'
    if disk_free<512*1024**2:return 'DISK_HEADROOM_LOW'
    if used_bytes+64*1024**2>256*1024**2:return 'CAPTURE_BUDGET_REACHED'
    if files>=10000:return 'CAPTURE_FILE_BUDGET_REACHED'
    return None


def usage(root):
    total=count=0
    for p in root.rglob('*'):
        if p.is_symlink():raise ValueError('symlink in capture archive')
        if p.is_file():total+=p.stat().st_size;count+=1
    return total,count


def unit_text(root,base,user):
    # Installer accepts only the standard versioned Pi layout, no shell substitutions.
    for p in [root,base]:
        if not str(p).startswith('/home/'+user+'/zkp-beacon-observer') or any(c in str(p) for c in ' \n%"'):
            raise ValueError('unsafe service path')
    return f'''[Unit]
Description=Remote ID research scan receiver (no transmitter)
Wants=network-online.target
After=network-online.target
StartLimitIntervalSec=300
StartLimitBurst=3

[Service]
Type=simple
User={user}
Group={user}
UMask=0077
Environment=PYTHONDONTWRITEBYTECODE=1
ExecStart=/usr/bin/python3 {root}/experiments/week28-beacon-observers/boot_observer.py --config {base}/config/node.json
Restart=on-failure
RestartSec=30
RestartPreventExitStatus=78
KillMode=mixed
TimeoutStopSec=95
MemoryMax=160M
CPUQuota=50%
TasksMax=32
Nice=10
NoNewPrivileges=true
AmbientCapabilities=CAP_NET_ADMIN
CapabilityBoundingSet=CAP_NET_ADMIN
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths={root}/captures
PrivateTmp=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
'''


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path,required=True)
    p.add_argument('--segments',type=int,default=0,help='test-only finite segment count; 0 is continuous boot reception')
    p.add_argument('--segment-seconds',type=int,default=60)
    a=p.parse_args()
    if not 10<=a.segment_seconds<=300 or a.segments<0:p.error('segment duration 10..300, segments >=0')
    os.umask(0o077);cfg=read_config(a.config)
    if os.getuid()==0:raise ValueError('receiver must run as ordinary observer user')
    archive=ROOT/'captures';archive.mkdir(mode=0o700,exist_ok=True)
    if archive.is_symlink() or archive.stat().st_uid!=os.getuid() or archive.stat().st_mode&0o077:
        raise ValueError('owner-only capture archive required')
    lock=open(archive/'.boot-observer.lock','a');os.chmod(lock.name,0o600)
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    stop=threading.Event()
    for sig in [signal.SIGTERM,signal.SIGINT]:signal.signal(sig,lambda *_:stop.set())
    def status(state,**extra):
        tmp=archive/('.boot-status-'+uuid.uuid4().hex+'.tmp');target=archive/'boot-status.json'
        # New names preserve interrupted writes without blocking the next boot.
        with private_output(tmp) as f:
            json.dump(dict(state=state,segments=completed,source_type='real_capture',
                observation_kind='linux_scan_cache',physical_packet_match='unconfirmed',**extra),f);f.write('\n');f.flush();os.fsync(f.fileno())
        tmp.replace(target)
        print(json.dumps(dict(state=state,segments=completed)),flush=True)
    completed=failures=0
    status('STARTING')
    try:
        while not stop.is_set() and (a.segments==0 or completed<a.segments):
            mem=dict(line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())
            size,files=usage(archive)
            reason=capacity(archive,int(mem['MemAvailable'].split()[0]),shutil.disk_usage(archive).free,size,files)
            if reason:status(reason);return 78
            interface=Path('/sys/class/net')/cfg['interface']/'operstate'
            if not interface.exists() or interface.read_text().strip()!='up':
                status('WAITING_FOR_NETWORK');stop.wait(15);continue
            status('RECEIVING',segment_seconds=a.segment_seconds,scan_request_interval_s=1)
            cmd=[sys.executable,str(ROOT/'experiments/week28-beacon-observers/run_observer.py'),
                 '--config',str(a.config),'--duration',str(a.segment_seconds),'--interval','0.25','--active-scan','--scan-interval','1']
            # Existing wrapper retains raw errors/metadata owner-private. Never emit them to journal.
            child=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            try:stdout,stderr=child.communicate(timeout=a.segment_seconds+25)
            except subprocess.TimeoutExpired:
                child.terminate()
                try:child.communicate(timeout=5)
                except subprocess.TimeoutExpired:child.kill();child.communicate()
                status('SEGMENT_TIMEOUT');return 2
            completed+=1
            try:summary=json.loads(stdout)
            except json.JSONDecodeError:summary={}
            counts=(summary.get('capture') or {}).get('counts') or {}
            status('SEGMENT_COMPLETE',exit_code=child.returncode,records=counts.get('odid_records'),
                   fresh_records=counts.get('fresh_decoded_records'))
            if child.returncode not in [0,3]:
                failures+=1
                if failures>=3:status('REPEATED_CAPTURE_FAILURE');return 2
                stop.wait(15)
            else:failures=0
    finally:status('STOPPED') if stop.is_set() else None
    if not stop.is_set():status('FINITE_TEST_COMPLETE')
    return 0


if __name__=='__main__':raise SystemExit(main())
