#!/usr/bin/env python3
"""Summarize private study archives without extracting or publishing raw radio data."""
import argparse
import collections
import csv
import datetime
import io
import json
import re
from pathlib import Path
import tarfile
from run_scan_busy_batch import percentile


def scan_spans(text,interface='wlan0'):
    pending={};spans=[];held=collections.Counter()
    pattern=re.compile(r'^(\d+\.\d+): (\S+) \(phy #(\d+)\): scan (started|finished)')
    for line in text.splitlines():
        if 'scan started' not in line and 'scan finished' not in line:continue
        m=pattern.match(line)
        if not m:held['unparsed_scan_event']+=1;continue
        stamp,iface,phy,kind=m.groups()
        if iface!=interface:continue
        key=(iface,phy);stamp=float(stamp)
        if kind=='started':
            if key in pending:pending[key]=None;held['overlapping_started']+=1
            else:pending[key]=stamp
        elif key not in pending:held['finished_without_started']+=1
        else:
            start=pending.pop(key)
            if start is None:held['ambiguous_pair']+=1
            elif stamp<start:held['clock_reversal']+=1
            else:spans.append((start,stamp))
    held['unclosed_started']=len(pending)
    return spans,dict(held)


def main():
    p=argparse.ArgumentParser();p.add_argument('--private-root',type=Path,required=True);p.add_argument('--results',type=Path,required=True);a=p.parse_args()
    if 'captures' not in a.private_root.resolve().parts:raise ValueError('Raw archives stay in captures/')
    summary=json.loads((a.results/'summary.json').read_text());trials=summary['trials'];profile=[]
    with tarfile.open(a.private_root/'c-experiment.tar.gz','r:gz') as archive:
        members=archive.getmembers()
        if any(not m.isfile() and not m.isdir() for m in members):raise ValueError('Unexpected archive member type')
        def read(name):
            match=[m for m in members if m.name.lstrip('./')==name]
            if len(match)!=1 or not match[0].isfile() or match[0].size>20*1024**2:raise ValueError('Missing/unsafe study member '+name)
            return archive.extractfile(match[0]).read().decode()
        spans,held=scan_spans(read('batch-results/iw-events-private.log'))
        for trial in trials:
            n=trial['trial'];worker=json.loads(read(f'batch-results/trial-{n}-stdout-private.json'))
            start=datetime.datetime.strptime(worker['run_id'],'%Y%m%dT%H%M%S.%fZ').replace(tzinfo=datetime.timezone.utc).timestamp()
            end=start+trial['wall_elapsed_s']
            subset=[b-a for a,b in spans if start<=a and b<=end]
            prefix=f'batch-results/trial-{n}/'
            size=sum(m.size for m in members if m.isfile() and m.name.lstrip('./').startswith(prefix))
            profile.append(dict(trial=n,round=trial['round'],strategy=trial['strategy'],interval_s=trial['interval_s'],
                scan_event_pairs_inside_window=len(subset),scan_event_duration_median_s=percentile(subset,.5),
                scan_event_duration_p95_s=percentile(subset,.95),worker_child_peak_rss_kib=worker.get('child_peak_rss_kib'),
                trial_capture_files_bytes=size,window_alignment='same-host UTC run label; starts near boundary excluded; not hardware time'))
    with (a.results/'scan-duration-and-resources.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(profile[0]));w.writeheader();w.writerows(profile)
    groups=[]
    for key in sorted({(t['strategy'],t['interval_s']) for t in trials},key=str):
        selected=[t for t in trials if (t['strategy'],t['interval_s'])==key]
        req=sum(t['scan_requests'] for t in selected);busy=sum(t['busy'] for t in selected)
        metrics=[v for v in profile if (v['strategy'],v['interval_s'])==key]
        groups.append(dict(strategy=key[0],configured_interval_s=key[1],windows=len(selected),
            total_requested_seconds=sum(t['requested_duration_s'] for t in selected),requests=req,busy=busy,
            busy_fraction=busy/req if req else None,accepted=sum(t['scan_accepted'] for t in selected),
            new_target_cache_timestamps=sum(t['target_new_observations'] for t in selected),
            new_target_vendor_contents_by_window=[t['target_distinct_vendor_contents'] for t in selected],
            scan_duration_medians_by_window=[v['scan_event_duration_median_s'] for v in metrics],
            peak_worker_child_rss_kib=max((v['worker_child_peak_rss_kib'] for v in metrics if v['worker_child_peak_rss_kib'] is not None),default=None)))
    (a.results/'analysis.json').write_text(json.dumps(dict(groups=groups,scan_event_pairs=len(spans),scan_event_holds=held,
        observed_quantities='Linux scan-cache observations and iw scan notifications; not packet delivery rate',
        limit='one receiver/transmitter placement, two ordered windows per active condition, no independent flights'),indent=2)+'\n')
    print(json.dumps(groups))


if __name__=='__main__':main()
