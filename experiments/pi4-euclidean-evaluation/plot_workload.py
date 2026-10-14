"""Plot observation-count scaling and measured finite synthetic input queues."""
import argparse,json
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--data',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
attempts=json.loads((a.data/'summary.json').read_text())['results'];summary=sorted([s for s in attempts if s['status']=='completed'],key=lambda s:s['observation_count']);assert summary,'no completed workload trial to plot'
samples=[json.loads(s) for s in (a.data/'samples.jsonl').read_text().splitlines()];queue=[json.loads(s) for s in (a.data/'queue_observed_1hz.jsonl').read_text().splitlines()]
fig,axes=plt.subplots(1,3,figsize=(12,4.5),layout='constrained');counts=[s['observation_count'] for s in summary]
axes[0].plot(counts,[s['flow_ms_mean']/1000 for s in summary],marker='o');axes[0].set_title('Mean flow vs observations (s)')
for s in summary:
 xs=[r for r in samples if r['run_id']==s['run_id'] and not r['warmup']];axes[0].scatter([s['observation_count']]*len(xs),[r['flow_ms']/1000 for r in xs],s=18)
axes[1].plot(counts,[s['prove_memory_sampled_peak_bytes_max']/2**20 for s in summary],marker='o',label='Prove sampled peak');axes[1].plot(counts,[s['whole_unit_peak_bytes']/2**20 for s in summary],marker='s',label='Whole-unit kernel peak');axes[1].set_title('Memory vs observations (MiB)');axes[1].legend(fontsize=8)
for s in summary:
 q=sorted([r for r in queue if r['run_id']==s['run_id'] and r['phase']=='input_dequeue'],key=lambda r:r['repetition']);assert len(q)==3 and all(r['measured_load_test'] for r in q);axes[2].plot([r['repetition'] for r in q],[r['wait_ms']/1000 for r in q],marker='o',label=f"n={s['observation_count']}")
axes[2].set_title('Observed FIFO waiting time (s)');axes[2].set_xlabel('Synthetic batch index');axes[2].set_xticks([0,1,2]);axes[2].legend(fontsize=8)
for ax in axes:ax.grid(alpha=.25);ax.set_ylim(bottom=0)
for ax in axes[:2]:ax.set_xticks(counts);ax.set_xlabel('Signed observations / proof')
fig.suptitle('Pi4 gnark Groth16: MiMC + EdDSA + session/policy/RID binding | CPU 25%')
fig.supxlabel('Warmup1 + repeat3; finite 1 batch/s input, queue capacity3; n=2/4 means 2/4 observations per batch. No sustained-rate claim. Failed/partial trials excluded; see trials.csv.',fontsize=9)
a.out.parent.mkdir(parents=True,exist_ok=True);fig.savefig(a.out.with_suffix('.png'),dpi=180);fig.savefig(a.out.with_suffix('.svg'))
f=a.out.with_suffix('.svg');f.write_text('\n'.join(s.rstrip() for s in f.read_text().splitlines())+'\n')
