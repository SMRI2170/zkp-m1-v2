"""Issue #61: balanced CLI drivers, preserving archived relation and rejection tests."""
import argparse
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]

def replace_once(s,old,new):
    if s.count(old)!=1:raise ValueError('source shape changed: '+old)
    return s.replace(old,new)

def render(framework):
    name={'circom':'circom/bench.cjs','noir':'noir/bench.py'}[framework]
    source=ROOT/'experiments/pi4-euclidean'/name
    expected=json.loads((ROOT/'week24/manifests/euclidean-frameworks.json').read_text())['source_sha256'][name]
    if hashlib.sha256(source.read_bytes()).hexdigest()!=expected:raise ValueError('archived source hash mismatch')
    s=source.read_text()
    if framework=='circom':
        s=replace_once(s,'for(let i=0;i<cases.length;i++){','for(let sample_id=0;sample_id<28;sample_id++){\n   const i=sample_id%7;')
        s=replace_once(s,"phase:'sample',case_id:i,", "phase:'sample',case_id:i,sample_id,warmup:sample_id<7,repetition:sample_id<7?null:Math.floor((sample_id-7)/7),")
        s=replace_once(s,"proof_json_bytes:fs.statSync(path.join(tmp,'proof.json')).size", "proof_json_bytes:fs.statSync(path.join(tmp,'proof.json')).size,proof_bytes:fs.statSync(path.join(tmp,'proof.json')).size,public_bytes:fs.statSync(path.join(tmp,'public.json')).size,proof_encoding:'JSON'")
        s=replace_once(s,"phase:'summary',samples:7,", "phase:'summary',samples:21,warmups:7,protocol:'distance-u16-balanced-v1',")
    else:
        s=replace_once(s,'for i,a in enumerate(CASES):','for sample_id in range(28):\n        i=sample_id%7; a=CASES[i]')
        s=replace_once(s,"out=work/f'proof-{i}'","out=work/f'proof-{sample_id}'")
        s=replace_once(s,"'phase':'sample','case_id':i,", "'phase':'sample','case_id':i,'sample_id':sample_id,'warmup':sample_id<7,'repetition':None if sample_id<7 else (sample_id-7)//7,")
        s=replace_once(s,"'execute_compile_witness_ms':wms,'prove_with_vk_ms':pms,", "'execute_compile_witness_ms':wms,'prove_with_vk_ms':pms,'witness_ms':wms,'prove_ms':pms,")
        s=replace_once(s,"'proof_bytes':len(proof),", "'proof_bytes':len(proof),'public_bytes':(out/'public_inputs').stat().st_size,'proof_encoding':'native bb UltraHonk',")
        s=replace_once(s,"'phase':'summary','samples':7,", "'phase':'summary','samples':21,'warmups':7,'protocol':'distance-u16-balanced-v1',")
    return s,{'archived_source':str(source.relative_to(ROOT)),'archived_source_sha256':expected,
              'framework':framework,'protocol':'distance-u16-balanced-v1','warmups':7,'measured_samples':21,
              'phase_notes':{'circom':'WASM witness timer excludes WTNS write; prove/verify include native CLI launch; fixture setup on Mac',
                             'noir':'execute includes compile/witness; prove includes VK generation; CLI launch included; not a setup-excluded steady prover timer'}[framework]}

def main():
    p=argparse.ArgumentParser();p.add_argument('framework',choices=['circom','noir']);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    s,meta=render(a.framework)
    a.out.mkdir(parents=True,exist_ok=False)
    file=a.out/('bench.cjs' if a.framework=='circom' else 'bench.py');file.write_text(s)
    meta.update(rendered_sha256=hashlib.sha256(file.read_bytes()).hexdigest(),renderer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),proof_executed=False)
    (a.out/'metadata.json').write_text(json.dumps(meta,indent=2)+'\n')
    print(json.dumps(meta))
if __name__=='__main__':main()
