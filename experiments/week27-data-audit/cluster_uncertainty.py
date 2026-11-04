"""Paired descriptive uncertainty, resampling whole conditions, not packets/folds.

This is conditional on the saved fitted models; not a full-pipeline bootstrap
or evidence that the recorded conditions represent new sites or aircraft.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import numpy as np

VARIANTS=('normal','position_only','exact_compensation','bounded_3db','mismatched_n2')

def condition_matrix(rows):
    selected=[r for r in rows if r['direction']=='outward' and float(r['claim_horizontal_shift_m'])==100.]
    grouped={}
    for r in selected:
        key=(r['condition'],r['variant']);grouped.setdefault(key,{})
        run=r['evaluation_run']
        if run in grouped[key]:raise ValueError('Repeated evaluation run')
        grouped[key][run]=float(r['alarm_rate'])
    conditions=sorted({k[0] for k in grouped})
    matrix=[]
    for c in conditions:
        sets=[set(grouped.get((c,v),{})) for v in VARIANTS]
        if len(sets[0])!=3 or any(s!=sets[0] for s in sets):raise ValueError('Incomplete paired run cohort')
        matrix.append([np.mean(list(grouped[c,v].values())) for v in VARIANTS])
    if len(matrix)<2:raise ValueError('Too few clusters')
    return conditions,np.asarray(matrix)


def resample(matrix,seed=27,replicates=10000):
    x=np.asarray(matrix,dtype=float)
    if x.ndim!=2 or len(x)<2 or not np.isfinite(x).all() or np.any((x<0)|(x>1)):raise ValueError('Invalid rates')
    # One common draw for all variants preserves pairing.
    indices=np.random.default_rng(seed).integers(0,len(x),(replicates,len(x)))
    return x[indices].mean(axis=1)


def analyze(path,seed=27,replicates=10000):
    with path.open() as f:conditions,x=condition_matrix(list(csv.DictReader(f)))
    boot=resample(x,seed,replicates);loco=np.array([np.delete(x,k,axis=0).mean(axis=0) for k in range(len(x))])
    estimates=[]
    for i,v in enumerate(VARIANTS):
        delta=(x[:,i]-x[:,0])*100;db=(boot[:,i]-boot[:,0])*100
        estimates.append(dict(variant=v,mean_alarm_rate=float(x[:,i].mean()),
            cluster_percentile_95=np.quantile(boot[:,i],[.025,.975]).tolist(),
            paired_excess_pp=float(delta.mean()),paired_excess_percentile_95_pp=np.quantile(db,[.025,.975]).tolist(),
            leave_one_condition_out_rate_range=[float(loco[:,i].min()),float(loco[:,i].max())]))
    return dict(scope='100m outward; fixed existing LoRa receiver-position/power proxy',
        clusters=len(x),evaluation_runs=len(x)*3,seed=seed,replicates=replicates,
        unit='condition block containing all three rotating train/cal/evaluation roles',
        limitations=['Conditional resampling spread of saved fitted results, not full-pipeline retraining',
                    'Exchangeability of condition blocks is an assumption, not established by these data',
                    'Shared campaign/site may introduce cross-condition dependence',
                    'Not independent-packet/fold confidence bounds or new-site/RID performance guarantees'],
        input_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        condition_means=[dict(condition=c,**{v:float(value) for v,value in zip(VARIANTS,line)}) for c,line in zip(conditions,x)],
        estimates=estimates)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    result=analyze(a.input)
    if a.output.exists():raise ValueError('Output already exists')
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result['estimates'],indent=2))
