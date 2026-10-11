"""Prepare an isolated, pinned legacy source; never modify nova_poc."""
from pathlib import Path
import re, subprocess, hashlib, json
root = Path(__file__).resolve().parents[3]
source = root / '.cache/week23/sources/sonobe-repro'
rev = '9b7dd34f0e0341046baeabc6f900f5ee63007f18'
if not source.exists():
    subprocess.run(['git', 'clone', 'https://github.com/privacy-ethereum/sonobe.git', str(source)], check=True)
    subprocess.run(['git', '-C', str(source), 'checkout', '--detach', rev], check=True)
assert subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'], text=True).strip() == rev
p = source / 'Cargo.toml'
s = subprocess.check_output(['git','-C',str(source),'show',rev+':'+str(p.relative_to(source))], text=True)
s = re.sub(r'members = \[.*?\]', 'members = ["folding-schemes"]', s, count=1, flags=re.S)
s = re.sub(r'\[patch.crates-io\].*?(?=\[workspace.package\])', '', s, flags=re.S)
s = s.replace('^0.5.0', '=0.6.0')
p.write_text(s)
for filename in ['pedersen.rs', 'ipa.rs']:
    p = source / 'folding-schemes/src/commitment' / filename
    s = subprocess.check_output(['git','-C',str(source),'show',rev+':'+str(p.relative_to(source))], text=True)
    pattern = r'(\w+(?:\[[^\]]+\])?)\.joint_scalar_mul_be\(\s*([^,]+),\s*([^,]+),\s*([^,]+),\s*\)\?'
    def replace(m):
        a,b,x,y = [v.strip() for v in m.groups()]
        return f'({a}.scalar_mul_le({x})? + ({b}).scalar_mul_le({y})?)'
    s, count = re.subn(pattern, replace, s)
    assert 'joint_scalar_mul_be' not in s
    p.write_text(s)
patch = subprocess.check_output(['git','-C',str(source),'diff','--','Cargo.toml','folding-schemes/src/commitment'],text=True)
(root / 'week23/manifests/legacy-arkworks06.patch').write_text(patch)
print(json.dumps({'revision':rev,'patch_sha256':hashlib.sha256(patch.encode()).hexdigest()}))
