"""Matched honest-at-claim control; synthetic LDPL, NOT another RF execution.

An alert under power compensation can just be poor calibration at the claimed
distance. Compare an honest transmitter at that position using the SAME noise.
For K=1 and unclipped compensation the observables are algebraically identical.
"""
import argparse
import json
from pathlib import Path
import numpy as np
from normalize import write_csv
from run_ghostbuster import observations, estimate, score, claims_for, record_scores, aggregate


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--study',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    if a.out.exists():p.error('New output path required')
    a.out.mkdir(parents=True);cfg=json.loads((a.study/'config.json').read_text())
    import csv
    with (a.study/'aggregate.csv').open() as f: prior=list(csv.DictReader(f))
    rows=[];audits=[]
    for k in [1,5]:
        thresholds={row['threshold_policy']:float(row['threshold_m']) for row in prior
                    if int(row['k'])==k and row['noise_sd_db']=='3.5'}
        for seed in cfg['evaluation_seeds']:
            position,r,base=observations(cfg,seed,cfg['evaluation_windows_per_seed'],k,3.5)
            for offset in cfg['offsets_m']:
                q=claims_for(position,r,'away_rx0',offset)
                actual=np.linalg.norm(position[:,:,None,:]-r,axis=-1)
                claimed=np.linalg.norm(q[:,:,None,:]-r,axis=-1)
                correction=10*cfg['path_loss_exponent']*np.log10(actual/claimed)
                honest=np.trunc(base+correction)
                e,valid,detail=estimate(honest,r,cfg)
                meta=dict(source='synthetic_ldpl',k=k,noise_sd_db=3.5,direction='away_rx0',
                          attack='honest_at_claimed_position',offset_m=offset)
                record_scores(rows,score(e,valid,q,r),seed,meta,thresholds)
                clipped=np.clip(correction[...,0],-cfg['power_change_bound_db'],cfg['power_change_bound_db'])
                attack=np.trunc(base+clipped[...,None])
                unconstrained=(np.abs(correction[...,0])<=cfg['power_change_bound_db'])
                errors=np.abs(attack[...,0]-honest[...,0])[unconstrained]
                audits.append(dict(k=k,seed=seed,offset_m=offset,unclipped_packets=int(unconstrained.sum()),
                                   packets=unconstrained.size,paired_rx0_rss_max_difference_unclipped_db=float(errors.max()) if len(errors) else None,
                                   **detail))
    write_csv(a.out/'per-seed.csv',rows);write_csv(a.out/'aggregate.csv',aggregate(rows,cfg['bootstrap_repeats']))
    (a.out/'audit.json').write_text(json.dumps(audits,indent=2)+'\n')
    (a.out/'status.json').write_text(json.dumps(dict(status='COMPLETED',new_native_rf_cases=0,
        scope='Same-noise synthetic honest-at-claim control; not a real flight. Normal threshold unchanged from study.',
        maximum_paired_rx0_rss_error_unclipped_db=max(r['paired_rx0_rss_max_difference_unclipped_db'] or 0 for r in audits)),indent=2)+'\n')


if __name__=='__main__':main()
