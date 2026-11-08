"""Regenerate seed-level aggregate statistics from saved public per-seed counts."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

from evaluation import seed_interval
from normalize import write_csv
from run_evaluation import aggregate


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('results',type=Path);a=p.parse_args()
    cfg=json.loads((a.results/'configuration.json').read_text())
    source=a.results/'per-seed-metrics.csv'
    with source.open() as f:records=list(csv.DictReader(f))
    strings=['link','model','method']
    integers=['seed','offset_m','tx_count','received_count','scored_count','flag_count','below_count','und_count']
    rows=[]
    for record in records:
        row={}
        for key,value in record.items():
            if key in strings:row[key]=value
            elif key=='risk_scenario':row[key]=value=='True'
            elif key in integers:row[key]=int(value)
            else:row[key]=float(value) if value else None
        rows.append(row)
    write_csv(a.results/'aggregate-metrics.csv',aggregate(rows,cfg['bootstrap_repeats']))
    receipt=dict(status='PASSED',per_seed_source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                 per_seed_rows=len(rows),scope='No RF rerun, no threshold changes; reaggregate saved independent-seed metrics. One scored seed has a mean but no uncertainty interval.',
                 source_sha256={name:hashlib.sha256((Path(__file__).parent/name).read_bytes()).hexdigest() for name in ['evaluation.py','run_evaluation.py','summarize_evaluation.py']})
    (a.results/'statistics-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt,indent=2))


if __name__=='__main__':main()
