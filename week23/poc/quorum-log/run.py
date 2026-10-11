"""Independent replica processes, injected delivery schedule, actual Ed25519 QCs."""
from pathlib import Path
import base64
import json
import os
import subprocess
import sys
import time
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding,PublicFormat,PrivateFormat,NoEncryption
from replica import canon

os.umask(0o077)
ROOT=Path(__file__).resolve().parents[3]
BASE=ROOT/'.cache/week23/private/quorum-log-v1'
HERE=Path(__file__).resolve().parent
class Harness:
    def __init__(self,name):
        self.directory=BASE/name;self.directory.mkdir(mode=0o700)
        log=json.loads((ROOT/'week23/logs/integrated-history.json').read_text())
        hashes={r['kind']:r['evidence_sha256'] for r in log['verified_certificates']}
        self.x,self.y=hashes['normal'],hashes['outlier']
        roster={}
        for i in range(4):
            key=Ed25519PrivateKey.generate();(self.directory/(str(i)+'.key')).write_bytes(key.private_bytes(Encoding.Raw,PrivateFormat.Raw,NoEncryption()))
            roster[str(i)]=base64.b64encode(key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)).decode()
        self.config={'roster':roster,'slot':log['session_golden_vectors']['recursive'],'epoch':2,'policy':20261011,'height':1,'parent':'0'*64,'verified_evidence':[self.x,self.y]}
        (self.directory/'config.json').write_bytes(canon(self.config))
        self.processes={};self.bytes=0;self.messages=0
        for i in range(4): self.start(i)
    def start(self,i): self.processes[i]=subprocess.Popen([sys.executable,str(HERE/'replica.py'),str(self.directory),str(i)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
    def stop(self,i):
        p=self.processes.pop(i);p.stdin.close();p.wait(timeout=5);p.stdout.close()
    def close(self):
        for i in list(self.processes): self.stop(i)
    def ask(self,i,request):
        data=canon(request);self.bytes+=len(data);self.messages+=1
        p=self.processes[i];p.stdin.write(data.decode()+'\n');p.stdin.flush();line=p.stdout.readline();assert line
        self.bytes+=len(line.encode());return json.loads(line)
    def ok(self,i,request):
        result=self.ask(i,request);assert result['ok'],result;return result['result']
    def body(self,candidate): return {**{k:self.config[k] for k in ('slot','epoch','policy','height','parent')},'evidence':candidate}
    def proposal(self,candidate): return self.ok(0,{'action':'propose','body':self.body(candidate)})
    def finish(self,proposal,active):
        prepares=[self.ok(i,{'action':'prepare','proposal':proposal}) for i in active]
        commits=[self.ok(i,{'action':'commit','qc':prepares}) for i in active]
        decisions=[self.ok(i,{'action':'decide','qc':commits}) for i in active]
        assert len({d['decision_sha256'] for d in decisions})==1
        return prepares,commits,decisions

def main():
    BASE.mkdir(mode=0o700)
    rows=[]
    for case in ('normal','one-follower-offline','two-offline','leader-offline','partition-2-2','partition-3-1','delay-reorder-replay','byzantine-equivocation','restart-lock','invalid-signature'):
        h=Harness(case);start=time.monotonic();detail={}
        try:
            if case=='leader-offline':
                h.stop(0);detail={'progress':False,'reason':'fixed leader; no view change implemented'}
            elif case=='two-offline':
                proposal=h.proposal(h.x);h.stop(2);h.stop(3)
                prepares=[h.ok(i,{'action':'prepare','proposal':proposal}) for i in (0,1)]
                assert not h.ask(0,{'action':'commit','qc':prepares})['ok'];detail={'progress':False,'quorum_rejected':True}
            elif case=='partition-2-2':
                px=h.proposal(h.x);py=h.proposal(h.y)
                ax=[h.ok(i,{'action':'prepare','proposal':px}) for i in (0,1)]
                ay=[h.ok(i,{'action':'prepare','proposal':py}) for i in (2,3)]
                assert not h.ask(0,{'action':'commit','qc':ax})['ok'];assert not h.ask(2,{'action':'commit','qc':ay})['ok']
                detail={'progress':False,'two_competing_minority_qcs_rejected':True,'healed_liveness':'not guaranteed without a view-change/unlock protocol'}
            elif case=='byzantine-equivocation':
                px=h.proposal(h.x);py=h.proposal(h.y)
                ax=[h.ok(i,{'action':'prepare','proposal':px}) for i in (0,1,2)]
                ay=[h.ok(3,{'action':'prepare','proposal':py})]
                assert not h.ask(1,{'action':'prepare','proposal':py})['ok'];assert not h.ask(3,{'action':'commit','qc':ay})['ok']
                commits=[h.ok(i,{'action':'commit','qc':ax}) for i in (0,1,2)]
                ds=[h.ok(i,{'action':'decide','qc':commits}) for i in (0,1,2)]
                assert len({d['evidence'] for d in ds})==1;detail={'one_decision':True,'conflicting_vote_refused':True}
            elif case=='restart-lock':
                px=h.proposal(h.x);py=h.proposal(h.y);h.ok(1,{'action':'prepare','proposal':px});h.stop(1);h.start(1)
                assert not h.ask(1,{'action':'prepare','proposal':py})['ok'];detail={'restart_double_vote_refused':True}
            elif case=='invalid-signature':
                px=h.proposal(h.x);px['body']['evidence']=h.y
                assert not h.ask(1,{'action':'prepare','proposal':px})['ok'];detail={'modified_signed_proposal_rejected':True}
            else:
                active=[0,1,2,3]
                if case in ('one-follower-offline','partition-3-1'): active=[0,1,2]
                if case=='one-follower-offline': h.stop(3)
                p=h.proposal(h.x)
                if case=='delay-reorder-replay':
                    time.sleep(.2);active=[2,0,3,1]
                prepares,commits,decisions=h.finish(p,active)
                if case=='delay-reorder-replay':
                    replay=h.ok(1,{'action':'decide','qc':commits});assert replay==decisions[0]
                    assert not h.ask(1,{'action':'commit','qc':[prepares[0]]*3})['ok']
                if case=='partition-3-1':
                    catchup=h.ok(3,{'action':'decide','qc':commits});assert catchup==decisions[0]
                detail={'progress':True,'same_decision':True,'deciding_replicas':len(active),'minority_catchup':case=='partition-3-1','replay_idempotent':case=='delay-reorder-replay'}
            rows.append({'case':case,**detail,'wall_ms':(time.monotonic()-start)*1000,'ipc_request_response_bytes':h.bytes,'ipc_request_count':h.messages})
        finally: h.close()
    result={'replicas':4,'quorum':3,'protocol':'fixed-leader, two-phase signed receipt quorum log; NO blockchain, view-change or general PBFT claim','tests':rows,'inputs':'same independently verified recursive normal/outlier receipt hashes from integrated-history.json','network':'coordinator-controlled delivery schedule to four independent local processes; no measured real WAN','limits':['Transport bytes include JSON/stdio harness requests, not WAN protocol traffic','A first prepare vote locks the slot permanently; safety is conservative, liveness can stall after split votes','Leader failure does not recover: no view change','Uses locally preverified receipts as application precondition; no new proof generation','Not independent operators, production BFT, sensor truth or hardware authentication']}
    (ROOT/'week23/logs/quorum-log.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__': main()
