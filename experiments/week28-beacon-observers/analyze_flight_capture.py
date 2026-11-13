#!/usr/bin/env python3
"""Aggregate private flight captures without emitting positions, IDs or timestamps.

Input layout: sensor-complete.jsonl, marker-a.json, receiver-{b,c}/{events,
observations}.jsonl. Each receiver directory must be a completed capture segment.
The output measures cache updates, not independent over-the-air packets.
"""
import argparse
import json
from pathlib import Path
import statistics


def rows(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines()]


def intervals(stamps):
    times = sorted(set(stamps))
    gaps = [b-a for a,b in zip(times,times[1:])]
    return dict(count=len(times), median_interval_s=statistics.median(gaps) if gaps else None,
                max_interval_s=max(gaps) if gaps else None)


def receiver(folder, marker):
    events = rows(folder/'events.jsonl')
    start = next(e['started_boottime_s'] for e in events if e['event']=='start')
    observations = rows(folder/'observations.jsonl')
    matching = [r for r in observations if r['bssid'].lower()==marker['tx_mac'].lower()
                and marker['uas_id'] in r['claimed_uas_ids']]
    fresh = [r for r in matching if not r['cache_stale'] and r['monotonic_time_us'] is not None
             and r['monotonic_time_us'] >= start*1e6 and r.get('rssi_dbm') is not None]
    requests = [e for e in events if e['event']=='scan_request']
    return dict(records=len(matching), **intervals([r['monotonic_time_us']/1e6 for r in fresh]),
                roles=sorted({r['source_annotation']['role'] for r in matching}),
                targeted_requests=sum(bool(e.get('requested_frequencies_mhz')) for e in requests),
                broad_requests=sum(not e.get('requested_frequencies_mhz') for e in requests),
                accepted_requests=sum(bool(e['accepted']) for e in requests),
                observation_kind='linux_scan_cache', physical_packet_match='unconfirmed')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    sensors=rows(a.input/'sensor-complete.jsonl')
    result=dict(sensor=dict(samples=len(sensors),gps_valid=sum(r['gps']['valid'] for r in sensors),
                           bme_valid=sum(r['bme280']['valid'] for r in sensors),
                           **intervals([r['host_monotonic_s'] for r in sensors])),receivers={})
    marker=json.loads((a.input/'marker-a.json').read_text())
    for n in ['b','c']:result['receivers'][n]=receiver(a.input/('receiver-'+n),marker)
    # Aggregate only. Never add the private inputs to Git.
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('x') as f:json.dump(result,f,indent=2);f.write('\n')


if __name__=='__main__':main()
