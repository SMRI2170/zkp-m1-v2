"""Render collected CSV later; matplotlib is only required when creating charts."""
import argparse,csv,statistics
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--data',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
with (a.data/'samples.csv').open() as f:rows=list(csv.DictReader(f))
rows=[r for r in rows if r['warmup']=='False' and r['trial_completed']=='True'];groups={k:[r for r in rows if r['framework']==k] for k in sorted({r['framework'] for r in rows})};assert groups
fig,axes=plt.subplots(1,3,figsize=(12,4.5),layout='constrained');names=list(groups)
for ax,key,div,title in zip(axes,['flow_ms','prove_memory_sampled_peak_bytes','proof_bytes'],[1000,2**20,1024],['Flow (s), warmup excluded','Prove interval sampled peak (MiB)','Serialized proof (KiB)']):
 values=[[float(r[key])/div for r in groups[n] if r[key]!=''] for n in names]
 assert all(values),f'unavailable metric: {key}; do not zero-fill'
 ax.boxplot(values,tick_labels=names,showfliers=True);ax.set_title(title);ax.grid(axis='y',alpha=.25)
 for i,v in enumerate(values,1):ax.scatter([i]*len(v),v,s=25,color='#3274a1');ax.annotate(f'n={len(v)}',(i,max(v)),xytext=(8,4),textcoords='offset points',fontsize=8)
fig.suptitle('Pi4 synthetic same-input repetitions | CPU quota 25% | preliminary within-process repeats')
fig.supxlabel('Within-process repeats; sampled memory is not kernel peak. Different proof encodings/security assumptions.',fontsize=9)
a.out.parent.mkdir(parents=True,exist_ok=True);fig.savefig(a.out.with_suffix('.png'),dpi=180);fig.savefig(a.out.with_suffix('.svg'))
f=a.out.with_suffix('.svg');f.write_text('\n'.join(s.rstrip() for s in f.read_text().splitlines())+'\n')
