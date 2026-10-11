"""Adversarial certificate checks using fresh disposable local keys and state."""
from pathlib import Path
import json
import shutil
from replica import Replica
from run import BASE, ROOT

work=ROOT/'.cache/week23/private/quorum-security-v1'
work.mkdir(mode=0o700)
source=BASE/'normal'
for name in ['config.json',*[str(i)+'.key' for i in range(4)]]:shutil.copy(source/name,work/name)
replicas=[Replica(work,i) for i in range(4)]
config=replicas[0].config
x={**{k:config[k] for k in ('slot','epoch','policy','height','parent')},'evidence':config['verified_evidence'][0]}
y={**x,'evidence':config['verified_evidence'][1]}
rows=[]
def reject(name,request):
    try:replicas[1].receive(request)
    except Exception as error:rows.append({'case':name,'rejected':True,'reason':str(error) or type(error).__name__});return
    raise AssertionError(name+' unexpectedly accepted')
for field,value in [('slot','another-session'),('epoch',999),('policy',0),('parent','1'*64),('evidence','2'*64)]:
    bad={**x,field:value};reject('wrong-'+field,{'action':'prepare','proposal':replicas[0].signed('proposal',bad)})
reject('wrong-leader',{'action':'prepare','proposal':replicas[2].signed('proposal',x)})
reject('mixed-prepare-QC',{'action':'commit','qc':[replicas[0].signed('prepare',x),replicas[2].signed('prepare',x),replicas[3].signed('prepare',y)]})
reject('duplicate-prepare-QC',{'action':'commit','qc':[replicas[0].signed('prepare',x)]*3})
reject('wrong-phase-QC',{'action':'commit','qc':[r.signed('commit',x) for r in replicas[:3]]})
reject('two-vote-decision',{'action':'decide','qc':[r.signed('commit',x) for r in replicas[:2]]})
(ROOT/'week23/logs/quorum-security.json').write_text(json.dumps({'tests':rows},indent=2)+'\n')
print('10 adversarial quorum certificate checks passed')
