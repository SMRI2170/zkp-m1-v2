import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
paths=[]
for folder in ['experiments/pi-balanced-readiness','week24/logs/pi-readiness-issue60-v1']:
    paths += [p for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts]
paths += [ROOT/'.github/workflows/pi-readiness.yml',ROOT/'week24/15_Pi無負荷の事前観測と測定待ち条件.md']
(ROOT/'week24/manifests/pi-readiness-issue60.json').write_text(json.dumps({'scope':'read-only readiness; no new proofs','file_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}},indent=2)+'\n')
