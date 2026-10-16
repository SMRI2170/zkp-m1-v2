import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
paths=[p for p in (ROOT/'experiments/balanced-cli').rglob('*') if p.is_file() and '__pycache__' not in p.parts]
paths += [ROOT/'.github/workflows/balanced-cli.yml',ROOT/'week24/14_CLI方式の21件ドライバとPi接続状況.md']
(ROOT/'week24/manifests/balanced-cli.json').write_text(json.dumps({'scope':'source adapter and fake CLI tests only; no real CLI/Pi proofs','file_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}},indent=2)+'\n')
