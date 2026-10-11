"""Bounded fixed-leader two-phase quorum log, n=4/q=3. Not PBFT/view-change.
Each replica is a separate process with a durable vote/decision file.
"""
from pathlib import Path
import base64
import hashlib
import json
import os
import sys
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

os.umask(0o077)
def canon(x): return json.dumps(x, sort_keys=True, separators=(',', ':')).encode()

class Replica:
    def __init__(self, directory, index):
        self.directory, self.index = Path(directory), index
        self.config = json.loads((self.directory/'config.json').read_text())
        self.key = Ed25519PrivateKey.from_private_bytes((self.directory/(str(index)+'.key')).read_bytes())
        self.path = self.directory/(str(index)+'.state.json')
        self.state = json.loads(self.path.read_text()) if self.path.exists() else {'vote':None,'commit':None,'decision':None}
    def save(self):
        tmp=self.path.with_suffix('.tmp')
        with tmp.open('wb') as f: f.write(canon(self.state)); f.flush(); os.fsync(f.fileno())
        os.replace(tmp,self.path)
        fd=os.open(self.directory,os.O_RDONLY)
        try: os.fsync(fd)
        finally: os.close(fd)
    def signed(self, phase, body):
        payload={'domain':'week23-quorum-log-v1','phase':phase,'sender':self.index,'body':body}
        return {**payload,'signature':base64.b64encode(self.key.sign(canon(payload))).decode()}
    def valid(self, message, phase):
        if message['domain']!='week23-quorum-log-v1' or message['phase']!=phase: raise ValueError('domain/phase')
        i=message['sender']
        if type(i)!=int or not 0<=i<4: raise ValueError('unknown replica')
        payload={k:v for k,v in message.items() if k!='signature'}
        Ed25519PublicKey.from_public_bytes(base64.b64decode(self.config['roster'][str(i)])).verify(base64.b64decode(message['signature']),canon(payload))
        return message['body']
    def check(self, body):
        expected={k:self.config[k] for k in ('slot','epoch','policy','height','parent')}
        if any(body[k]!=v for k,v in expected.items()): raise ValueError('session/epoch/policy/history')
        if body['evidence'] not in self.config['verified_evidence']: raise ValueError('not a verified evidence receipt')
    def qc(self, messages, phase):
        if len(messages)<3: raise ValueError('no quorum')
        if len({m['sender'] for m in messages})!=len(messages): raise ValueError('duplicate vote')
        bodies=[self.valid(m,phase) for m in messages]
        if any(b!=bodies[0] for b in bodies): raise ValueError('mixed candidates')
        self.check(bodies[0]); return bodies[0]
    def receive(self, request):
        phase=request['action']
        if phase=='status': return self.state
        if phase=='propose':
            body=request['body']; self.check(body)
            if self.index!=0: raise ValueError('fixed leader only')
            # Deliberate Byzantine leader mode exists only in fault injection tests.
            return self.signed('proposal',body)
        if phase=='prepare':
            body=self.valid(request['proposal'],'proposal');self.check(body)
            if request['proposal']['sender']!=0: raise ValueError('wrong leader')
            if self.state['vote'] is not None and self.state['vote']!=body: raise ValueError('durable double-vote refusal')
            self.state['vote']=body;self.save();return self.signed('prepare',body)
        if phase=='commit':
            body=self.qc(request['qc'],'prepare')
            if self.state['vote'] is not None and self.state['vote']!=body: raise ValueError('locked competing vote')
            if self.state['commit'] is not None and self.state['commit']!=body: raise ValueError('double commit')
            self.state['vote']=body;self.state['commit']=body;self.save();return self.signed('commit',body)
        if phase=='decide':
            body=self.qc(request['qc'],'commit')
            if self.state['commit'] is not None and self.state['commit']!=body: raise ValueError('conflicting decision')
            if self.state['decision'] is not None and self.state['decision']!=body: raise ValueError('decided')
            self.state['vote']=body;self.state['commit']=body;self.state['decision']=body;self.save()
            return {'decision_sha256':hashlib.sha256(canon(body)).hexdigest(),'evidence':body['evidence']}
        raise ValueError('unknown action')

if __name__=='__main__':
    replica=Replica(sys.argv[1],int(sys.argv[2]))
    for line in sys.stdin:
        try: result={'ok':True,'result':replica.receive(json.loads(line))}
        except Exception as error: result={'ok':False,'reason':str(error) or type(error).__name__}
        print(json.dumps(result),flush=True)
