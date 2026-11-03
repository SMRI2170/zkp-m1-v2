"""Offline verification of condition-block results and LoRaIQ audit aggregates."""
import hashlib,json
from pathlib import Path
from cluster_uncertainty import analyze

root=Path(__file__).resolve().parents[2]
p=root/'week27/results'
saved=json.loads((p/'cluster-uncertainty-20261103/summary.json').read_text())
assert analyze(p/'paired-attacks-20261103-v2/fold-metrics.csv')==saved,'Resampling evidence differs'
x=json.loads((p/'loraiq-v2-audit-20261103/summary.json').read_text())
assert x['code_sha256']==hashlib.sha256(Path(__file__).with_name('audit_loraiq.py').read_bytes()).hexdigest()
assert x['total_rows']==114147 and x['uav_rows']==53875
assert x['position_available_uav_rows']+x['uav_rows_missing_position']==x['uav_rows']
assert sum(x['uav_session_rows'].values())==x['uav_rows']
assert sum(x['missing_position_by_session'].values())==x['uav_rows_missing_position']
assert 'rssi' not in x['columns'] and x['gates']['attack_detection']=='NOT_RUN'
for key in ['all_frames','uav_frames','position_available_uav_frames']:
 g=x[key];assert sum(g['receiver_count_histogram'].values())==g['transmissions']
 assert g['complete_consistent_multi_receiver_groups']<=g['complete_consistent_position_groups']<=g['transmissions']
assert x['uav_frames']['complete_consistent_multi_receiver_groups']==7368
print('External validity evidence verified: paired block resampling, hashes and audit accounting; raw LoRaIQ not rerun in CI')

for dirname in ['cluster-uncertainty-20261103','loraiq-v2-audit-20261103']:
    out=p/dirname
    manifest=json.loads((out/'figure-manifest.json').read_text())
    assert manifest['plot_code_sha256']==hashlib.sha256(Path(__file__).with_name('plot_external_validity.py').read_bytes()).hexdigest()
    assert manifest['helper_code_sha256']==hashlib.sha256(Path(__file__).with_name('plot_paired_attacks.py').read_bytes()).hexdigest()
    for name,sha in manifest['outputs'].items():assert hashlib.sha256((out/name).read_bytes()).hexdigest()==sha
print('Both figure manifests verified')
