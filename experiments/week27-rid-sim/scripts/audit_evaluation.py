"""Add per-observer aggregate evidence and scrubbed execution receipts.

Read original raw records without modification; derived risk ledgers remain
private in captures/. Never publishes trajectories.
"""
import argparse
import json
import math
import os
import statistics
from pathlib import Path

import pyarrow.parquet as pq

from evaluation import metrics,grouped_frames
from normalize import write_csv
from observations import asynchronous_view
from scene import RX_POSITIONS
from setup import REPO
from run_evaluation import user_at


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--raw-dir',type=Path,required=True);p.add_argument('--results',type=Path,required=True)
    a=p.parse_args()
    os.umask(0o077)
    if not a.raw_dir.resolve().is_relative_to((REPO/'captures').resolve()):p.error('Private derived ledgers require ignored captures/')
    summary=json.loads((a.results/'summary.json').read_text())
    if summary['status']!='PR4_EVALUATION_PASSED':raise ValueError('Cannot audit incomplete evaluation as complete')
    receipts=json.loads((a.results/'case-receipts.json').read_text());per_observer=[];execution=[];diagnostics=[]
    for r in receipts:
        directory=a.raw_dir/r['run_id'];spec=r['spec']
        receipt=json.loads((directory/'execution.json').read_text())
        scrub=lambda s:s.replace(str(a.raw_dir.resolve()),'<PRIVATE_CAPTURE>').replace(str(REPO),'<REPO>')
        execution.append(dict(run_id=r['run_id'],**{k:([scrub(str(v)) for v in value] if k=='argv' else value) for k,value in receipt.items()}))
        if '-eval-' not in r['run_id']:continue
        rows=pq.read_table(directory/'observations.parquet').to_pylist()
        view=asynchronous_view(rows,list(RX_POSITIONS),spec['count'])
        if r['run_id'].startswith('risk-'):
            ledger=[]
            for row in view:
                user=user_at(row['tx_time']);true_distance=math.dist(row['true_tx_xyz'],user);claimed_distance=math.dist(row['claimed_xyz'],user)
                ledger.append(dict(tx_event_id=row['tx_event_id'],sim_time=row['tx_time'],synthetic_user_xyz=user,
                                   true_distance_m=true_distance,claimed_distance_m=claimed_distance,
                                   risky_claim=true_distance<30<=claimed_distance,evaluation_only=True))
            (directory/'risk-distance-ledger.json').write_text(json.dumps(ledger)+'\n')
        results=json.loads((directory/'detector-scores.json').read_text())
        if spec['offset_x_m']==0 and '-strong-' in r['run_id'] and not r['run_id'].startswith('risk-'):
            for n in [4,5]:
                spans=[]
                for frame in grouped_frames(rows,list(RX_POSITIONS)[:n]):
                    implied=[row['rssi_dbm']+20*math.log10(max(math.dist(row['rx_claimed_xyz'],row['rx_xyz']),.1))+40.04 for row in frame if row['delivered'] and row['rssi_dbm'] is not None]
                    if len(implied)>=2:spans.append(max(implied)-min(implied))
                scores=[v for v in results[f'MLAT{n}']['scores'] if v is not None]
                diagnostics.append(dict(seed=spec['seed'],model=spec['model'],method=f'MLAT{n}',
                                        finite_scores=len(scores),median_normal_position_error_m=statistics.median(scores) if scores else None,
                                        max_normal_position_error_m=max(scores) if scores else None,
                                        median_isotropic_implied_power_span_db=statistics.median(spans) if spans else None))
        for method in ['FreePowerUND','SingleResidual','KF_NIS']:
            decisions=results[method]['decisions']
            for node in RX_POSITIONS:
                indices=[i for i,row in enumerate(view) if row['rx_node_id']==node]
                per_observer.append(dict(seed=spec['seed'],model=spec['model'],offset_m=spec['offset_x_m'],
                                         risk_scenario=r['run_id'].startswith('risk-'),link=next(link for link in ['strong','edge','weak'] if f'-{link}-' in r['run_id']),
                                         method=method,rx_node_id=node,
                                         **metrics([decisions[i] for i in indices],[view[i]['delivered'] for i in indices])))
    write_csv(a.results/'per-observer-metrics.csv',per_observer)
    if diagnostics:write_csv(a.results/'mlat-normal-diagnostics.csv',diagnostics)
    (a.results/'execution-receipts.json').write_text(json.dumps(execution,indent=2)+'\n')
    print(json.dumps(dict(status='PASSED',scenes=len(execution),per_observer_metric_rows=len(per_observer)),indent=2))


if __name__=='__main__':main()
