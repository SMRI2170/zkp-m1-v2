"""Hash only new Issue #58 artifacts; old manifests remain unchanged."""
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
paths=[]
for folder in ['experiments/unified-distance-bench','week24/data/unified-distance-plan','week24/logs/unified-native-v2']:
    paths += [p for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts]
paths += [ROOT/'.github/workflows/unified-distance.yml',ROOT/'week24/13_比較条件の統一と21件ベンチ実装.md']
result={'scope':'balanced driver implementation and recorded host correctness; not Pi balanced measurements',
        'file_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}}
(ROOT/'week24/manifests/unified-distance.json').write_text(json.dumps(result,indent=2)+'\n')
