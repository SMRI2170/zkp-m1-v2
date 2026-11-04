"""Collect only saved aggregates and one explicitly synthetic trajectory."""
import csv, hashlib, importlib.util, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
R = ROOT/'week26/results'
def read(folder, name):
 p=R/folder/name
 return json.loads(p.read_text()) if name.endswith('.json') else list(csv.DictReader(p.open()))
data={
 'events':read('mac-event-scenarios-20261101','summary.json'),
 'lora':read('mac-public-lora-20261101','summary.json'),
 'ble':read('mac-recheck-20261101','summary.json'),
 'ble_detection':read('mac-recheck-20261101','detection-summary.csv'),
 'personal':read('mac-sensitivity-20261101-v2','personalization-summary.csv'),
 'empirical':read('mac-robustness-20261101','empirical_sync-summary.csv'),
 'poisoning':read('mac-robustness-20261101','poisoning-summary.csv'),
 'anchor':read('mac-robustness-20261101','anchor_gate-summary.csv'),
 'time':read('mac-robustness-20261101','time_mismatch-summary.csv'),
 'single':read('mac-independent3d-20261101','summary.json')['summary']}
p=ROOT/'experiments/week26-rssi-privacy/event_scenarios.py'
spec=importlib.util.spec_from_file_location('events',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
cfg=data['events']['config'];d=m.generate(cfg,cfg['seeds'][0],1)
data['synthetic_example_xyz']=d['xyz'][0,::6].tolist()
data['inputs']=[{'path':str(p.relative_to(ROOT)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for folder in ['mac-event-scenarios-20261101','mac-public-lora-20261101','mac-recheck-20261101','mac-sensitivity-20261101-v2','mac-robustness-20261101','mac-independent3d-20261101'] for p in (R/folder).glob('*') if p.suffix in ['.csv','.json'] and 'seed-metrics' not in p.name]
out=ROOT/'.cache/week26-slides/slide-data.json';out.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
print('Prepared aggregate slide data:',out)
