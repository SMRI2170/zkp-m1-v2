#!/usr/bin/env python3
"""Reject private field artifacts from tracked Week29 publication files."""
import csv
import json
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[2]
FORBIDDEN_KEYS={'latitude','longitude','receiver_latitude','receiver_longitude',
                'claimed_latitude','claimed_longitude','claimed_id','uas_id','bssid',
                'private_key','session_key','password','boot_scope'}
FORBIDDEN_SUFFIXES={'.jsonl','.sqlite','.sqlite3','.db','.pem','.key','.ptau','.zkey','.proof'}
ROW_SERIES={'source_rssi.csv','candidate_intervals.csv','update-intervals.csv'}


def check_object(value):
    if isinstance(value,dict):
        if FORBIDDEN_KEYS.intersection(value):raise ValueError('Private row field in public JSON')
        for item in value.values():check_object(item)
    elif isinstance(value,list):
        for item in value:check_object(item)


def main():
    names=subprocess.check_output(['git','ls-files','-z','--','week29'],cwd=ROOT).decode().split('\0')
    checked=0
    for name in filter(None,names):
        p=ROOT/name
        if p.is_symlink() or not p.is_file():raise ValueError('Nonregular publication artifact: '+name)
        if p.suffix in FORBIDDEN_SUFFIXES or p.name in ROW_SERIES or 'captures' in p.parts:
            raise ValueError('Private field artifact must not be tracked: '+name)
        if p.suffix=='.json':check_object(json.loads(p.read_text()))
        elif p.suffix=='.csv':
            with p.open() as f:
                if FORBIDDEN_KEYS.intersection(csv.DictReader(f).fieldnames or []):
                    raise ValueError('Private row field in public CSV: '+name)
        if p.suffix in {'.json','.csv','.md','.log'}:
            value=p.read_text()
            if re.search(r'\b192\.168\.\d+\.\d+\b',value):raise ValueError('Private LAN address in '+name)
            if re.search(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',value):raise ValueError('Private key in '+name)
        checked+=1
    if not checked:raise ValueError('No tracked Week29 artifacts checked; stage publication first')
    print('Checked '+str(checked)+' tracked Week29 files; no private captures, location fields, keys, or row-series CSVs')


if __name__=='__main__':main()
