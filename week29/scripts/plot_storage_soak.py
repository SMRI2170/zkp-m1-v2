#!/usr/bin/env python3
"""Plot anonymous recorder monitoring samples, never treat WAITING as RF success."""
import argparse
import csv
import json
from pathlib import Path


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--results',type=Path,required=True)
    a=p.parse_args()
    summary=json.loads((a.results/'summary.json').read_text())
    with (a.results/'resources.csv').open() as f:rows=list(csv.DictReader(f))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    nodes=[x['node'] for x in summary if x['result_collected']]
    fig,axes=plt.subplots(len(nodes),2,figsize=(11,3.3*len(nodes)),squeeze=False)
    for i,node in enumerate(nodes):
        data=[x for x in rows if x['node']==node and x['role']=='receiver']
        expected=next(x for x in summary if x['node']==node)
        if len(data)!=expected['samples']:raise ValueError('Sample denominator mismatch')
        for j,field in enumerate(['memory_available_bytes','session_bytes']):
            subset=[x for x in data if x[field]!='']
            t=[float(x['elapsed_s'])/3600 for x in subset]
            values=[float(x[field])/1024**2 for x in subset]
            ax=axes[i,j];ax.plot(t,values,color=['#165AA7','#C16A1B'][j],linewidth=1.4)
            ax.set(xlabel='Monitor elapsed time [hours]',ylabel='MiB',
                   title=f'{node}: '+['Host available RAM','Cumulative receiver session bytes'][j],xlim=(0,4))
            ax.grid(alpha=.25)
    fig.suptitle('4-hour recorder health monitoring | C/D: WAITING only, 0 target RID records')
    fig.tight_layout();fig.savefig(a.results/'resource-timeline.png',dpi=170);plt.close(fig)


if __name__=='__main__':main()
