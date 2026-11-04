"""Check saved synthetic-run accounting and a no-RSSI constant-prior baseline."""
import argparse
import json
from pathlib import Path
import numpy as np
from simulate3d_independent import generate, receive, MODELS, SCENARIOS


def main():
    parser=argparse.ArgumentParser();parser.add_argument('run',type=Path);args=parser.parse_args()
    r=json.loads((args.run/'summary.json').read_text());c=r['config'];stats=[]
    for seed in c['seeds']:
        train=generate(c,seed,'train');test=generate(c,seed,'test')
        train_mask,_=receive(train,c,'mixed');mask,_=receive(test,c,'mixed')
        prior=np.median(train['d_true'][train_mask]);true=test['d_true'][mask]
        stats.append({'seed':seed,'received':len(true),'constant_prior_median_m':float(prior),
                      'constant_prior_abs_error_sum_m':float(np.abs(prior-true).sum()),
                      'always_far_wrong_count':int((true<=30).sum()),
                      'within_20_to_40m_count':int(((true>=20)&(true<=40)).sum()),
                      'true_distance_below_30_count':int((true<30).sum())})
    n=sum(s['received'] for s in stats)
    diag={'scope':'Post-run diagnostic, no GP/MLP refit; normal mixed channel only',
          'per_seed':stats,'pooled':{'received':n,
          'constant_prior_median_mae_m':sum(s['constant_prior_abs_error_sum_m'] for s in stats)/n,
          'always_far_wrong_rate':sum(s['always_far_wrong_count'] for s in stats)/n,
          'within_20_to_40m_fraction':sum(s['within_20_to_40m_count'] for s in stats)/n,
          'below_30m_fraction':sum(s['true_distance_below_30_count'] for s in stats)/n}}
    rows={(v['channel'],v['scenario'],v['model']):v for v in r['summary']}
    for model in MODELS:
        for key in ['mae_m','received','interval_coverage','undetermined_rate']:
            assert rows['mixed','normal',model][key]==rows['mixed','position_only',model][key],(model,key)
    expected=len(c['seeds'])*c['flights']['test']*c['events_per_flight']
    assert rows['mixed','normal','GP']['emitted']==expected
    assert sum(v['emitted'] for v in r['summary'] if v['channel']=='mixed' and v['model']=='GP')==expected*len(SCENARIOS)
    diag['checks']={'paired_position_only_predictions_identical':True,
                    'main_event_condition_instances':expected*len(SCENARIOS),
                    'main_normal_emitted':expected}
    (args.run/'geometry-and-prior-diagnostic.json').write_text(json.dumps(diag,indent=2)+'\n')
    print(json.dumps(diag['pooled']))


if __name__=='__main__':main()
