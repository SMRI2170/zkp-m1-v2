# coding: utf-8
"""Rebuild a separate scaling dataset; never edit the historic n4 partial trial."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[2]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--new-run',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    for name in ['metadata.json','benchmark.jsonl']:
        if not (a.new_run/name).is_file():p.error('Missing '+name)
    cache=ROOT/'.cache/week24';cache.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='scaling-input-',dir=cache) as d:
        staging=Path(d)
        original=ROOT/'week24/logs/pi-observation-workload'
        for run in sorted(original.iterdir()):
            if run.is_dir():shutil.copytree(run,staging/run.name)
        if (staging/a.new_run.name).exists():p.error('New run must have a different name from historic trials')
        shutil.copytree(a.new_run,staging/a.new_run.name)
        scripts=ROOT/'experiments/pi4-euclidean-evaluation'
        subprocess.run([sys.executable,str(scripts/'collect.py'),'--runs',str(staging),'--out',str(a.out)],check=True)
        subprocess.run([sys.executable,str(scripts/'summarize.py'),'--data',str(a.out)],check=True)
    return 0

if __name__=='__main__':raise SystemExit(main())
