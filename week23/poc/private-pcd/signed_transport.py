"""Transport tests over locally generated recursive proofs. No proof is regenerated here."""
from pathlib import Path
import base64,hashlib,json,os,subprocess,sys
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey,Ed25519PublicKey
from cryptography.hazmat.primitives import serialization
root=Path(__file__).resolve().parents[3]
base=root/'.cache/week23/private/pcd'
transport=root/'.cache/week23/private/signed-transport'
binary=root/'.cache/week23/private-pcd-bench'
def canon(o):return json.dumps(o,sort_keys=True,separators=(',',':')).encode()
def save(p,b):
    fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'wb') as f:f.write(b)
def verify_packet(packet,roster,now=100002,seen=False):
    body=packet['body'];key=Ed25519PublicKey.from_public_bytes(base64.b64decode(roster[str(body['stage'])]))
    key.verify(base64.b64decode(packet['signature']),canon(body))
    assert (body['session'],body['policy'],body['rid'],body['bucket'])==(777,20261011,424242,100001)
    assert body['bucket']<=now<=body['bucket']+2
    assert not seen

def worker(stage):
    roster=json.loads((transport/'roster.json').read_text())
    incoming=False;previous=None
    if stage>1:
        packet=json.loads((transport/f'{stage-1}.json').read_text())
        verify_packet(packet,roster)
        assert packet['body']['stage']==stage-1
        # Reconstruct only proof+public; independently trusted VK is local setup metadata.
        incoming_dir=transport/f'incoming-{stage}'
        incoming_dir.mkdir(mode=0o700);p=incoming_dir/str(stage-1);p.mkdir(mode=0o700)
        for name in ['proof','public']:save(p/f'{name}.bin',base64.b64decode(packet['body'][name]))
        (p/'vk.bin').symlink_to(base/str(stage-1)/'vk.bin')
        subprocess.run([str(binary),'verify',str(incoming_dir),str(stage-1)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        incoming=True;previous=hashlib.sha256(canon(packet)).hexdigest()
    subprocess.run([str(binary),'verify',str(base),str(stage)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    body={'stage':stage,'session':777,'policy':20261011,'rid':424242,'bucket':100001,'previous_packet_sha256':previous}
    for name in ['proof','public']:body[name]=base64.b64encode((base/str(stage)/f'{name}.bin').read_bytes()).decode()
    key=Ed25519PrivateKey.from_private_bytes((transport/f'{stage}.key').read_bytes())
    packet={'body':body,'signature':base64.b64encode(key.sign(canon(body))).decode()}
    verify_packet(packet,roster)
    save(transport/f'{stage}.json',canon(packet))
    print(json.dumps({'stage':stage,'pid':os.getpid(),'incoming_signature_and_proof_verified':incoming,'own_proof_verified':True,'packet_bytes':len(canon(packet)),'original_assignment_transferred':False}))

def main():
    transport.mkdir(mode=0o700) # preserve prior experiments; no cleanup/reuse
    roster={}
    for stage in [1,2,3]:
        key=Ed25519PrivateKey.generate()
        save(transport/f'{stage}.key',key.private_bytes(serialization.Encoding.Raw,serialization.PrivateFormat.Raw,serialization.NoEncryption()))
        roster[str(stage)]=base64.b64encode(key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)).decode()
    save(transport/'roster.json',canon(roster))
    rows=[]
    for stage in [1,2,3]:
        r=subprocess.run([sys.executable,__file__,'worker',str(stage)],check=True,capture_output=True,text=True)
        rows.append(json.loads(r.stdout))
    packet=json.loads((transport/'3.json').read_text())
    tests=[]
    for case in ['payload','session','policy','expired','replay']:
        altered=json.loads(json.dumps(packet));now=100002;seen=False
        if case=='payload':altered['body']['proof']='AA=='
        if case=='session':altered['body']['session']=778
        if case=='policy':altered['body']['policy']=0
        if case=='expired':now=100004
        if case=='replay':seen=True
        try:verify_packet(altered,roster,now,seen)
        except Exception:rejected=True
        else:rejected=False
        tests.append({'case':case,'rejected':rejected,'scope':'transport signature/host gate'})
        assert rejected
    # Two independently verified branches can coexist; signatures and PCD do not select one history.
    fork_key=Ed25519PrivateKey.from_private_bytes((transport/'3.key').read_bytes())
    fork=json.loads(json.dumps(packet));fork['body']['branch']='second-local-branch'
    fork['signature']=base64.b64encode(fork_key.sign(canon(fork['body']))).decode()
    verify_packet(fork,roster)
    result={'workers':rows,'negative_transport_tests':tests,'forked_signed_envelopes_both_valid':True,'fixture_keys':'local owner-only; never release','proof_generation_scope':'separate Go prove processes; this harness signs/transfers completed proofs'}
    (root/'week23/logs/private-pcd-signed-transport.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))
if __name__=='__main__':
    if len(sys.argv)>1:worker(int(sys.argv[2]))
    else:main()
