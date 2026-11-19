#!/usr/bin/env python3
"""Read recorder heartbeats. Optional ACT LED reports recorder health, never RID validity."""
import argparse
import json
import os
from pathlib import Path
import re
import signal
import time
from capture_storage import boot_id

DIRS={'receiver':'receiver','sensors':'flight-sensors','transmitter':'flight-tx'}
PATTERNS={'ACTIVE':(900,900),'WAITING':(100,1900),'FAULT':(100,100)}
def health(root,roles,*,now=None,boot=None):
    now=time.monotonic() if now is None else now;boot=boot_id() if boot is None else boot
    details={};overall='ACTIVE'
    for role in roles:
        try:
            p=Path(root)/DIRS[role]/'storage-status.json'
            if p.is_symlink() or p.stat().st_size>16384:raise ValueError('unsafe status')
            o=json.loads(p.read_text());age=now-o['updated_monotonic_s'];state=o['state'];reason=None
            if boot=='unknown' or o['boot_id']=='unknown':reason='BOOT_ID_UNAVAILABLE'
            elif o['boot_id']!=boot:reason='PREVIOUS_BOOT'
            elif not 0<=age<=(120 if role=='receiver' else 30):reason='HEARTBEAT_STALE'
            elif state not in ['STARTING','CAPTURE_ACTIVE']:reason=state
            elif state=='STARTING':reason='STARTING'
            elif role!='receiver' and (o.get('last_record_monotonic_s') is None or not 0<=now-o['last_record_monotonic_s']<=15):reason='NO_RECENT_WRITE'
            elif role=='receiver' and not o.get('records_written'):reason='WAITING_FOR_OBSERVATIONS'
            phase='ACTIVE' if reason is None else 'WAITING' if reason in ['STARTING','WAITING_FOR_OBSERVATIONS'] else 'FAULT'
            details[role]=dict(phase=phase,reason=reason,records_written=o.get('records_written',0),heartbeat_age_s=round(age,2),session_bytes=o.get('session_bytes'),byte_budget=o.get('byte_budget'))
        except (OSError,ValueError,TypeError,KeyError):phase='FAULT';details[role]=dict(phase=phase,reason='STATUS_UNAVAILABLE')
        if phase=='FAULT':overall='FAULT'
        elif phase=='WAITING' and overall!='FAULT':overall='WAITING'
    return dict(schema='capture_health_v1',phase=overall,roles=details,meaning='recorder_status_not_aircraft_or_sensor_authentication')

def led_path(value):
    p=Path(value)
    if p.parent!=Path('/sys/class/leds') or p.name not in ['ACT','led0']:raise ValueError('only the activity LED may be used')
    triggers=(p/'trigger').read_text()
    if 'timer' not in triggers.split():raise ValueError('timer LED trigger unavailable')
    m=re.search(r'\[([^]]+)\]',triggers)
    if not m:raise ValueError('original LED trigger missing')
    return p,m[1]

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--roles',nargs='+',choices=list(DIRS),default=['receiver']);p.add_argument('--led');p.add_argument('--duration',type=float,default=0);a=p.parse_args()
    if a.duration<0:p.error('duration >= 0 required')
    if not a.led:
        print(json.dumps(health(a.root,a.roles)));return
    led,original=led_path(a.led);stop=False
    def request(*_):
        nonlocal stop;stop=True
    for s in [signal.SIGTERM,signal.SIGINT]:signal.signal(s,request)
    start=time.monotonic();previous=None
    try:
        while not stop and (a.duration==0 or time.monotonic()-start<a.duration):
            o=health(a.root,a.roles)
            if o['phase']!=previous:
                (led/'trigger').write_text('timer');on,off=PATTERNS[o['phase']]
                (led/'delay_on').write_text(str(on));(led/'delay_off').write_text(str(off));print(json.dumps(o),flush=True);previous=o['phase']
            time.sleep(1)
    finally:(led/'trigger').write_text(original)
if __name__=='__main__':main()
