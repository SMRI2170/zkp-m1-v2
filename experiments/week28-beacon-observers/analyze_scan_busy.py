#!/usr/bin/env python3
"""Anonymized summaries and plots from private bounded scan diagnostic logs."""
import argparse
import csv
import json
from pathlib import Path
import statistics
from diagnose_scan_busy import summarize

SCENARIOS=['idle','fixed_fast','broad_probe','broad_wait','two_requesters']


def analyze(events):
    if not any(e['kind']=='completed' for e in events):raise ValueError('incomplete diagnostic; not a successful run')
    out={s:summarize([e for e in events if e['scenario']==s]) for s in SCENARIOS}
    for s in SCENARIOS:
        rows=[e for e in events if e['scenario']==s]
        out[s]['observed_scan_starts']=sum(e['kind']=='started' for e in rows)
        waits=[e['duration_s'] for e in rows if e['kind']=='wait' and e.get('terminal')=='finished' and e['tag'].startswith('broad')]
        out[s]['broad_completion_median_s']=statistics.median(waits) if waits else None
        out[s]['broad_completion_min_s']=min(waits) if waits else None
        out[s]['broad_completion_max_s']=max(waits) if waits else None
        for prefix,name in [('during-broad','premature_target'),('after-completion','target_after_completion')]:
            req=[e for e in rows if e['kind']=='request' and e['tag'].startswith(prefix)]
            out[s][name+'_requests']=len(req)
            out[s][name+'_busy']=sum(e['reason']=='busy' for e in req)
    return out


def figures(events,output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(2,1,figsize=(10,7),layout='constrained')
    labels=['Fixed channel\n0.25 s requests','Before broad\nscan completion','After broad\nscan completion','Two requesters\n(same radio)']
    for offset,(node,es) in enumerate(events.items()):
        groups=[('fixed_fast',None),('broad_probe','during-broad'),('broad_wait','after-completion'),('two_requesters',None)]
        counts=[]
        for scenario,prefix in groups:
            req=[e for e in es if e['kind']=='request' and e['scenario']==scenario and (prefix is None or e['tag'].startswith(prefix))]
            counts.append((sum(e['reason']=='busy' for e in req),len(req)))
        x=[i+(offset-.5)*.32 for i in range(4)]
        bars=axes[0].bar(x,[100*b/n if n else 0 for b,n in counts],width=.3,label='Node '+node.upper())
        for bar,(b,n) in zip(bars,counts):axes[0].text(bar.get_x()+bar.get_width()/2,bar.get_height()+2,f'{b}/{n}',ha='center',fontsize=9)
    axes[0].set_xticks(range(4),labels);axes[0].set_ylim(0,118)
    axes[0].set_ylabel('Busy requests / attempted requests (%)');axes[0].legend()
    axes[0].set_title('Controlled contention tests: ratios are NOT packet-loss rates')
    y=0;yticks=[];ylabels=[]
    for node,es in events.items():
        for scenario,tag in [('broad_probe','broad-0'),('broad_wait','broad-wait-0')]:
            start=next(e for e in es if e['kind']=='request' and e['tag']==tag)
            end=next(e for e in es if e['kind']=='wait' and e['tag']==tag)
            duration=end['duration_s'];t0=start['request_started_s']
            axes[1].plot([0,duration],[y,y],lw=8,color='#355c9a',alpha=.6)
            req=[e for e in es if e['kind']=='request' and e['scenario']==scenario and
                 (e['tag']=='during-broad-0' or e['tag']=='after-completion-0')]
            for r in req:
                busy=r['reason']=='busy'
                axes[1].scatter(r['request_started_s']-t0,y,c='#c44b31' if busy else '#16835f',marker='x' if busy else 'o',s=70,zorder=3)
            yticks.append(y);ylabels.append(node.upper()+(' / early requests' if scenario=='broad_probe' else ' / wait done'))
            y+=1
    axes[1].set_yticks(yticks,ylabels);axes[1].set_xlabel('Seconds after broad scan request (first trial)')
    axes[1].set_title('Blue: scan in progress    Red x: busy    Green dot: accepted')
    axes[1].set_xlim(-.1,4.5);axes[1].grid(axis='x',alpha=.2)
    fig.savefig(output/'scan-busy-comparison.png',dpi=160)
    svg=output/'scan-busy-comparison.svg';fig.savefig(svg)
    svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines())+'\n')
    plt.close(fig)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--plot',action='store_true');a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False)
    events={n:[json.loads(x) for x in (a.input/n/'events.jsonl').read_text().splitlines()] for n in ['b','c']}
    result={n:analyze(es) for n,es in events.items()}
    (a.output/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    with (a.output/'scenarios.csv').open('w') as f:
        writer=csv.writer(f,lineterminator='\n');writer.writerow(['node','scenario','requests','accepted','busy','busy_fraction','broad_completion_median_s'])
        for n,groups in result.items():
            for s,r in groups.items():writer.writerow([n,s,*[r[k] for k in ['requests','accepted','busy','busy_fraction','broad_completion_median_s']]])
    if a.plot:figures(events,a.output)


if __name__=='__main__':main()
