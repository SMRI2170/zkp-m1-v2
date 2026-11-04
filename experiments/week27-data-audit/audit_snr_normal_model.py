"""Offline accounting and leakage-boundary audit, not a raw-data reanalysis."""
from collections import defaultdict
import csv,hashlib,json,math
from pathlib import Path
root=Path(__file__).resolve().parents[2];p=root/'week27/results/snr-normal-model-20261104'
x=json.loads((p/'summary.json').read_text())
def close(a,b):assert math.isclose(a,b,rel_tol=1e-10,abs_tol=1e-12)
for name,sha in x['code_hashes'].items():assert hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()==sha
assert x['cohort']['accepted_four_station_groups']==6728 and len(x['rows'])==72 and len(x['parameters'])==24
assert len({(r['fold'],r['method'],r['evaluation_session']) for r in x['rows']})==72
assert x['source_sha256']=='f261a911a96c6e79b23272a21091b97e51719ef1c1033116d900862afde65fd3'
assert x['receiver_location_sha256']=='62531352197223e47c4a1a5ed0e9b44eac74a01e472512febae97ab4bfd9621e'
inventory={r['session']:r for r in x['session_inventory']}
for name in ['rows','aggregates']:
    with (p/(name+'.csv')).open() as f:rows=list(csv.DictReader(f))
    assert rows==[{k:'' if v is None else str(v) for k,v in r.items()} for r in x[name]]
for model in x['parameters']:
    train=model['training_sessions'].split(',');cal=model['calibration_session'];test=model['heldout_los_session']
    assert len(set(train))==2 and len(set(train+[cal,test]))==4
    assert all(inventory[s]['domain']=='drone_los' for s in train+[cal,test])
    close(sum(model['station_offsets_db']),0)
    if model['method']=='horizontal_geometry':
        close(model['fitted_n'],-model['slope_db_per_log10']/10)
        assert model['decaying_slope']==(model['slope_db_per_log10']<0)
    else:assert model['slope_db_per_log10']==0 and model['fitted_n'] is None
    rows=[r for r in x['rows'] if r['fold']==model['fold'] and r['method']==model['method']]
    assert {r['evaluation_session'] for r in rows}=={test,'S5','S6'}
    assert len({r['threshold_db'] for r in rows})==len({r['window_threshold_db'] for r in rows})==1
    for r in rows:
        assert r['training_sessions']==model['training_sessions'] and r['calibration_session']==cal
        assert r['evaluation_session'] not in train+[cal]
        assert r['evaluation_frames']==inventory[r['evaluation_session']]['frames']
        assert r['calibration_frames']==inventory[cal]['frames']
        assert 0<=r['normal_alarm_rate']<=1 and 0<=r['feature_component_range_outside_fraction']<=1
        if r['evaluation_session']=='S6':assert r['normal_window_alarm_rate'] is None and r['evaluation_windows']==0
for a in x['aggregates']:
    rows=[r for r in x['rows'] if r['domain']==a['domain'] and r['method']==a['method']]
    grouped=defaultdict(list)
    for r in rows:grouped[r['evaluation_session']].append(r)
    assert len(rows)==a['evaluation_rows'] and len(grouped)==a['evaluation_sessions']
    for field,target in [('normal_alarm_rate','session_equal_mean_normal_alarm_rate'),('centered_snr_rmse_db','session_equal_mean_rmse_db')]:
        means=[sum(r[field] for r in g)/len(g) for g in grouped.values()];close(sum(means)/len(means),a[target])
    close(min(r['normal_alarm_rate'] for r in rows),a['row_alarm_rate_min']);close(max(r['normal_alarm_rate'] for r in rows),a['row_alarm_rate_max'])
    w=[r for r in rows if r['normal_window_alarm_rate'] is not None]
    assert len(w)==a['window_evaluable_rows'] and len({r['evaluation_session'] for r in w})==a['window_evaluable_sessions']
    close(sum(r['normal_window_alarm_rate'] for r in w)/len(w),a['mean_evaluable_window_alarm_rate'])
m=json.loads((p/'figures/manifest.json').read_text())
assert m['input_summary_sha256']==hashlib.sha256((p/'summary.json').read_bytes()).hexdigest()
for name,sha in m['code_hashes'].items():assert hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()==sha
assert len(m['outputs'])==6
for name,sha in m['outputs'].items():assert hashlib.sha256((p/'figures'/name).read_bytes()).hexdigest()==sha
print('Normal SNR model evidence verified: split boundaries, calibration invariance, CSV/JSON aggregates, parameters and code/figure hashes; no attacks or raw reanalysis in CI')
