"""Offline evidence accounting; does not rerun RF or validate field accuracy."""
import argparse
from collections import defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path


def validate(directory):
    if json.loads((directory/'status.json').read_text())['status']!='COMPLETED':
        raise ValueError('Incomplete study')
    groups=defaultdict(list)
    keys=['source','k','noise_sd_db','direction','attack','offset_m','threshold_policy']
    with (directory/'per-seed.csv').open() as f:
        for row in csv.DictReader(f):
            total,scored,flags,und=(int(row[k]) for k in ['windows','scored','flags','und'])
            if not 0<=flags<=scored<=total or scored+und!=total:raise ValueError('Invalid denominator')
            if abs(float(row['alarm_all'])-flags/total)>1.e-12:raise ValueError('All-window rate mismatch')
            if abs(float(row['eligible'])-scored/total)>1.e-12:raise ValueError('Eligibility mismatch')
            groups[tuple(row[k] for k in keys)].append(row)
    with (directory/'aggregate.csv').open() as f:
        aggregates=list(csv.DictReader(f))
    if len(groups)!=len(aggregates):raise ValueError('Missing/duplicate aggregate')
    for aggregate in aggregates:
        group=groups[tuple(aggregate[k] for k in keys)]
        if len({row['seed'] for row in group})!=len(group):raise ValueError('Duplicate seed')
        if len(group)!=int(aggregate['independent_seeds']):raise ValueError('Seed denominator mismatch')
        for field in ['windows','scored','flags','und']:
            if sum(int(row[field]) for row in group)!=int(aggregate[field]):raise ValueError('Count mismatch')
        for field in ['alarm_all','eligible']:
            expected=sum(float(row[field]) for row in group)/len(group)
            if abs(expected-float(aggregate[field+'_mean']))>1.e-12:raise ValueError('Macro mean mismatch')
        for row in group:
            if row['threshold_m']!=aggregate['threshold_m']:raise ValueError('Threshold changed per attack/seed')
    manifest=directory/'manifest.json'
    if manifest.exists():
        for name,expected in json.loads(manifest.read_text())['sha256'].items():
            if hashlib.sha256((directory/name).read_bytes()).hexdigest()!=expected:raise ValueError('Artifact hash mismatch: '+name)
    return dict(directory=directory.name,aggregate_groups=len(groups),per_seed_rows=sum(map(len,groups.values())),status='ACCOUNTING_VERIFIED')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directories',nargs='+',type=Path);a=p.parse_args()
    print(json.dumps([validate(d) for d in a.directories],indent=2))


if __name__=='__main__':main()
