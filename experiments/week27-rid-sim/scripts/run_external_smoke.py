"""PR6a real native geometry smoke; predictions are checked, not invented."""
import argparse
import hashlib
import json
import os
from pathlib import Path

from external_scene import DIRECTIONS,spec_for,run_external
from observer_attack import compare_legacy
from setup import REPO


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--raw-dir',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--workspace',type=Path,default=REPO/'.cache/issue77');a=p.parse_args();os.umask(0o077)
    if not a.raw_dir.resolve().is_relative_to((REPO/'captures').resolve()) or a.raw_dir.exists() or a.out.exists():p.error('New private captures and output paths required')
    a.raw_dir.mkdir(parents=True,mode=0o700);a.out.mkdir(parents=True)
    plans=[];key=os.urandom(32);(a.raw_dir/'private-schedule-key.bin').write_bytes(key)
    for layout in ['baseline','biased','irregular']:
        for case in ['position_only','schedule_aware']:
            plans.append((layout,'x',701,case,30))
        plans.append((layout,'x',701,'position_only',0))
    for case in ['position_only','schedule_aware']:plans.append(('baseline','x',702,case,100))
    plans.append(('baseline','x',702,'position_only',0))
    for direction in DIRECTIONS[1:]:plans.append(('baseline',direction,701,'schedule_aware',100))
    receipts=[];result=dict(status='RUNNING',dataset_source='simulation',stage='PR6a',planned_cases=len(plans),completed_cases=0,receipts=receipts)
    try:
        for layout,direction,seed,case,distance in plans:
            cell=dict(layout=layout,direction=direction,profile='free',schedule='round_robin',bound_db=10,attack_n=2)
            spec=spec_for(cell,seed,case,distance,key);rid=f'{layout}-{direction}-{seed}-{case}-{distance}'
            rows,tx,audit,ledger=run_external(spec,a.workspace.resolve(),a.raw_dir.resolve()/rid)
            record=dict(run_id=rid,layout=layout,direction=direction,seed=seed,attack_case=case,offset_m=distance,tx=audit['tx_enqueued'],rx=audit['rx_delivered'],
                        exit_code=audit['execution_exit_code'],vector_sha256=audit['vector_sha256'],log_sha256=audit['simulation_log_sha256'],claim_max_error_m=audit['claim_max_error_m'],displacement_norm_max_error_m=audit['displacement_norm_max_error_m'])
            if layout=='baseline' and direction=='x' and case=='position_only':
                old=REPO/'captures/issue70-evaluation-20261108-full-a'/f'main-eval-strong-fixed-{seed}-offset{distance}'
                record['legacy']=compare_legacy(rows,tx,old)
            receipts.append(record);result['completed_cases']=len(receipts)
            (a.out/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
            with (a.out/'simulation.log').open('a') as f:
                f.write(f'\nRUN {rid}\n');f.write((a.raw_dir/rid/'simulation.log').read_text().replace(str(REPO),'<REPO>'))
        result.update(status='PR6A_GEOMETRY_SMOKE_PASSED',total_new_phy_tx=sum(r['tx'] for r in receipts),total_rx=sum(r['rx'] for r in receipts),private_schedule_key_commitment=hashlib.sha256(key).hexdigest())
    except Exception as error:result.update(status='PR6A_FAILED',error=f'{type(error).__name__}: {error}')
    (a.out/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='receipts'},indent=2));return 0 if result['status']=='PR6A_GEOMETRY_SMOKE_PASSED' else 2


if __name__=='__main__':raise SystemExit(main())
