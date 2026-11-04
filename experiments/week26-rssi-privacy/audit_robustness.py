"""Saved-run checks. These do not certify RF or model correctness."""
import argparse
import hashlib
import json
from pathlib import Path
from robustness_suite import KEYS


def main():
    p=argparse.ArgumentParser();p.add_argument('run',type=Path);a=p.parse_args()
    r=json.loads((a.run/'summary.json').read_text());s=r['summaries'];checks=[]
    assert json.loads((a.run/'status.json').read_text())['status']=='complete'
    for study,rows in s.items():
        assert len(rows)==len({tuple(v[k] for k in KEYS[study]) for v in rows})
        assert all(v['seeds']==len(r['config']['seeds']) for v in rows)
        for v in rows:
            if 'alarms' in v:
                assert 0<=v['alarms']<=v['tested'];assert v['alarm_rate']==v['alarms']/v['tested']
            if 'accepted_units' in v:
                assert 0<=v['accepted_units']<=v['anchor_units']
                assert v['tested']==v['accepted_units']*r['config']['fresh_anchor_gate']['query_events_per_flight']
                if v['tested']==0:assert v['mae_m'] is None and v['point_wrong30_rate'] is None
        checks.append(study+': groups, seed counts and denominators valid')
    assert all(v['sectors_disjoint'] and v['calibration']['count']==12600 and v['test']['count']==12600 for v in r['empirical_residual_pools'])
    checks.append('empirical pools: sectors disjoint; baseline/scoring row counts match')
    assert all(v['alarms']==v['matched_normal_alarms'] for v in s['empirical_sync'] if v['delta_m']==0)
    checks.append('zero displacement equals corresponding normal control after shift')
    for v in s['poisoning']:
        if v['model']=='shared':
            reference=next(x for x in s['poisoning'] if x['model']=='shared' and x['flight_sd_db']==v['flight_sd_db'] and x['scenario']==v['scenario'])
            assert reference['mae_m']==v['mae_m']
    checks.append('protected shared training is invariant to target-label corruption')
    for v in s['anchor_gate']:
        if v['model']=='rid_gated' and v['scenario']=='step_after8':
            normal=next(x for x in s['anchor_gate'] if x['model']==v['model'] and x['scenario']=='normal' and x['flight_sd_db']==v['flight_sd_db'] and x['anchor_count']==v['anchor_count'])
            assert normal['accepted_units']==v['accepted_units']
    checks.append('attack after anchor retains normal gate acceptance: negative control')
    assert hashlib.sha256(Path(__file__).with_name('robustness_suite.py').read_bytes()).hexdigest()==r['source_sha256']
    checks.append('runner source hash matches saved execution')
    (a.run/'audit.json').write_text(json.dumps({'status':'passed','checks':checks},indent=2)+'\n')
    print('Passed',len(checks),'saved-run checks.')


if __name__=='__main__':main()
