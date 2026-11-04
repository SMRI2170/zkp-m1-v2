"""Offline audit of public aggregate SNR evidence; does not re-fetch raw CSV."""
import csv,hashlib,json,math
from collections import defaultdict
from pathlib import Path

root=Path(__file__).resolve().parents[2];p=root/'week27/results/snr-four-station-20261104'
x=json.loads((p/'summary.json').read_text());t=x['tables']
def close(a,b):assert math.isclose(a,b,abs_tol=1e-9),f'{a} != {b}'
for name,sha in x['code_hashes'].items():assert hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()==sha
assert x['source_sha256']=='f261a911a96c6e79b23272a21091b97e51719ef1c1033116d900862afde65fd3'
assert x['sessions']==6 and x['cohort']['accepted_four_station_groups']==6728
assert sum(r['n'] for r in t['session_quality'])==6728
assert sum(x['cohort']['exclusive_exclusions'].values())+6728==x['cohort']['total_uav_groups']==13803
assert len(t['pair_stats'])==36 and len(t['station_stats'])==24
for name,rows in t.items():
    with (p/(name+'.csv')).open() as f:saved=list(csv.DictReader(f))
    assert len(saved)==len(rows)
    for a,b in zip(rows,saved):assert {k:'' if v is None else str(v) for k,v in a.items()}==b,'CSV / JSON mismatch'
for q in t['session_quality']:
    s=q['session'];stations={r['quantity']:r for r in t['station_stats'] if r['session']==s}
    close(sum(r['mean_db'] for r in stations.values()),0)
    for kind,key in [('pair','pair_stats'),('station','station_stats')]:
        for r in [r for r in t[key] if r['session']==s]:
            assert r['n']==q['n'] and r['adjacent_pairs']<=r['n']-1
            assert r['lag_one_correlation'] is None or -1<=r['lag_one_correlation']<=1
            if r['late_minus_early_db'] is None:assert min(r['early_n'],r['late_n'])<20
            else:
                assert min(r['early_n'],r['late_n'])>=20
                close(r['late_minus_early_db'],r['late_median_db']-r['early_median_db'])
            if kind=='pair':
                i,j=r['quantity'].split('-');close(r['mean_db'],stations[i]['mean_db']-stations[j]['mean_db'])
            hist=[h for h in t['histograms'] if h['session']==s and h['kind']==kind and h['quantity']==r['quantity']]
            assert len(hist)==80 and sum(h['count'] for h in hist)==q['n']
            assert all(h['count']>=0 for h in hist)
    grouped=defaultdict(list)
    for r in t['time_windows']:
        if r['session']==s:grouped[r['window_index']].append(r)
    assert len(grouped)==q['accepted_windows']
    covered=0
    for index,rows in grouped.items():
        assert len(rows)==10 and len({(r['kind'],r['quantity']) for r in rows})==10
        assert len({r['n'] for r in rows})==1 and rows[0]['n']>=5
        assert all(r['elapsed_start_s']==10*index for r in rows)
        assert 10*(index+1)<=q['duration_s']
        covered+=rows[0]['n'];station={r['quantity']:r for r in rows if r['kind']=='station'}
        close(sum(r['mean_db'] for r in station.values()),0)
        for r in rows:
            if r['kind']=='pair':
                i,j=r['quantity'].split('-');close(r['mean_db'],station[i]['mean_db']-station[j]['mean_db'])
    assert covered==q['window_covered_frames']<=q['n']
manifest=json.loads((p/'figures/manifest.json').read_text())
assert manifest['input_summary_sha256']==hashlib.sha256((p/'summary.json').read_bytes()).hexdigest()
for name,sha in manifest['code_hashes'].items():assert hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()==sha
for name,sha in manifest['outputs'].items():assert hashlib.sha256((p/'figures'/name).read_bytes()).hexdigest()==sha
assert len(manifest['outputs'])==8
print('Four-station SNR evidence verified: complete cohorts, CSV/JSON, contrast identities, temporal accounting, source/code/figure hashes; raw source not rerun in CI')
