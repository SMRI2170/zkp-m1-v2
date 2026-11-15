#!/usr/bin/env python3
"""Plot sanitized benchmark aggregates, never raw capture input."""
import argparse
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--results', required=True, type=Path)
    args=p.parse_args()
    profiles=json.loads((args.results/'validation.json').read_text())['profiles']
    profiles=sorted(profiles,key=lambda r:r['scan_request_interval_s'])
    x=[r['scan_request_interval_s'] for r in profiles]
    y=[r['interval_median_s'] for r in profiles]
    fig,ax=plt.subplots(figsize=(7.2,4.2))
    ax.plot(x,x,'--',color='gray',label='Requested spacing (reference)')
    ax.plot(x,y,'o-',color='#145ba8',label='Observed median RSSI update interval')
    ax.scatter(x,[r['interval_p95_s'] for r in profiles],marker='x',color='#b53a33',label='Observed p95')
    for a,b in zip(x,y):
        ax.annotate(f'{b:.3f}s',(a,b),xytext=(6,-14),textcoords='offset points',fontsize=9)
    ax.set(xlabel='Requested scan spacing (seconds)',ylabel='RSSI cache update interval (seconds)',
           title='Pi C receiving controlled Pi Beacon: 20 seconds per profile')
    ax.set_xticks(x);ax.set_ylim(bottom=0);ax.grid(alpha=.2);ax.legend(fontsize=8)
    fig.text(.01,.005,'Single frequency 2452 MHz; poll 0.1s. Cache updates, not physical packet counts.',fontsize=8)
    fig.tight_layout(rect=(0,.035,1,1))
    for extension in ['png','svg']:
        path=args.results/f'request-vs-rssi-update.{extension}'
        fig.savefig(path,dpi=160)
        if extension=='svg':
            path.write_text('\n'.join(l.rstrip() for l in path.read_text().splitlines())+'\n')
    plt.close(fig)


if __name__=='__main__':
    main()
