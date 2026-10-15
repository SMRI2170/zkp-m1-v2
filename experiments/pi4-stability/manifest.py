# coding: utf-8
"""Regenerate the public evidence hash ledger after reviewing source and raw logs."""
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
files=[]
for directory in ['experiments/pi4-stability','experiments/pi4-binding-tests',
                  'week24/logs/pi-stability','week24/data/pi-observation-scaling-v2']:
    files.extend(p for p in (ROOT/directory).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
files.extend((ROOT/'week24/plots').glob('pi-observation-scaling-v2*'))
for name in ['week24/10_追加実装と進捗.md','week24/README.md','.github/workflows/verify.yml']:
    files.append(ROOT/name)
for name in ['main.go','main_test.go','go.mod','go.sum']:
    files.append(ROOT/'experiments/pi4-euclidean-evaluation/workload'/name)
for name in ['collect.py','summarize.py','plot_workload.py','plot_memory.py','run_guarded.py']:
    files.append(ROOT/'experiments/pi4-euclidean-evaluation'/name)
m={'basis_commit':'e9705d1d02d3e2a8fd1550e73cbd6d8593371ef0',
   'pi_n4_verified':True,'original_workload_unchanged':True,'pi_restart_cause':'unknown',
   'readiness_scope':'before and during initialization; not three idle samples before load',
   'launcher_pi_e2e_verified':False,
   'file_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(set(files))}}
(ROOT/'week24/manifests/pi-stability.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
