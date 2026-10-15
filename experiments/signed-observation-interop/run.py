# coding: utf-8
"""Pipe fresh synthetic Go assignments into Rust; export only verdicts and metadata."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
SOURCE=ROOT/'experiments/pi4-euclidean-evaluation/workload'

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();os.umask(0o077);a.out.mkdir(parents=True) # no overwrite of previous evidence
    expected=json.loads((ROOT/'week24/manifests/euclidean-evaluation.json').read_text())['file_sha256']
    provenance={}
    cache=ROOT/'.cache/week24';cache.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='interop-go-',dir=cache) as d:
        tmp=Path(d)
        for name in ['main.go','go.mod','go.sum']:
            path=SOURCE/name;digest=hashlib.sha256(path.read_bytes()).hexdigest()
            assert digest==expected[str(path.relative_to(ROOT))],name
            provenance[str(path.relative_to(ROOT))]=digest
            shutil.copyfile(path,tmp/name)
        shutil.copyfile(HERE/'go/interop_test.go',tmp/'interop_test.go')
        subprocess.run(['go','test','-c','-o',str(tmp/'fixtures')],cwd=tmp,check=True)
        subprocess.run(['cargo','+1.97.1','build','--manifest-path',str(HERE/'core/Cargo.toml'),
                        '--example','check_vectors','--locked','-j','1'],check=True)
        start=time.monotonic()
        fixture=subprocess.Popen([str(tmp/'fixtures'),'-test.run','^TestEmitInterop$'],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:
            rust=subprocess.run([str(HERE/'core/target/debug/examples/check_vectors')],stdin=fixture.stdout,capture_output=True,timeout=120)
            fixture.stdout.close()
            _,go_error=fixture.communicate(timeout=30)
        finally:
            if fixture.poll() is None:fixture.kill();fixture.wait()
        if fixture.returncode or rust.returncode:
            # Keep diagnostic stderr private on failure; never print or export the assignment stream.
            private=cache/'interop-failure';private.mkdir(mode=0o700,exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=private,delete=False) as f:f.write(go_error+rust.stderr)
            raise SystemExit('Interop failed; inspect ignored owner-only diagnostic, no vector bodies exported')
        result=json.loads(rust.stdout)
        assert result['all_matched'] and len(result['cases'])==40
        assert sum(x['accepted'] for x in result['cases'])==3
        result['elapsed_native_crosscheck_s']=time.monotonic()-start
        result['scope']='Go constraint solver/envelope versus native Rust verifier; not Jolt proof generation or ZK verification'
        (a.out/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    meta={'baseline_source_sha256':provenance,
          'implementation_source_sha256':{str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(HERE.rglob('*')) if f.is_file() and f.suffix in ['.py','.rs','.toml','.lock','.go'] and 'target' not in f.parts and '__pycache__' not in f.parts},
          'go_version':subprocess.check_output(['go','version'],text=True).strip(),
          'rust_version':subprocess.check_output(['rustc','+1.97.1','--version'],text=True).strip(),
          'private_vectors_transport':'anonymous pipe only; no fixture files / assignments / secret keys exported',
          'key_origin':'fresh random synthetic observer key per count, generated in Go RAM',
          'native_reference_key_validation':'canonical coordinates; on-curve, nonidentity prime-subgroup public key; on-curve R; S<order',
          'baseline_circuit_key_validation':'has S<order and cofactored equation; no separate PK nonidentity/subgroup check; expected registered key must be validated externally',
          'proof_generated':False,'pi_executed':False}
    (a.out/'metadata.json').write_text(json.dumps(meta,indent=2)+'\n')
    print(json.dumps({'all_matched':True,'cases':40,'accepted':3,'rejected':37,'proof_generated':False,'private_vectors_saved':False}))

if __name__=='__main__':main()
