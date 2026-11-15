#!/usr/bin/env python3
"""Bounded iw scan-contention experiments. Explicitly stop the managed receiver first.

This tool does not change connection, channel, driver, power-save or NetworkManager.
Raw iw event text is private. Events do not identify which process caused a scan.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import re
import signal
import statistics
import subprocess
import threading
import time


def event_kind(line, interface):
    if not re.search(r'\b'+re.escape(interface)+r'\s+\(phy #\d+\):',line):return None
    for text,kind in [('scan started','started'),('scan finished','finished'),('scan aborted','aborted')]:
        if text in line:return kind
    return None


def result_reason(code,stderr):
    if code==0:return 'accepted'
    text=stderr.lower()
    if 'busy' in text or '(-16)' in text:return 'busy'
    if any(x in text for x in ['not permitted','permission','password']):return 'permission'
    return 'driver_rejected'


def summarize(records):
    requests=[r for r in records if r['kind']=='request']
    busy=[r for r in requests if r['reason']=='busy']
    return dict(requests=len(requests),accepted=sum(r['reason']=='accepted' for r in requests),
                busy=len(busy),permission=sum(r['reason']=='permission' for r in requests),
                busy_fraction=len(busy)/len(requests) if requests else None,
                busy_while_scan_event_open=sum(r.get('scan_open_before',False) for r in busy),
                timeouts=sum(r.get('timed_out',False) for r in records if r['kind']=='wait'),
                event_aborts=sum(r['kind']=='aborted' for r in records))


class Probe:
    def __init__(self,interface,output):
        self.interface=interface;self.output=output;self.events=[];self.lock=threading.Lock()
        self.start=time.monotonic();self.scenario='startup';self.file=None;self.process=None

    def log(self,kind,**fields):
        with self.lock:
            row=dict(kind=kind,elapsed_s=time.monotonic()-self.start,scenario=self.scenario,**fields)
            self.events.append(row);self.file.write(json.dumps(row)+'\n');self.file.flush()
        return row

    def snapshot(self):
        with self.lock:return list(self.events)

    def scan_open(self):
        events=[r for r in self.snapshot() if r['kind'] in ['started','finished','aborted']]
        return bool(events and events[-1]['kind']=='started')

    def trigger(self,frequency,tag):
        before=self.scan_open();began=time.monotonic()-self.start
        command=['/usr/sbin/iw','dev',self.interface,'scan','trigger']
        if frequency is not None:command+=['freq',str(frequency)]
        try:
            r=subprocess.run(command,capture_output=True,text=True,timeout=2)
            reason=result_reason(r.returncode,r.stderr);code=r.returncode;error=r.stderr.strip()
        except subprocess.TimeoutExpired:reason='timeout';code=None;error='command timeout'
        return self.log('request',frequency_mhz=frequency,tag=tag,reason=reason,
                        returncode=code,stderr=error,scan_open_before=before,request_started_s=began)

    def wait_done(self,request,timeout=10):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            terminal=[r for r in self.snapshot() if r['kind'] in ['finished','aborted']
                      and r['elapsed_s']>=request['request_started_s']]
            if terminal:
                self.log('wait',tag=request['tag'],timed_out=False,terminal=terminal[0]['kind'],
                         duration_s=terminal[0]['elapsed_s']-request['request_started_s'])
                return terminal[0]['kind']=='finished'
            time.sleep(.02)
        self.log('wait',tag=request['tag'],timed_out=True,terminal=None,duration_s=timeout)
        return False

    def monitor(self):
        for line in self.process.stdout:
            kind=event_kind(line,self.interface)
            if kind:self.log(kind)
            # Entire event stream may contain MACs/SSIDs; it never goes to stdout/Git.
            with (self.output/'iw-events.txt').open('a') as f:f.write(line)

    def execute(self,frequency,repeats):
        self.file=(self.output/'events.jsonl').open('x',buffering=1)
        self.process=subprocess.Popen(['/usr/bin/stdbuf','-oL','/usr/sbin/iw','event','-t'],
                                      stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        thread=threading.Thread(target=self.monitor,daemon=True);thread.start()
        try:
            time.sleep(.3)
            if self.process.poll() is not None:raise RuntimeError('iw event monitor unavailable')
            self.scenario='idle';self.log('scenario_start');time.sleep(6)
            self.scenario='fixed_fast';self.log('scenario_start');end=time.monotonic()+12;failures=0
            while time.monotonic()<end:
                r=self.trigger(frequency,'fixed')
                if r['reason']=='permission':raise RuntimeError('permission denied')
                failures=0 if r['reason']=='accepted' else failures+1
                if failures>=5:raise RuntimeError('failure limit')
                time.sleep(.25 if not failures else min(5,2**(failures-1)))
            time.sleep(2)
            self.scenario='broad_probe';self.log('scenario_start')
            for i in range(repeats):
                r=self.trigger(None,'broad-'+str(i))
                if r['reason']!='accepted':self.log('trial_skipped',reason='broad_not_accepted');time.sleep(2);continue
                for delay in [.25,1,2]:
                    time.sleep(delay);q=self.trigger(frequency,'during-broad-'+str(i))
                    if q['reason']=='accepted':self.wait_done(q,3);break
                self.wait_done(r);time.sleep(.5)
            self.scenario='broad_wait';self.log('scenario_start')
            for i in range(repeats):
                r=self.trigger(None,'broad-wait-'+str(i))
                if r['reason']=='accepted' and self.wait_done(r):
                    q=self.trigger(frequency,'after-completion-'+str(i))
                    if q['reason']=='accepted':self.wait_done(q,3)
                else:self.log('trial_skipped',reason='broad_not_completed')
                time.sleep(.5)
            self.scenario='two_requesters';self.log('scenario_start')
            for i in range(repeats):
                with ThreadPoolExecutor(max_workers=2) as pool:
                    pair=list(pool.map(lambda j:self.trigger(frequency,'pair-'+str(i)+'-'+str(j)),[0,1]))
                for r in pair:
                    if r['reason']=='accepted':self.wait_done(r,3)
                time.sleep(.5)
            self.log('completed')
        finally:
            self.process.terminate()
            try:self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:self.process.kill();self.process.wait()
            thread.join(timeout=3)
            self.file.close()
        data=self.snapshot();out={s:summarize([r for r in data if r['scenario']==s])
                                 for s in ['idle','fixed_fast','broad_probe','broad_wait','two_requesters']}
        out['monitor']=dict(started=sum(r['kind']=='started' for r in data),
                            finished=sum(r['kind']=='finished' for r in data),
                            aborted=sum(r['kind']=='aborted' for r in data),
                            attribution='interface_events_not_process_ownership')
        (self.output/'summary.json').write_text(json.dumps(out,indent=2)+'\n')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--interface',default='wlan0');p.add_argument('--frequency',type=int,required=True)
    p.add_argument('--repeats',type=int,default=3);a=p.parse_args()
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,15}',a.interface) or not 2400<=a.frequency<=7125 or not 1<=a.repeats<=5:p.error('invalid bounded probe parameters')
    a.output=Path(os.path.abspath(a.output))
    if not any(x in ['captures'] for x in a.output.parts):p.error('private captures output required')
    if any(x.is_symlink() for x in [a.output,*a.output.parents]):p.error('symlink rejected')
    os.umask(0o077);a.output.mkdir(mode=0o700,parents=True,exist_ok=False)
    active=subprocess.run(['systemctl','is-active','zkp-rid-observer.service'],capture_output=True,text=True)
    if active.stdout.strip() in ['active','activating','deactivating']:raise RuntimeError('stop managed observer before probe')
    mem=Path('/proc/meminfo').read_text();available=int(re.search(r'^MemAvailable:\s+(\d+)',mem,re.M)[1])
    if available<192*1024:raise RuntimeError('insufficient free RAM')
    def terminate(*_):raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,terminate)
    Probe(a.interface,a.output).execute(a.frequency,a.repeats)
    print('SCAN_BUSY_PROBE_COMPLETED_PRIVATE_RESULTS')


if __name__=='__main__':main()
