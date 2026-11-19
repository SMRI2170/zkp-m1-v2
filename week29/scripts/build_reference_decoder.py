#!/usr/bin/env python3
"""Fetch hash-pinned upstream C sources and build the offline-only test decoder."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import urllib.request

ROOT=Path(__file__).resolve().parents[2]


def main():
    metadata=json.loads((ROOT/'week29/results/b-initial-audit/reference-source.json').read_text())
    out=ROOT/'.cache/week29-odid-reference'
    out.mkdir(parents=True,exist_ok=True)
    for name,expected in metadata['files'].items():
        if name not in ['opendroneid.h','opendroneid.c']:
            raise ValueError('Unexpected pinned source')
        path=out/name
        if path.is_symlink():raise ValueError('Source symlink rejected')
        if path.exists():data=path.read_bytes()
        else:
            url='https://raw.githubusercontent.com/opendroneid/opendroneid-core-c/'+metadata['commit']+'/libopendroneid/'+name
            with urllib.request.urlopen(url,timeout=30) as response:data=response.read(2*1024*1024)
        if hashlib.sha256(data).hexdigest()!=expected:raise ValueError('Pinned source hash mismatch: '+name)
        if not path.exists():path.write_bytes(data)
    target=out/'decode'
    if target.is_symlink():raise ValueError('Decoder symlink rejected')
    subprocess.run([os.environ.get('CC','cc'),'-O1','-Wall','-Wextra','-DODID_DISABLE_PRINTF',
                    '-I',str(out),str(ROOT/'week29/scripts/odid_reference_decode.c'),
                    str(out/'opendroneid.c'),'-lm','-o',str(target)],check=True,timeout=120)
    print('Built hash-pinned offline reference decoder; production admission unchanged')


if __name__=='__main__':main()
