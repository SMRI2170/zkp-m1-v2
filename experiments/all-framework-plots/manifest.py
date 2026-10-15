"""Hash the new artifacts without editing older experiment ledgers."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
files=[]
for name in ['experiments/all-framework-plots','week24/data/all-frameworks','week24/plots/all-frameworks']:
    files.extend(p for p in (ROOT/name).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
files+=[ROOT/'week24/plots/all-frameworks.zip',ROOT/'week24/12_全フレームワークの比較グラフ.md',ROOT/'.github/workflows/all-framework-plots.yml']
m={'scope':'18 assessed configurations; existing public measured metadata only','new_measurements':False,
   'file_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(set(files))}}
(ROOT/'week24/manifests/all-framework-plots.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
