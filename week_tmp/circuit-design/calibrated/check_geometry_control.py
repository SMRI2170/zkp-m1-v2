"""Isolate projection/quantization from domain gating and envelope approximation."""
import argparse,csv,json,math,sys
from pathlib import Path
from evaluate import ROOT,private_path,load_selection,split_time,prediction,normalize_geometry,sha

def main():
 p=argparse.ArgumentParser();p.add_argument('--positions-config',type=Path,required=True);p.add_argument('--selection-manifest',type=Path,required=True);p.add_argument('--results',type=Path,required=True);a=p.parse_args()
 conf=json.loads(private_path(a.positions_config,existing=True).read_text());positions=private_path(conf['positions'],existing=True);before=sha(positions)
 with positions.open() as f:rows=list(csv.DictReader(f))
 selected=[r for r in load_selection(a.selection_manifest,positions,rows) if r['node']=='Pixel'];items=[dict(source=r,boot=r['boot_scope'],time=float(r['observed_us'])/1e6,distance=float(r['claimed_horizontal_distance_m']),rssi=float(r['rssi_dbm'])) for r in selected]
 train,cal,test=split_time(items);model=json.loads((ROOT/'week29/results/issue96-attacks-a/summary.json').read_text());aa,nn,tau=model['model_intercept_dbm'],model['horizontal_proxy_n'],model['threshold_db']
 origin=dict(latitude=float(train[0]['source']['receiver_latitude']),longitude=float(train[0]['source']['receiver_longitude']),altitude_m=0.)
 old=new=changed=0
 for item in test:
  r=item['source'];rx=dict(latitude=float(r['receiver_latitude']),longitude=float(r['receiver_longitude']),horizontal_accuracy_m=float(r['accuracy_m']));q=dict(latitude=float(r['claimed_latitude']),longitude=float(r['claimed_longitude']),horizontal_accuracy_m=0.)
  g=normalize_geometry(rx,q,origin,2,projection_allowance_m=.02);d=math.dist(g['receiver']['center_cm'][:2],g['claim']['center_cm'][:2])/100
  was=abs(item['rssi']-prediction(item['distance'],aa,nn))>tau
  now=abs(round(item['rssi']*100)/100-prediction(d,aa,nn))>tau
  old+=was;new+=now;changed+=was!=now
 if sha(positions)!=before:raise ValueError('Input changed')
 result=dict(n=len(test),original_unbounded_point_alarms=old,enu_cm_unbounded_point_alarms=new,changed_alarm_labels_due_to_geometry_and_quantization=changed,scope='same frozen coefficients/threshold, no domain guard; not real spoof performance',input_unchanged=True,code_sha256=sha(__file__))
 with (a.results/'geometry-control.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
 with (a.results/'comparison.csv').open() as f:comparison=list(csv.DictReader(f))
 row=next(r for r in comparison if r['scenario']=='nominal_point' and r['attack']=='unmodified')
 import matplotlib;matplotlib.use('Agg')
 import matplotlib.pyplot as plt
 groups=[(27-old,old,0),(27-new,new,0),(int(row['oracle_consistent']),int(row['oracle_alarm']),int(row['oracle_hold'])),(int(row['consistent']),int(row['alarm']),int(row['hold']))]
 fig,ax=plt.subplots(figsize=(9,5));bottom=[0]*4
 for idx,label,color in [(0,'consistent','#285b8e'),(1,'alarm','#b44d4d'),(2,'hold','#e0a93a')]:
  values=[g[idx] for g in groups];ax.bar(range(4),values,bottom=bottom,label=label,color=color)
  for i,v in enumerate(values):
   if v:ax.text(i,bottom[i]+v/2,str(v),ha='center',va='center',color='black' if idx==2 else 'white')
  bottom=[b+v for b,v in zip(bottom,values)]
 ax.set(xticks=range(4),xticklabels=['Original\npoint log','ENU cm\npoint log','+ trained\ndomain guard','+ integer\nenvelope'],ylim=(0,29),ylabel='Same 27 unmodified records',title='Control: distance normalization / domain / approximation are different changes');ax.legend(loc='upper right',fontsize=8)
 fig.tight_layout();fig.savefig(a.results/'02_point_reference_control.png',dpi=170);plt.close(fig)
 print(json.dumps(result))
if __name__=='__main__':main()
