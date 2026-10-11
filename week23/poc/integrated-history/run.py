"""Local ZKP verification -> unanimous receipt signatures -> Besu digest history."""
from pathlib import Path
import hashlib
import json
import os
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'besu-local'))
import native_qbft as network
from receipt_worker import sha

ROOT = network.ROOT
HERE = Path(__file__).resolve().parent
network.BASE = ROOT / '.cache/week23/private/integrated-history-v1'

def experiment(keyfile):
    work = network.BASE
    pins = {}
    manifests = {}
    for kind, label, stages, directory in (
        ('individual', 'individual', [1,2,3], ROOT / '.cache/week23/private/baseline'),
        ('recursive', 'recursive', [3], ROOT / '.cache/week23/private/pcd'),
        ('recursive', 'normal', [3], ROOT / '.cache/week23/private/pcd-fork-normal'),
        ('recursive', 'outlier', [3], ROOT / '.cache/week23/private/pcd-fork-outlier')):
        entries=[]
        for stage in stages:
            source = directory / str(stage) if label in ('individual','recursive') else directory
            trusted = ROOT / '.cache/week23/private' / ('baseline' if kind == 'individual' else 'pcd') / str(stage) / 'vk.bin'
            pins[kind+'-'+str(stage)] = sha(trusted)
            entries.append({'stage': stage, **{n:str(source / (n+'.bin')) for n in ('proof','public')}})
        path = work / (label+'.json')
        path.write_text(json.dumps({'kind':kind,'artifacts':entries}))
        manifests[label] = str(path)
    (work / 'trusted-vks.json').write_text(json.dumps(pins))
    original = json.loads(Path(manifests['individual']).read_text())
    for name in ('proof','public'):
        bad = json.loads(json.dumps(original))
        data = bytearray(Path(bad['artifacts'][0][name]).read_bytes())
        data[-1] ^= 1
        target = work / ('tampered-'+name+'.bin')
        target.write_bytes(data)
        bad['artifacts'][0][name] = str(target)
        path = work / ('tampered-'+name+'.json')
        path.write_text(json.dumps(bad))
        manifests['tampered-'+name] = str(path)
    code = HERE.joinpath('experiment.cjs').read_text()
    env = {'KEYFILE':str(keyfile),'PRIVATE':str(work),'SOURCE':str(HERE/'VerifiedHistory.sol'),
           'WORKER':str(HERE/'receipt_worker.py'),'MANIFESTS':json.dumps(manifests)}
    prefix = ''.join('process.env.W23_'+key+'='+json.dumps(value)+';' for key,value in env.items())
    result = json.loads(network.node_js(prefix+code))
    result.update({'host':'one Mac arm64, four loopback Besu validators, one operator',
                   'besu_version':'26.9.0', 'proof_generation':'previous synthetic fixtures; reverified now, no new setup/prove',
                   'guarantee':'onchain verifies receipt signatures/digests, NOT Groth16 or physical truth'})
    (ROOT/'week23/logs/integrated-history.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))

if __name__ == '__main__':
    network.main(experiment)
