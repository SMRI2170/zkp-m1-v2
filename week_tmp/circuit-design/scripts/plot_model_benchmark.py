import argparse,csv,json,statistics
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('results',type=Path);a=p.parse_args()
rows=list(csv.DictReader((a.results/'model-benchmark.csv').open()));s=json.loads((a.results/'model-e2e-summary.json').read_text())
summary={key:dict(n=len(rows),mean=statistics.mean(float(r[key]) for r in rows),median=statistics.median(float(r[key]) for r in rows),min=min(float(r[key]) for r in rows),max=max(float(r[key]) for r in rows)) for key in ['assignment_and_sign_us','prove_us','joint_verify_us','durable_commit_us','full_flow_us']}
(a.results/'benchmark-statistics.json').write_text(json.dumps({'scope':'three synthetic samples, shared setup, one Mac process; not independent field runs','stages':summary},indent=2)+'\n')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
fig,axes=plt.subplots(1,2,figsize=(11,4.5));x=list(range(1,len(rows)+1))
axes[0].bar(x,[float(r['prove_us'])/1e6 for r in rows],color='#285b8e');axes[0].set(xlabel='Synthetic sample (same setup/process)',ylabel='Proving time [s]',xticks=x,title='New frozen-model signed circuit')
for key,label in [('assignment_and_sign_us','assignment + sign'),('joint_verify_us','joint verify'),('durable_commit_us','durable commit')]:axes[1].plot(x,[float(r[key])/1000 for r in rows],marker='o',label=label)
axes[1].set(xlabel='Synthetic sample (same setup/process)',ylabel='Time [ms]',xticks=x,title='Other stages');axes[1].legend(fontsize=8)
fig.suptitle('Mac only; 368,931 constraints; 3 samples are NOT field detection trials')
fig.tight_layout();fig.savefig(a.results/'model-performance.png',dpi=170)
