"""Create fresh, private, single-contributor Groth16 TEST fixture on host only."""
import argparse,hashlib,json,os,secrets,shutil,subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('fixture',type=Path);a=p.parse_args()
os.umask(0o077);a.fixture.mkdir(mode=0o700)
source=Path(__file__).with_name('euclidean.circom').resolve()
def run(args):subprocess.run(list(map(str,args)),check=True,stdout=subprocess.DEVNULL)
run(['circom',source,'--r1cs','--wasm','-o',a.fixture])
f=a.fixture
run(['snarkjs','powersoftau','new','bn128','10',f/'initial.ptau'])
# Never reuse the uncontributed initial Powers of Tau or zkey: degenerate ICs
# can accept changed publics. Contribution entropy remains in process memory.
run(['snarkjs','powersoftau','contribute',f/'initial.ptau',f/'contributed.ptau','--name=local-disposable-test','-e='+secrets.token_hex(64)])
run(['snarkjs','powersoftau','prepare','phase2',f/'contributed.ptau',f/'phase2.ptau'])
run(['snarkjs','powersoftau','verify',f/'phase2.ptau'])
run(['snarkjs','groth16','setup',f/'euclidean.r1cs',f/'phase2.ptau',f/'initial.zkey'])
run(['snarkjs','zkey','contribute',f/'initial.zkey',f/'local.zkey','--name=local-disposable-test','-e='+secrets.token_hex(64)])
run(['snarkjs','zkey','verify',f/'euclidean.r1cs',f/'phase2.ptau',f/'local.zkey'])
run(['snarkjs','zkey','export','verificationkey',f/'local.zkey',f/'vk.json'])
names=['local.zkey','vk.json','euclidean.r1cs','euclidean_js/euclidean.wasm','euclidean_js/witness_calculator.js']
manifest={'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
 'phase1_contributed':True,'phase2_contributed':True,'zkey_verified':True,
 'scope':'disposable single-contributor test-only; never publish/deploy',
 'files':{n:hashlib.sha256((f/n).read_bytes()).hexdigest() for n in names}}
(f/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
for path in f.rglob('*'):os.chmod(path,0o700 if path.is_dir() else 0o600)
print(json.dumps({'phase':'setup','test_only':True,'phase1_contributed':True,'phase2_contributed':True,'zkey_verified':True,'source_sha256':manifest['source_sha256']}))
