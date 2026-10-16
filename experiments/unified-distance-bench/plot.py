"""Plot recorded complete cohorts only; no imputation and no cold/warm pooling."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
from protocol import VERSION

def main():
    p=argparse.ArgumentParser();p.add_argument('--data',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    summaries=json.loads((a.data/'summary.json').read_text())
    groups=defaultdict(list)
    for r in summaries:
        if r['status']=='completed' and r['protocol']==VERSION:
            # Same host, quota, thread and measured phases are necessary, not sufficient security equivalence.
            key=(r['host_class'],r['cpu_quota_percent'],r['threads'],r['flow_scope'])
            groups[key].append(r)
    if not groups:raise SystemExit('No complete balanced cohort; no performance graph generated')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    points=[json.loads(s) for s in (a.data/'samples.jsonl').read_text().splitlines() if s.strip()]
    a.out.mkdir(parents=True,exist_ok=False)
    for index,(cohort,rows) in enumerate(groups.items()):
        fig,axes=plt.subplots(1,3,figsize=(19,max(5,len(rows)*.7+2)))
        for i,r in enumerate(rows):
            samples=[s for s in points if s['run_id']==r['run_id'] and not s['warmup']]
            axes[0].scatter([s['flow_ms'] for s in samples],[i+(s['case_id']-3)*.035 for s in samples],s=15,alpha=.6)
            axes[0].errorbar(r['flow_ms']['mean'],i,xerr=r['flow_ms']['sd'],fmt='D',color='black',capsize=3)
            axes[0].scatter(r['flow_ms']['median'],i,marker='x',color='darkred',s=45,zorder=4)
            # Measured whole-unit values including startup/setup/warmups/negative tests.
            if r['whole_run_memory_mean_bytes'] is not None:
                axes[1].barh(i+.15,r['whole_run_memory_mean_bytes']/2**20,height=.25,color='gray')
            if r['whole_run_kernel_peak_bytes'] is not None:
                axes[1].barh(i-.15,r['whole_run_kernel_peak_bytes']/2**20,height=.25,color='steelblue')
            if r['proof_bytes']['mean'] is not None:
                axes[2].barh(i,r['proof_bytes']['mean'],height=.5,color='steelblue')
        for ax in axes:
            ax.set_yticks(range(len(rows)),[r['framework']+' (n=21)' for r in rows]);ax.invert_yaxis();ax.grid(axis='x',alpha=.2)
        axes[0].set_xlabel('Flow (ms): points; mean diamond +/- SD; median x');axes[0].set_xscale('log')
        axes[1].set_xlabel('Whole-run memory (MiB): gray=time mean, blue=kernel peak')
        axes[2].set_xlabel('Native serialized proof (bytes; encodings differ)');axes[2].set_xscale('log')
        fig.suptitle('Balanced distance protocol: 7 inputs x 3 repeats; 7 warmups excluded\n'+str(cohort),fontsize=10)
        fig.text(.5,.015,'Within-process repetitions; SD is descriptive, not a confidence interval. Native proof/security settings differ.',ha='center',fontsize=9)
        fig.tight_layout(rect=(0,.06,1,.91))
        for ext in ('png','svg'):fig.savefig(a.out/f'cohort-{index:02}.{ext}',dpi=160)
        plt.close(fig)
if __name__=='__main__':main()
