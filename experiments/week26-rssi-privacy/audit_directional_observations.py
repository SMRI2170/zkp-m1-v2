"""Independent saved-count and provenance audit (no RF/field validation)."""
import argparse
import collections
import csv
import hashlib
import json
from pathlib import Path
import numpy as np


def audit(root):
    manifest=json.loads((root/'manifest.json').read_text())
    cfg=json.loads((root/'config.json').read_text());summary=json.loads((root/'summary.json').read_text())
    checks=[]
    def check(name, predicate):
        if not predicate: raise AssertionError(name)
        checks.append(name)
    check('saved input/output hashes', all(hashlib.sha256((root/p).read_bytes()).hexdigest()==h for p,h in manifest['output_sha256'].items()))
    check('current simulator/config/loader source hashes', all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in manifest['source_sha256'].items()))
    with (root/'per_seed.csv').open() as f: seed=list(csv.DictReader(f))
    keys=['study','noise_sd_db','antennas','power_mode','scenario','distance_m','gap_s','case','model','shift_m','direction']
    groups=collections.defaultdict(list)
    for r in seed: groups[tuple(r[k] for k in keys)].append(r)
    for r in summary['metrics']:
        group=groups[tuple(str(r[k]) for k in keys)]
        assert len(group)==len(cfg['seeds'])
        assert len({g['seed'] for g in group})==len(cfg['seeds'])
        for metric in ('events','decided','alarms'): assert sum(int(g[metric]) for g in group)==r[metric]
        assert 0<=r['alarms']<=r['decided']<=r['events']
        for metric in ('alarm_all','abstain_rate','alarm_conditional'):
            values=[float(g[metric]) for g in group if g[metric]!='']
            if not values: assert r[metric] is None;continue
            assert len(values)==len(cfg['seeds'])
            np.testing.assert_allclose(r[metric],np.mean(values),atol=1e-12)
            assert 0<=r[metric+'_lo']<=r[metric+'_hi']<=1
        if r['model']=='M0_free': assert r['decided']==0 and r['alarm_conditional'] is None and r['abstain_rate']==1
    checks.extend(['all groups have independent-seed support','aggregate counts and seed-rate means','valid counts and bootstrap endpoints','M0-free is explicitly undefined/all-abstention'])
    # Check raw saved rates against integer counts, independently of simulator.
    for r in seed:
        n,k,a=[int(r[t]) for t in ('events','decided','alarms')]
        np.testing.assert_allclose(float(r['alarm_all']),a/n,atol=1e-12)
        np.testing.assert_allclose(float(r['abstain_rate']),1-k/n,atol=1e-12)
        assert (r['alarm_conditional']=='') == (k==0)
        if k: np.testing.assert_allclose(float(r['alarm_conditional']),a/k,atol=1e-12)
    checks.append('every per-seed rate agrees with integer counts')
    identity={}
    for r in seed:
        if r['study']=='main' and r['model'] in ('M1','M2'):
            key=tuple(r[k] for k in ('seed','noise_sd_db','antennas','case','model'))
            value=(r['alarms'],r['decided'])
            if key in identity: assert identity[key]==value
            identity[key]=value
    checks.append('common power modes leave full-reception M1/M2 decisions invariant')
    for r in seed:
        if r['study']=='async' and r['scenario']=='ideal':
            key=tuple(r[k] for k in ('seed','case','model'))
            value=(r['alarms'],r['decided'])
            if key in identity: assert identity[key]==value
            identity[key]=value
    checks.append('timestamp gap alone does not create information/change local decisions')
    examples=summary['counterexamples']
    check('analytic radial, mirror and arbitrary-power counterexamples', all(examples[k]<1e-10 for k in ('radial_equal_rssi_max_db','mirror_two_antenna_max_db','arbitrary_common_power_score_difference_db')))
    with (root/'thresholds.csv').open() as f: tables=list(csv.DictReader(f))
    check('no threshold fitted on unsupported masks',all(int(r['samples'])>=cfg['minimum_calibration_events'] for r in tables))
    check('indoor public data hash provenance and held-out sectors',bool(summary['empirical_sources']) and all(r['disjoint_sector_sets'] for r in summary['empirical_pool_statistics']))
    with (root/'history_per_seed.csv').open() as f: histories=list(csv.DictReader(f))
    lookup={(r['seed'],r['scenario'],r['gap_s'],r['case'],r['rule']):r for r in histories}
    for k,r in lookup.items():
        if k[-1]=='at_least_1_alarms':
            other=lookup[(*k[:-1],'at_least_2_alarms')]
            assert int(other['alarms'])<=int(r['alarms'])
    checks.append('history aggregation threshold ordering')
    if (root/'figures.json').exists():
        figures=json.loads((root/'figures.json').read_text())
        check('figure evidence source and image hashes',
              figures['source_summary_sha256']==hashlib.sha256((root/'summary.json').read_bytes()).hexdigest() and
              all(hashlib.sha256((root/p).read_bytes()).hexdigest()==h for p,h in figures['sha256'].items()))
    return dict(scope='Saved evidence/code verification, not operational RF validation',passed=len(checks),checks=checks)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('result',type=Path);args=p.parse_args()
    result=audit(args.result)
    (args.result/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
