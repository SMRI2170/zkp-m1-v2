"""Plot Pi-native runs only; n=1 is a functional measurement, not a repeat estimate."""
import json, statistics
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[2]
RUNS=[('Kimchi', 'next-kimchi-pi-v2'),('Binius64\nportable BLAKE3','next-binius-pi-v1'),('Jolt ZK\nquick, n=1','next-jolt-pi-v2')]
def read(p):return json.loads(p.read_text())
results=[]
for label,name in RUNS:
 p=ROOT/'week24/logs/pi-euclidean-next'/name
 rows=[json.loads(s) for s in (p/'benchmark.jsonl').read_text().splitlines() if s.startswith('{')]
 samples=[s for s in rows if s['phase']=='sample']; resource=read(p/'resource.json'); mem=read(p/'memory-summary.json')
 assert resource['exit_code']==0 and rows[-1]['all_verified']
 flows=[sum(s.get(k,0) for k in ['witness_ms','prove_ms','verify_ms']) for s in samples]
 results.append(dict(label=label,run=name,n=len(samples),flow_mean_ms=statistics.mean(flows),flow_sd_ms=statistics.stdev(flows) if len(flows)>1 else None,memory_time_weighted_mean_bytes=mem['time_weighted']['mean_bytes'],memory_kernel_peak_bytes=resource['cgroup_peak_bytes'],proof_mean_bytes=statistics.mean(s['proof_bytes'] for s in samples),proof_min_bytes=min(s['proof_bytes'] for s in samples),proof_max_bytes=max(s['proof_bytes'] for s in samples)))
summary={'cpu_quota_percent':25,'scope':'Pi4 ARM64; setup excluded from flow; memory includes setup and negative tests; varied synthetic cases, not IID repeats; Jolt quick n=1 has no SD','results':results}
(ROOT/'week24/logs/euclidean-next-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
fig,axes=plt.subplots(1,3,figsize=(13,4.5),layout='constrained');x=list(range(3)); labels=[r['label'] for r in results]
values=[[r['flow_mean_ms']/1000 for r in results],[r['memory_time_weighted_mean_bytes']/2**20 for r in results],[r['proof_mean_bytes']/1024 for r in results]]
for ax,v,title in zip(axes,values,['Mean flow (s)','Whole-unit memory (MiB)','Serialized proof (KiB)']):
 bars=ax.bar(x,v,color=['#3274a1','#e1812c','#3a923a']);ax.set_xticks(x,labels);ax.set_title(title);ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
 for b,a in zip(bars,v):ax.annotate(f'{a:.2f}',(b.get_x()+b.get_width()/2,a),xytext=(0,4),textcoords='offset points',ha='center',fontsize=9)
 ax.set_ylim(0,max(v)*1.25)
peaks=[r['memory_kernel_peak_bytes']/2**20 for r in results];axes[1].scatter(x,peaks,color='black',marker='_',s=220,label='Kernel peak');axes[1].legend(loc='upper left',fontsize=8);axes[1].set_ylim(0,max(peaks)*1.3)
fig.suptitle('Pi4 Euclidean proof: CPU quota 25% | Kimchi/Binius64 n=7, Jolt quick n=1')
fig.supxlabel('Flow = witness + prove + verify; setup/negative tests excluded. Proof formats differ. No ranking across prior CPU conditions.',fontsize=9)
p=ROOT/'week24/plots';p.mkdir(exist_ok=True)
fig.savefig(p/'euclidean-next.png',dpi=180);fig.savefig(p/'euclidean-next.svg')
s=p/'euclidean-next.svg';s.write_text('\n'.join(line.rstrip() for line in s.read_text().splitlines())+'\n')
print(json.dumps(summary))
