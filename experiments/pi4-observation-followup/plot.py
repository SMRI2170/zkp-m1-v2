"""Mac-only plots, kept separate from Pi cgroup/CPU25 results."""
import argparse,json,statistics
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--data',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
rs=[r for r in json.loads((a.data/'summary.json').read_text())['results'] if r['status']=='completed'];rs=sorted(rs,key=lambda s:s['observation_count']);x=sorted({r['observation_count'] for r in rs});groups=[[r for r in rs if r['observation_count']==n] for n in x]
fig,axs=plt.subplots(1,3,figsize=(12,4),layout='constrained')
for ax,values,title in zip(axs,[[statistics.mean(r['flow_mean_ms'] for r in g)/1000 for g in groups],[max(r['whole_run_sampled_process_tree_rss_peak_bytes'] for r in g)/2**20 for g in groups],[max(r['max_wait_ms'] for r in g)/1000 for g in groups]],['Mean flow (s)','Whole-run sampled RSS peak (MiB)','Max observed FIFO wait (s)']):
 ax.plot(x,values,marker='o');ax.set_xticks(x);ax.set_xlabel('Signed observations / batch');ax.set_title(title);ax.grid(alpha=.2);ax.set_ylim(bottom=0)
fig.suptitle('Mac ARM64: Groth16 signed workload | compute parallelism1, CPU quota unset')
fig.supxlabel('Cold processes n1/n2=1 each, n4=2 completed,1 stopped; warmup1+repeat3 per process; fresh setup/key. RSS soft guard, not Pi metrics.',fontsize=9)
a.out.parent.mkdir(parents=True,exist_ok=True);fig.savefig(a.out.with_suffix('.png'),dpi=180);fig.savefig(a.out.with_suffix('.svg'))
f=a.out.with_suffix('.svg');f.write_text('\n'.join(s.rstrip() for s in f.read_text().splitlines())+'\n')
