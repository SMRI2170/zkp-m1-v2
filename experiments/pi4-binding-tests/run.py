# coding: utf-8
"""Run extra solver tests against hash-pinned original source without editing baseline."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
SOURCE=ROOT/'experiments/pi4-euclidean-evaluation/workload'

def main():
    manifest=json.loads((ROOT/'week24/manifests/euclidean-evaluation.json').read_text())['file_sha256']
    cache=ROOT/'.cache/week24';cache.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='binding-tests-',dir=cache) as d:
        target=Path(d)
        for name in ['main.go','main_test.go','go.mod','go.sum']:
            path=SOURCE/name
            assert hashlib.sha256(path.read_bytes()).hexdigest()==manifest[str(path.relative_to(ROOT))],name
            shutil.copyfile(path,target/name)
        shutil.copyfile(HERE/'extra_test.go',target/'extra_test.go')
        return subprocess.run(['go','test','-count=1','-v','./...'],cwd=target).returncode

if __name__=='__main__':raise SystemExit(main())
