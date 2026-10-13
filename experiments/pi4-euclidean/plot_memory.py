"""Standalone research plots from committed Pi memory samples, not simulation."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
root=Path(__file__).resolve().parents[2]
names=['euclidean-groth16-v1','euclidean-plonk-v1','euclidean-rapid-v3','euclidean-halo2-v2','euclidean-noir-v1','euclidean-nova-v2','euclidean-hypernova-v1','euclidean-nova-v1']
labels=['gnark Groth16','gnark PLONK','Circom / RapidSnark','Halo2 IPA / Pasta','Noir / Barretenberg','Nova / CycleFold (IVC only)','HyperNova / CycleFold (IVC only)','Nova: stopped on undervoltage']
matplotlib.rcParams['svg.fonttype']='none'
fig,axes=plt.subplots(4,2,figsize=(11,12))
for ax,name,label in zip(axes.flat,names,labels):
    p=root/'week24/logs/pi-euclidean'/name
    rows=[json.loads(l) for l in (p/'memory.jsonl').read_text().splitlines()]
    r=json.loads((p/'resource.json').read_text())
    ax.plot([v['elapsed_s'] for v in rows],[v['cgroup_current_bytes']/2**20 for v in rows],color='#165ea9',linewidth=1.1,label='whole cgroup (sampled)')
    ax.axhline(r['cgroup_peak_bytes']/2**20,color='#a54b0b',linestyle='--',linewidth=.8,label='kernel peak')
    ax.set_title(label,fontsize=11)
    ax.set_xlabel('Time from process launch (s)');ax.set_ylabel('Memory (MiB)');ax.grid(alpha=.2)
    ax.set_ylim(bottom=0);ax.legend(fontsize=7,loc='best')
fig.suptitle('Pi4: synthetic integer Euclidean distance circuits\nstartup + proof/verification + negative tests; different setup scopes',fontsize=13)
fig.tight_layout(rect=[0,0,1,.95])
out=root/'week24/plots';out.mkdir(exist_ok=True)
fig.savefig(out/'euclidean-pi-memory.png',dpi=150)
fig.savefig(out/'euclidean-pi-memory.svg')
p=out/'euclidean-pi-memory.svg';p.write_text('\n'.join(x.rstrip() for x in p.read_text().splitlines())+'\n')
