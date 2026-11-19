#!/usr/bin/env python3
"""Finite isolated Pi scan comparison. Never controls normal services or changes channels."""
import argparse
import collections
import csv
import json
import math
import os
from pathlib import Path
import random
import shutil
import subprocess
import time


def plan():
    conditions=[dict(strategy=s,interval_s=v) for s in ['all_channels','fixed_frequency'] for v in [.5,1,2,5]]
    conditions.append(dict(strategy='adaptive',interval_s=.25))
    random.Random(20261119).shuffle(conditions)
    result=[dict(round=0,strategy='passive',interval_s=None)]
    for round_number,order in [(1,conditions),(2,list(reversed(conditions)))]:
        result.extend(dict(round=round_number,**x) for x in order)
    result.append(dict(round=3,strategy='passive',interval_s=None))
    return [dict(trial=i+1,**x) for i,x in enumerate(result)]


def percentile(values,p):
    if not values:return None
    v=sorted(values);i=(len(v)-1)*p;j=int(i)
    return v[j]+(v[min(j+1,len(v)-1)]-v[j])*(i-j)


def summarize(rows,events,target_id,started_us):
    matching=[r for r in rows if target_id in (r.get('claimed_uas_ids') or [])]
    current=[r for r in matching if r.get('rid_parse_status')=='decoded' and r.get('cache_stale') is False
             and isinstance(r.get('monotonic_time_us'),(int,float)) and r['monotonic_time_us']>=started_us]
    timestamps=sorted({r['monotonic_time_us'] for r in current})
    intervals=[(b-a)/1e6 for a,b in zip(timestamps,timestamps[1:]) if b>a]
    requests=[e for e in events if e.get('event')=='scan_request']
    reasons=collections.Counter(e.get('failure_reason') or 'unclassified' for e in requests if not e.get('accepted'))
    rssi=[r['rssi_dbm'] for r in current if isinstance(r.get('rssi_dbm'),(int,float)) and math.isfinite(r['rssi_dbm'])]
    return dict(scan_requests=len(requests),scan_accepted=sum(e.get('accepted') is True for e in requests),
                busy=reasons.get('busy',0),permission=reasons.get('permission',0),timeout=reasons.get('timeout',0),
                other_failures=sum(v for k,v in reasons.items() if k not in ['busy','permission','timeout']),
                target_saved_rows=len(matching),target_new_observations=len(timestamps),
                target_distinct_vendor_contents=len({r.get('vendor_content_digest') for r in current if r.get('vendor_content_digest')}),
                target_interval_median_s=percentile(intervals,.5),target_interval_p95_s=percentile(intervals,.95),
                target_rssi_median_dbm=percentile(rssi,.5),
                busy_fraction=reasons.get('busy',0)/len(requests) if requests else None,
                physical_packet_count_known=False,packet_delivery_rate=None)


def load_jsonl(path):
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--release',type=Path,required=True);p.add_argument('--config',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--target',type=Path,required=True)
    p.add_argument('--frequency',type=int,required=True);p.add_argument('--duration',type=int,default=20)
    a=p.parse_args();os.umask(0o077)
    if os.getuid()==0:raise ValueError('Run as observer user with scoped CAP_NET_ADMIN')
    if not 2412<=a.frequency<=2472 or not 10<=a.duration<=30:raise ValueError('Bounded 2.4GHz study required')
    release=a.release.resolve();out=a.output.absolute();anchor=release/'captures'
    if not out.is_relative_to(anchor) or any(x.is_symlink() for x in [out,*out.parents]):raise ValueError('Private output inside release captures required')
    if out.exists():raise ValueError('New experiment output required')
    cfg=json.loads(a.config.read_text());target=json.loads(a.target.read_text())['uas_id']
    if not target.startswith('PI-RID-SCAN-'):raise ValueError('Distinct study marker required')
    state=subprocess.run(['systemctl','is-active','zkp-rid-observer.service'],capture_output=True,text=True,timeout=10)
    if state.stdout.strip() not in ['inactive','failed']:raise ValueError('Normal receiver still running; refuse competing scans')
    mem={x.split(':')[0]:int(x.split()[1])*1024 for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')}
    if mem['MemAvailable']<256*1024**2 or shutil.disk_usage(release).free<2*1024**3:raise ValueError('Insufficient RAM/SD headroom')
    out.mkdir(mode=0o700,parents=True);results=[];complete=False
    (out/'plan.json').write_text(json.dumps(dict(conditions=plan(),duration_s=a.duration,poll_interval_s=.25,random_seed=20261119),indent=2)+'\n')
    trace_log=(out/'iw-events-private.log').open('x');trace=None
    try:
        trace=subprocess.Popen(['/usr/sbin/iw','event','-t'],stdout=trace_log,stderr=subprocess.STDOUT)
        with (out/'results.csv').open('x',newline='') as table:
            writer=None
            for item in plan():
                trial=out/('trial-'+str(item['trial']));started=time.monotonic()
                started_us=time.clock_gettime(getattr(time,'CLOCK_BOOTTIME',time.CLOCK_MONOTONIC))*1e6
                cmd=['/usr/bin/python3',str(release/'experiments/week28-beacon-observers/run_observer.py'),
                     '--config',str(a.config),'--capture-root',str(trial),'--duration',str(a.duration),'--interval','.25']
                if item['strategy']!='passive':cmd+=['--active-scan','--scan-interval',str(item['interval_s'])]
                if item['strategy']=='fixed_frequency':cmd+=['--frequency',str(a.frequency)]
                if item['strategy']=='adaptive':cmd+=['--adaptive-scan','--discovery-interval','30']
                worker=subprocess.run(cmd,capture_output=True,text=True,timeout=a.duration+30)
                (out/('trial-'+str(item['trial'])+'-stdout-private.json')).write_text(worker.stdout)
                (out/('trial-'+str(item['trial'])+'-stderr-private.log')).write_text(worker.stderr)
                logs=list(trial.rglob('events.jsonl'));records=list(trial.rglob('observations.jsonl'))
                events=load_jsonl(logs[0]) if len(logs)==1 else []
                rows=load_jsonl(records[0]) if len(records)==1 else []
                end_events=[e for e in events if e.get('event')=='finish']
                try:worker_summary=json.loads(worker.stdout);reason=(worker_summary.get('capture') or {}).get('stopped_reason')
                except ValueError:reason=None
                result=dict(node=cfg['node_id'][-1].upper(),**item,requested_duration_s=a.duration,
                            wall_elapsed_s=time.monotonic()-started,exit_code=worker.returncode,stopped_reason=reason,
                            valid_duration_complete=worker.returncode in [0,3] and reason=='duration_complete',
                            **summarize(rows,events,target,started_us))
                results.append(result)
                (out/'summary.json').write_text(json.dumps(dict(completed=False,trials=results,real_drone=False),indent=2)+'\n')
                if writer is None:writer=csv.DictWriter(table,fieldnames=list(result));writer.writeheader()
                writer.writerow(result);table.flush();os.fsync(table.fileno())
                if not result['valid_duration_complete']:break
                time.sleep(2)
            complete=len(results)==len(plan()) and all(r['valid_duration_complete'] for r in results)
    finally:
        if trace and trace.poll() is None:
            trace.terminate()
            try:trace.wait(timeout=5)
            except subprocess.TimeoutExpired:trace.kill();trace.wait()
        trace_log.close()
        (out/'summary.json').write_text(json.dumps(dict(completed=complete,trials=results,real_drone=False,
            interpretation='controlled synthetic-ID RF; scan cache updates, not physical packets; normal service restoration managed externally'),indent=2)+'\n')
    return 0 if complete else 2


if __name__=='__main__':raise SystemExit(main())
