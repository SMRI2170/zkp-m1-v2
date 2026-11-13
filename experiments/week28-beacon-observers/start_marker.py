#!/usr/bin/env python3
"""Manually start a bounded, separate Pi study marker, without Location data."""
import argparse
import json
import os
from pathlib import Path
import stat
import sys
import uuid
from safe_beacon_tx import test_identity,validate_ie


def load_marker(path):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd) as f:
        s=os.fstat(f.fileno())
        if not stat.S_ISREG(s.st_mode) or s.st_uid!=os.getuid() or s.st_mode&0o077 or s.st_size>1024:
            raise ValueError('marker config must be owner-private <=1KiB')
        cfg=json.load(f)
    body=bytes.fromhex('fa0bbc0d')+bytes([1,0xf2,25,1,2])+bytes(24)
    test_identity(bytes([221,len(body)])+body,cfg['uas_id'],cfg['tx_mac'])
    if not cfg['uas_id'].startswith('PI-RID-'):raise ValueError('onboard study marker must use PI-RID-*')
    return cfg


def command(base,marker,duration):
    if not 1<=duration<=120:raise ValueError('marker duration must be 1..120 seconds')
    return ['sudo','systemd-run','--wait','--pipe','--collect','--unit=zkp-beacon-marker-'+uuid.uuid4().hex[:10],
            '--property=RuntimeMaxSec='+str(duration+25),'--property=MemoryMax=128M','--property=TimeoutStopSec=15',
            '/usr/bin/python3',str(base/'current/experiments/week28-beacon-observers/safe_beacon_tx.py'),
            '--ap','ap0','--beacon-only-compat','--run-id','marker-'+uuid.uuid4().hex[:10],
            '--counter','1','--id-only','--uas-id',marker['uas_id'],'--tx-mac',marker['tx_mac'],'--duration',str(duration)]


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--duration',type=int,default=60)
    p.add_argument('--show-config',action='store_true',help='show locally only; broadcast identifiers are private field configuration')
    args=p.parse_args()
    if os.getuid()==0:p.error('launch as the observer user; sudo is scoped to the bounded service')
    release=Path(__file__).resolve().parents[2];base=release.parent.parent
    if release.parent.name!='releases' or base.name!='zkp-beacon-observer':p.error('install versioned release first')
    try:
        marker=load_marker(base/'config/marker.json');cmd=command(base,marker,args.duration)
    except (ValueError,OSError,KeyError) as exc:p.error('cannot load marker configuration: '+type(exc).__name__)
    if args.show_config:print(json.dumps(marker));return 0
    os.execvp(cmd[0],cmd)


if __name__=='__main__':raise SystemExit(main())
