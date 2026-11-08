"""Add independent-seed intervals for observer/power/clipping strata, no RF."""
import argparse
from collections import defaultdict
import csv
import hashlib
import json
from pathlib import Path

from normalize import write_csv
from run_observer_attack import bootstrap


def summarize(path,field,repeats):
    with path.open() as stream:rows=list(csv.DictReader(stream))
    keys=['phy','link','attack_case','offset_m','bound_db','method',field];groups=defaultdict(list)
    for r in rows:groups[tuple(r[k] for k in keys)].append(r)
    output=[]
    for key,records in groups.items():
        if len({r['seed'] for r in records})!=len(records):raise ValueError('Duplicate independent seed in stratum')
        result=dict(zip(keys,key));result['seeds_with_tx_in_stratum']=len(records)
        for metric in ['alarm_scored','alarm_received','alarm_all_tx','below_scored','und_rate','received_rate','eligible_rate']:
            result.update({f'{metric}_{k}':v for k,v in bootstrap([float(r[metric]) if r[metric] else None for r in records],repeats).items()})
        for metric in ['tx_count','received_count','scored_count','flag_count','below_count','und_count']:result[metric]=sum(int(r[metric]) for r in records)
        output.append(result)
    return output


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('results',type=Path);a=p.parse_args()
    cfg=json.loads((a.results/'configuration.json').read_text());outputs=[]
    for source,field,target in [('per-observer-metrics.csv','rx_node_id','observer-stratified-aggregate.csv'),
                                 ('power-stratified-metrics.csv','power_bin_dbm','power-stratified-extended.csv'),
                                 ('clipping-stratified-metrics.csv','constraint_stratum','clipping-stratified-extended.csv')]:
        path=a.results/source;destination=a.results/target
        if destination.exists():raise ValueError('Preserve the previous aggregate; choose a new results directory for reanalysis')
        rows=summarize(path,field,cfg['bootstrap_repeats']);write_csv(destination,rows)
        outputs.append(dict(source=source,source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),output=target,groups=len(rows)))
    (a.results/'stratum-intervals-receipt.json').write_text(json.dumps(dict(status='PASSED',outputs=outputs,
               scope='No RF or threshold changes. Per-seed rates; no interval for <2 defined seeds. Power/clamp strata use evaluation truth only.'),indent=2)+'\n')
    print(json.dumps(outputs,indent=2))


if __name__=='__main__':main()
