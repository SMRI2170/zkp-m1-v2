"""Validate source snapshots and metadata only; never claim real CLI proofs."""
import hashlib,json
from pathlib import Path
import render
ROOT=Path(__file__).resolve().parents[2]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    manifest=json.loads((ROOT/'week24/manifests/balanced-cli.json').read_text())
    for name,expected in manifest['file_sha256'].items():assert sha(ROOT/name)==expected,name
    for framework in ['circom','noir']:
        s,meta=render.render(framework);base=Path(__file__).with_name('rendered')/framework
        code=base/('bench.cjs' if framework=='circom' else 'bench.py')
        saved=json.loads((base/'metadata.json').read_text())
        assert code.read_text()==s
        assert saved['rendered_sha256']==sha(code) and saved['renderer_sha256']==sha(Path(render.__file__))
        assert all(saved[k]==v for k,v in meta.items()) and saved['proof_executed'] is False
    print('Balanced CLI source snapshots verified: 7 warmups + 21 measurements; actual CLI/Pi proofs not executed.')
if __name__=='__main__':main()
