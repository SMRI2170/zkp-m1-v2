"""Collect saved aggregates for the professor-focused presentation; no raw capture data."""
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / 'week26/results/mac-sensitivity-20261101-v2'
FILES = {'position': 'position-summary.csv', 'nodes': 'asynchronous-summary.csv',
         'history': 'time-summary.csv'}
data = {}
for key, filename in FILES.items():
    with (RESULTS / filename).open(newline='') as stream:
        data[key] = list(csv.DictReader(stream))
data['config'] = json.loads((RESULTS / 'config.json').read_text())
data['inputs'] = [{'path': str(p.relative_to(ROOT)),
                   'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
                  for p in [*(RESULTS / f for f in FILES.values()), RESULTS / 'config.json']]
output = ROOT / '.cache/week26-slides/professor-extra-data.json'
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
print(output)
