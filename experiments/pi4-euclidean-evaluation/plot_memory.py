"""Render the normalized memory CSV; condition metadata is joined through trials."""
import argparse,csv
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--data',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
with (a.data/'memory.csv').open() as f:rows=list(csv.DictReader(f))
ids=sorted({s['run_id'] for s in rows});assert ids
fig,axes=plt.subplots(len(ids),1,figsize=(10,2.5*len(ids)),layout='constrained',squeeze=False)
for ax,run in zip(axes[:,0],ids):
 xs=[r for r in rows if r['run_id']==run];ax.plot([float(r['elapsed_s']) for r in xs],[float(r['cgroup_current_bytes'])/2**20 for r in xs],lw=.7);ax.set_title(run);ax.set_ylabel('Whole-unit MiB');ax.set_xlabel('Elapsed seconds');ax.grid(alpha=.2);ax.set_ylim(bottom=0)
fig.suptitle('Sampled memory series including setup, warmup and negative tests; not a leak diagnosis')
a.out.parent.mkdir(parents=True,exist_ok=True);fig.savefig(a.out.with_suffix('.png'),dpi=160);fig.savefig(a.out.with_suffix('.svg'))
f=a.out.with_suffix('.svg');f.write_text('\n'.join(s.rstrip() for s in f.read_text().splitlines())+'\n')
