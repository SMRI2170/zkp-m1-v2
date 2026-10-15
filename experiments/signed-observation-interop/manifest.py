# coding: utf-8
"""Record reviewed source, dependency lock, and public verdict evidence."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
files=[]
for name in ['experiments/signed-observation-interop','week24/logs/signed-observation-interop']:
    files.extend(p for p in (ROOT/name).rglob('*') if p.is_file() and 'target' not in p.parts and '__pycache__' not in p.parts)
for name in ['week24/11_署名付き観測の共有仕様とRust互換検証.md','.github/workflows/signed-observation-interop.yml']:
    files.append(ROOT/name)
m={'issue':50,'completed_task':'shared statement and native interoperability reference',
   'proof_generated':False,'jolt_vm_executed':False,'pi_executed':False,
   'file_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(set(files))}}
(ROOT/'week24/manifests/signed-observation-interop.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
