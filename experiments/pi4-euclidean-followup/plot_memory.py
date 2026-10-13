"""Partial Pi cgroup and stopped Mac process/swap traces, never mixed as one metric."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[2]
def read(p,partial=False):
    rows=[]
    for s in p.read_text().splitlines():
        try:rows.append(json.loads(s))
        except json.JSONDecodeError:
            if not partial:raise
    return rows
plt.rcParams.update({'svg.fonttype':'none','font.size':10})
fig,axes=plt.subplots(1,3,figsize=(14,4.8),layout='constrained')
p=ROOT/'week24/logs/pi-euclidean-followup/additional-plonky2-cpu25-v4'
rows=read(p/'memory.jsonl',partial=True)
axes[0].plot([r['elapsed_s'] for r in rows],[r['cgroup_current_bytes']/2**20 for r in rows],color='#2369a5')
axes[0].set(title='A  Pi Plonky2: partial cgroup samples',xlabel='Elapsed seconds',ylabel='Whole-unit memory (MiB)',ylim=(0,1700))
axes[0].axhline(1536,color='#d6814b',ls='--',label='MemoryMax 1536 MiB')
axes[0].legend(fontsize=8)
for i,name in enumerate(['sp1-host-proof-v1','sp1-host-proof-v2']):
    rows=read(ROOT/'week24/logs/zkvm-followup'/name/'memory.jsonl')
    xs=[r['elapsed_s'] for r in rows]
    axes[1].plot(xs,[r['process_tree_rss_bytes']/2**20 for r in rows],label=f'Attempt {i+1}')
    axes[2].plot(xs,[r['system_swap_delta_bytes']/2**20 for r in rows],label=f'Attempt {i+1}')
axes[1].set(title='B  Mac SP1: sampled process-tree RSS',xlabel='Elapsed seconds',ylabel='RSS sum (MiB)')
axes[2].set(title='C  Mac: global swap growth from start',xlabel='Elapsed seconds',ylabel='System swap delta (MiB)')
axes[2].axhline(512,color='#d6814b',ls='--',label='Stop threshold 512 MiB')
for ax in axes:
    ax.grid(alpha=.2);ax.spines[['top','right']].set_visible(False)
axes[1].legend(fontsize=8);axes[2].legend(fontsize=8)
fig.suptitle('Followup failure evidence: different devices and memory scopes',fontsize=14)
fig.supxlabel('Pi: two verified proofs, reboot before summary. Mac: both SP1 attempts stopped on global swap growth; not an OOM.',fontsize=9)
for suffix in ['png','svg']:fig.savefig(ROOT/'week24/plots'/f'euclidean-followup-memory.{suffix}',dpi=170)
p=ROOT/'week24/plots/euclidean-followup-memory.svg';p.write_text('\n'.join(s.rstrip() for s in p.read_text().splitlines())+'\n')
