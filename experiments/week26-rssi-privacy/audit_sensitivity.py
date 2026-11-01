"""Audit paired controls and export grid-limited detection summaries."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
from sensitivity_suite import KEYS


def main():
    p=argparse.ArgumentParser();p.add_argument('run',type=Path);args=p.parse_args()
    result=json.loads((args.run/'summary.json').read_text());summaries=result['summaries']
    checks=[]
    for study,rows in summaries.items():
        unique={tuple(row[k] for k in KEYS[study]) for row in rows}
        assert len(unique)==len(rows)
        assert all(row['seeds']==len(result['config']['seeds']) for row in rows)
        for row in rows:
            if 'alarms' in row:
                assert 0<=row['alarms']<=row['tested']
                assert row['alarm_rate']==(row['alarms']/row['tested'] if row['tested'] else None)
        checks.append(study+': unique groups, seed counts and denominators valid')
    for row in summaries['position']:
        if row['direction']=='same_range':
            assert row['tested']==row['baseline_tested']
            assert row['alarms']==row['baseline_alarms']
    checks.append('single-RX same-range controls exactly match normal alarms')
    for row in summaries['synchronous']:
        if row['receivers']==1:assert row['alarms']==0
    checks.append('single RX has zero profiled unknown-power position information')
    for n in result['config']['receiver_counts']:
        a=next(r for r in summaries['asynchronous'] if r['receivers']==n and r['scenario']=='normal')
        b=next(r for r in summaries['asynchronous'] if r['receivers']==n and r['scenario']=='range_shift30')
        assert a['tested']==b['tested'] and a['mae_m']==b['mae_m']
    checks.append('async position-only claims cannot change RSSI-only GP predictions')
    for row in summaries['personalization']:
        if row['labeled_per_rid']==0:
            control=next(r for r in summaries['personalization'] if r['profile']==row['profile'] and r['scenario']==row['scenario'] and r['model']=='global' and r['labeled_per_rid']==0)
            assert row['mae_m']==control['mae_m']
    checks.append('RID cold-start models equal the shared predictor')
    sync=summaries['synchronous'];thresholds=[]
    for n in result['config']['receiver_counts']:
        for aperture in result['config']['sync']['aperture_radius_m']:
            for noise in result['config']['sync']['independent_link_noise_sd_db']:
                for direction in ['random_horizontal','same_range_first_rx']:
                    selected=sorted([r for r in sync if r['receivers']==n and r['aperture_radius_m']==aperture and r['link_noise_sd_db']==noise and r['direction']==direction],key=lambda r:r['delta_m'])
                    for target in [.5,.8,.95]:
                        hits=[r for r in selected if r['delta_m']>0 and r['alarm_rate'] is not None and r['alarm_rate']>=target]
                        thresholds.append({'receivers':n,'aperture_radius_m':aperture,'link_noise_sd_db':noise,'direction':direction,
                                           'target_alarm_rate':target,'first_sampled_displacement_m':hits[0]['delta_m'] if hits else None,
                                           'heldout_normal_fpr':selected[0]['matched_normal_fpr'],
                                           'scope':'first sampled grid point only; no guarantee between points or outside this synthetic condition'})
    with (args.run/'sampled-detection-limits.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(thresholds[0]));writer.writeheader();writer.writerows(thresholds)
    with (args.run/'personalization-seed-metrics.csv').open(newline='') as f:
        raw=list(csv.DictReader(f))
    seed_lookup={(int(r['seed']),r['profile'],int(r['labeled_per_rid']),r['scenario'],r['model']):r for r in raw}
    gains=[]
    for row in summaries['personalization']:
        if row['model']=='global':continue
        control=next(r for r in summaries['personalization'] if r['profile']==row['profile'] and r['scenario']==row['scenario'] and r['model']=='global' and r['labeled_per_rid']==row['labeled_per_rid'])
        seed_gains=[]
        for seed in result['config']['seeds']:
            rid=seed_lookup[seed,row['profile'],row['labeled_per_rid'],row['scenario'],row['model']]
            shared=seed_lookup[seed,row['profile'],row['labeled_per_rid'],row['scenario'],'global']
            seed_gains.append(100*(1-float(rid['abs_error_sum'])/float(shared['abs_error_sum'])))
        gains.append({'profile':row['profile'],'labeled_per_rid':row['labeled_per_rid'],'scenario':row['scenario'],'model':row['model'],
                      'shared_mae_m':control['mae_m'],'personalized_mae_m':row['mae_m'],
                      'relative_mae_reduction_percent':100*(1-row['mae_m']/control['mae_m']),
                      'seed_gain_min_percent':min(seed_gains),'seed_gain_max_percent':max(seed_gains),
                      'seeds_improved':sum(g>0 for g in seed_gains),'seeds':len(seed_gains)})
    with (args.run/'rid-improvement.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(gains[0]));writer.writeheader();writer.writerows(gains)
    source_hash_matches=hashlib.sha256(Path(__file__).with_name('sensitivity_suite.py').read_bytes()).hexdigest()==result['source_sha256']
    assert source_hash_matches
    (args.run/'audit.json').write_text(json.dumps({'status':'passed','checks':checks,
         'source_hash_matches':source_hash_matches},indent=2)+'\n')
    print('Passed',len(checks),'saved-result checks; sampled detection limits saved.')


if __name__=='__main__':main()
