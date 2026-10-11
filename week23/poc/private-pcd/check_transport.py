"""Check only the proof/public transport; setup keys remain private/local."""
from pathlib import Path
import subprocess,json,hashlib,os
root=Path(__file__).resolve().parents[3]
base=root/'.cache/week23/private/pcd'
rows=[]
for stage in [1,2,3]:
    p=base/str(stage)
    if not (p/'proof.bin').exists():continue
    files={name:{'bytes':(p/name).stat().st_size,'sha256':hashlib.sha256((p/name).read_bytes()).hexdigest()} for name in ['proof.bin','public.bin']}
    # Original private assignment is never serialized. This structural check is not a ZK proof.
    raw=(p/'proof.bin').read_bytes()+(p/'public.bin').read_bytes()
    matches=0
    for prior in range(1,stage):
        for value in [100000+prior*100+1,100000+prior*100+3,1200,900,300 if prior<3 else 5000]:
            matches+=sum(value.to_bytes(32,endian) in raw for endian in ['big','little'])
    rows.append({'stage':stage,'transport':files,'bytes':sum(v['bytes'] for v in files.values()),'private_assignment_cached':False,'prior_canary_scalar_byte_matches':matches,'scan_scope':'synthetic exact-byte canary test, not a ZK security proof'})
    assert matches==0
    forged=base/f'tampered-{stage}'
    forged.mkdir(mode=0o700,exist_ok=False)
    for name in ['vk.bin','public.bin']:(forged/name).symlink_to(p/name)
    b=bytearray((p/'proof.bin').read_bytes());b[10]^=1
    (forged/'proof.bin').write_bytes(b);(forged/'proof.bin').chmod(0o600)
    # The verify command resolves BASE/STAGE; use a separate BASE with stage-numbered path.
    wrap=base/f'tamper-run-{stage}';wrap.mkdir(mode=0o700);(wrap/str(stage)).symlink_to(forged)
    result=subprocess.run([str(root/'.cache/week23/private-pcd'),'verify',str(wrap),str(stage)],capture_output=True,text=True,env={**os.environ,'GOMAXPROCS':'2'})
    rows.append({'stage':stage,'case':'tampered-proof-byte','rejected':result.returncode!=0,'exit_code':result.returncode})
    assert result.returncode!=0
out=root/'week23/logs/private-pcd-transport.json'
out.write_text(json.dumps(rows,indent=2)+'\n');print(json.dumps(rows))
