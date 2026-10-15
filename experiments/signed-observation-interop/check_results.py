# coding: utf-8
"""Validate recorded interoperability scope and source hashes, never infer a proof."""
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]

def main():
    manifest=json.loads((ROOT/'week24/manifests/signed-observation-interop.json').read_text())
    for name,digest in manifest['file_sha256'].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest,name
    run=ROOT/'week24/logs/signed-observation-interop/native-v2'
    result=json.loads((run/'results.json').read_text())
    assert result['all_matched'] and result['private_vectors_saved'] is False and result['proof_generated'] is False
    cases=result['cases'];assert len(cases)==40
    for n,total in [(1,12),(2,14),(4,14)]:
        group=[x for x in cases if x['observation_count']==n]
        assert len(group)==total and sum(x['accepted'] for x in group)==1
        assert all(x['accepted']==x['expected'] for x in group)
        assert all(x['accepted']==(x['case']=='normal') for x in group)
    meta=json.loads((run/'metadata.json').read_text())
    for key in ['baseline_source_sha256','implementation_source_sha256']:
        for name,digest in meta[key].items():
            assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest,name
    assert meta['pi_executed'] is False and meta['proof_generated'] is False
    rv=json.loads((ROOT/'week24/logs/signed-observation-interop/riscv-check.json').read_text())
    assert rv['exit_code']==0 and rv['target']=='riscv64imac-unknown-none-elf'
    assert rv['proof_generated'] is False and rv['pi_executed'] is False
    assert rv['core_source_sha256']==hashlib.sha256((ROOT/'experiments/signed-observation-interop/core/src/lib.rs').read_bytes()).hexdigest()
    print('Interop: native Go/Rust 40 matched (3 accepted/37 rejected), RV64 library check only; no Jolt/Pi proof claim.')

if __name__=='__main__':main()
