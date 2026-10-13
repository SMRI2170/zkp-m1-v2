"""Noir beta25 / bb5.2 ZK mode; ephemeral prover data in owner-only tmpfs."""
import json,os,subprocess,sys,tempfile,time,shutil
from pathlib import Path
source,nargo,bb=map(Path,sys.argv[1:])
CASES=[(0,0,0,0),(0,0,3,4),(3,4,0,0),(0,0,1,1),(0,0,65535,65535),(65535,0,0,65535),(100,100,101,100)]
from math import isqrt
os.umask(0o077)
def emit(v):print(json.dumps(v),flush=True)
def command(args,cwd):
    r=subprocess.run(list(map(str,args)),cwd=cwd,capture_output=True,text=True,timeout=120)
    if r.returncode:raise RuntimeError(f'{Path(args[0]).name} failed (exit {r.returncode}); diagnostic retained only in private tmpfs')
    return r
with tempfile.TemporaryDirectory(prefix='week24-noir-',dir='/dev/shm') as td:
    work=Path(td);shutil.copytree(source,work/'project',ignore=shutil.ignore_patterns('target','Prover.toml'))
    project=work/'project';emit({'phase':'start','os':sys.platform,'arch':os.uname().machine,'nargo':command([nargo,'--version'],project).stdout.splitlines()[0],'bb':command([bb,'--version'],project).stdout.strip()})
    command([nargo,'test'],project)
    emit({'phase':'relation','noir_unit_tests_passed':True})
    for i,a in enumerate(CASES):
        d=(a[0]-a[2])**2+(a[1]-a[3])**2;r=isqrt(d)
        (project/'Prover.toml').write_text('\n'.join(f'{k} = "{v}"' for k,v in zip(['x1','y1','x2','y2','d2','r'],[*a,d,r]))+'\n')
        t=time.monotonic();command([nargo,'execute','w'],project);wms=(time.monotonic()-t)*1000
        out=work/f'proof-{i}'
        t=time.monotonic();command([bb,'prove','-b',project/'target/euclidean.json','-w',project/'target/w.gz','-o',out,'-t','evm','--write_vk'],project);pms=(time.monotonic()-t)*1000
        t=time.monotonic();command([bb,'verify','-k',out/'vk','-p',out/'proof','-i',out/'public_inputs','-t','evm'],project);vms=(time.monotonic()-t)*1000
        proof=(out/'proof').read_bytes();mutated=bytearray(proof);mutated[0]^=1;(out/'badproof').write_bytes(mutated)
        neg=subprocess.run([str(bb),'verify','-k',str(out/'vk'),'-p',str(out/'badproof'),'-i',str(out/'public_inputs'),'-t','evm'],capture_output=True,timeout=120)
        assert neg.returncode==1,'tampered proof: expected ordinary invalid-proof exit, not crash'
        pub=bytearray((out/'public_inputs').read_bytes());pub[-1]^=1;(out/'badpublic').write_bytes(pub)
        neg=subprocess.run([str(bb),'verify','-k',str(out/'vk'),'-p',str(out/'proof'),'-i',str(out/'badpublic'),'-t','evm'],capture_output=True,timeout=120)
        assert neg.returncode==1,'changed public: expected ordinary invalid-proof exit, not crash'
        emit({'phase':'sample','case_id':i,'execute_compile_witness_ms':wms,'prove_with_vk_ms':pms,'verify_ms':vms,'proof_bytes':len(proof),'verified':True,'tampered_proof_rejected':True,'changed_public_rejected':True})
    emit({'phase':'summary','samples':7,'all_verified':True,'negative_verifier_exit_code':1,'proofs_persisted':False,'transient_artifacts':'owner-only tmpfs, removed on exit','verifier_target':'evm/ZK; no deployment'})
