"""Frozen real-RSSI comparison; raw geometry remains private. No model adoption."""
import argparse,collections,csv,hashlib,json,math,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'week29/scripts'));sys.path.insert(0,str(ROOT/'week_tmp/circuit-design/uncertainty'))
from build_quality_manifest import private_path,load_selection
from evaluate_claim_attacks import split_time,prediction,compensation
from geometry import normalize_geometry
from profile import build,decision,continuous_oracle

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def csvwrite(p,rows):
 with p.open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def main():
 p=argparse.ArgumentParser();p.add_argument('--positions-config',type=Path,required=True);p.add_argument('--selection-manifest',type=Path,required=True);p.add_argument('--private-output',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();os.umask(0o077)
 config=private_path(a.positions_config,existing=True);conf=json.loads(config.read_text());positions=private_path(conf['positions'],existing=True);manifest=private_path(a.selection_manifest,existing=True);private_path(a.private_output)
 if a.output.exists() or a.private_output.exists():raise ValueError('Fresh output directories required')
 baseline=ROOT/'week29/results/issue96-attacks-a/summary.json';card=build(baseline);embedded=ROOT/'week_tmp/circuit-design/profiles/frozen-log-envelope-2d-v1.json'
 if card!=json.loads(embedded.read_text()):raise ValueError('Frozen model profile differs from circuit embedded profile')
 sources={str(x):sha(x) for x in [config,positions,manifest,baseline,embedded]}
 with positions.open() as f:rows=list(csv.DictReader(f))
 selected=[r for r in load_selection(manifest,positions,rows) if r['node']=='Pixel'];items=[dict(source=r,boot=r['boot_scope'],time=float(r['observed_us'])/1e6,distance=float(r['claimed_horizontal_distance_m']),rssi=float(r['rssi_dbm'])) for r in selected]
 train,cal,test=split_time(items);aa,nn,tau=map(float,[card['a'],card['n'],card['threshold_db']]);old=sum(abs(x['rssi']-prediction(x['distance'],aa,nn))>tau for x in test)
 if [len(train),len(cal),len(test),old]!=[52,26,27,13]:raise ValueError('Frozen original baseline changed')
 origin=dict(latitude=float(train[0]['source']['receiver_latitude']),longitude=float(train[0]['source']['receiver_longitude']),altitude_m=0.)
 prepared=[];private=[];summaries=[];drifts=[]
 for scenario in ['nominal_point','phone_radius','phone_and_rid10','strict_unverified_time']:
  for attack in ['unmodified','away50','away50_ideal_power']:
   counts=collections.Counter();oracle_counts=collections.Counter();mismatch=extra_hold=0
   for i,item in enumerate(test):
    s=item['source'];rx=dict(latitude=float(s['receiver_latitude']),longitude=float(s['receiver_longitude']),horizontal_accuracy_m=float(s['accuracy_m']))
    claim=dict(latitude=float(s['claimed_latitude']),longitude=float(s['claimed_longitude']),horizontal_accuracy_m=10. if scenario=='phone_and_rid10' else 0.)
    normalized=normalize_geometry(rx,claim,origin,2,projection_allowance_m=.02)
    q=normalized['claim']['center_cm'][:2];o=normalized['receiver']['center_cm'][:2]
    if attack!='unmodified':
     dx,dy=q[0]-o[0],q[1]-o[1];d=math.hypot(dx,dy)
     if d==0:raise ValueError('Undefined synthetic away direction')
     q=[round(q[0]+5000*dx/d),round(q[1]+5000*dy/d)]
    rssi=float(item['rssi'])
    if attack=='away50_ideal_power':rssi+=compensation(item['distance'],item['distance']+50,nn)
    encoded=round(rssi*100)+16000
    if not 0<=encoded<=16000:raise ValueError('RSSI outside circuit representation')
    obs=dict(claim=q,observer=o,receiver_radius_cm=0 if scenario=='nominal_point' else normalized['receiver']['axis_error_cm'][0],claim_radius_cm=0 if scenario=='nominal_point' else normalized['claim']['axis_error_cm'][0],rssi=encoded,eligible=scenario!='strict_unverified_time')
    actual=decision(card,obs);oracle=continuous_oracle(card,obs);counts[actual]+=1;oracle_counts[oracle]+=1
    if actual!=2 and actual!=oracle:mismatch+=1
    if actual==2 and oracle!=2:extra_hold+=1
    obs['expected_status']=actual;prepared.append(obs)
    private.append(dict(row_index=i,scenario=scenario,attack=attack,observed_us=s['observed_us'],fix_delta_s=s['fix_delta_s'],receiver_latitude=s['receiver_latitude'],receiver_longitude=s['receiver_longitude'],claim_latitude=s['claimed_latitude'],claim_longitude=s['claimed_longitude'],phone_altitude=s['phone_altitude_m'],claimed_geo_altitude=s['drone_geo_altitude_m'],circuit_status=actual,continuous_reference_status=oracle,**obs))
    if scenario=='nominal_point' and attack=='unmodified':drifts.append(abs(math.hypot(q[0]-o[0],q[1]-o[1])/100-item['distance']))
   summaries.append(dict(scenario=scenario,attack=attack,n=27,consistent=counts[0],alarm=counts[1],hold=counts[2],oracle_consistent=oracle_counts[0],oracle_alarm=oracle_counts[1],oracle_hold=oracle_counts[2],false_definite_against_continuous_reference=mismatch,additional_hold_from_envelope=extra_hold))
 if any(x['false_definite_against_continuous_reference'] for x in summaries):raise ValueError('Unsafe envelope disagreement; do not proceed')
 for path,h in sources.items():
  if sha(path)!=h:raise ValueError('Input changed')
 a.private_output.mkdir(parents=True,mode=0o700);a.output.mkdir(parents=True)
 (a.private_output/'circuit-input-private.json').write_text(json.dumps(dict(rows=prepared)))
 (a.private_output/'paired-private.json').write_text(json.dumps(private))
 (a.private_output/'input-hashes-private.json').write_text(json.dumps(sources,indent=2))
 csvwrite(a.output/'comparison.csv',summaries)
 result=dict(scope='fixed failed model; real RSSI and claim/phone geometry; synthetic attacks and assumed spatial radii. Not real spoof TPR/FPR.',adoption='NOT_SUPPORTED_UNCHANGED',original_baseline_alarms=13,original_evaluation_rows=27,conditions=len(summaries),field_derived_constraint_inputs=len(prepared),continuous_reference_false_definite_total=0,source_hashes_unchanged=True,profile_sha256=sha(embedded),normalization_difference_from_old_horizontal_distance_m=dict(max=max(drifts),mean=sum(drifts)/len(drifts)),time_scope='strict scenario holds all; conditional scenarios assume time/epoch validity, do not synthesize measurement timestamps',height_scope='2D only; raw altitude retained privately, no 3D inference',signature_and_proof='NOT_EXECUTED_NEW_MODEL',code_sha256=sha(__file__))
 (a.output/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
 env=os.environ.copy();env.update(GOMAXPROCS='2',GOMEMLIMIT='1GiB')
 command=['go','run','./cmd/calibrated-check','--input',str((a.private_output/'circuit-input-private.json').resolve()),'--output',str((a.output/'circuit-check.json').resolve())]
 with (a.output/'circuit-check.log').open('w') as log:
  done=subprocess.run(command,cwd=ROOT/'week_tmp/circuit-design',env=env,stdout=log,stderr=subprocess.STDOUT,timeout=180)
 if done.returncode:raise ValueError('Circuit check failed; see aggregate diagnostic log')
 result['r1cs_check_executed']=True;(a.output/'summary.json').write_text(json.dumps(result,indent=2)+'\n');plot(a.output,summaries)
 print(json.dumps(dict(conditions=len(summaries),private_rows=len(prepared),false_definite=0,output=str(a.output))))

def plot(output,rows):
 import matplotlib;matplotlib.use('Agg')
 import matplotlib.pyplot as plt
 fig,axes=plt.subplots(1,3,figsize=(13,5),sharey=True)
 for ax,attack in zip(axes,['unmodified','away50','away50_ideal_power']):
  group=[r for r in rows if r['attack']==attack];bottom=[0]*len(group)
  for key,color in [('consistent','#285b8e'),('hold','#e0a93a'),('alarm','#b44d4d')]:
   vals=[r[key]/27*100 for r in group];ax.bar(range(4),vals,bottom=bottom,color=color,label=key)
   for i,(v,r) in enumerate(zip(vals,group)):
    if v:ax.text(i,bottom[i]+v/2,str(r[key]),ha='center',va='center',color='black' if key=='hold' else 'white')
   bottom=[a+b for a,b in zip(bottom,vals)]
  ax.set(title=attack.replace('_',' '),xticks=range(4),xticklabels=['Point','Phone','+ RID10','Strict\ntime'],ylim=(0,105))
 axes[0].set_ylabel('Same 27 records [%]; labels = counts');axes[-1].legend(fontsize=8)
 fig.suptitle('Frozen log-model envelope: definite decisions vs HOLD, not spoof-detection validation')
 fig.tight_layout();fig.savefig(output/'01_model_alignment.png',dpi=170);plt.close(fig)
if __name__=='__main__':main()
