#!/usr/bin/env python3
"""Plot per-window scan pilot results; repeated windows are not independent flights."""
import argparse
import csv
from pathlib import Path


def main():
    p=argparse.ArgumentParser();p.add_argument('--results',type=Path,required=True);a=p.parse_args()
    with (a.results/'results.csv').open() as f:rows=list(csv.DictReader(f))
    rows=[r for r in rows if r['strategy']!='passive' and r['valid_duration_complete']=='True']
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    colors={'all_channels':'#C7692D','fixed_frequency':'#1D68A5','adaptive':'#777777'}
    fig,axes=plt.subplots(1,2,figsize=(12,4.7))
    for strategy in colors:
        subset=[r for r in rows if r['strategy']==strategy]
        for repetition in [1,2]:
            values=sorted([r for r in subset if int(r['round'])==repetition],key=lambda r:float(r['interval_s']))
            x=[float(r['interval_s']) for r in values]
            for ax,field in zip(axes,['busy_fraction','target_distinct_vendor_contents']):
                y=[float(r[field])*100 if field=='busy_fraction' else float(r[field]) for r in values]
                ax.plot(x,y,marker='o',color=colors[strategy],alpha=1 if repetition==1 else .55,
                        linestyle='-' if repetition==1 else '--',label=f'{strategy}, round {repetition}')
    axes[0].set(ylabel='Busy / scan requests [%]',ylim=(-3,103),title='Driver rejection among requested scans')
    axes[1].set(ylabel='Distinct target vendor contents [count]',title='Counter-content updates within each 20-second window')
    for ax in axes:
        ax.set_xscale('log',base=2);ax.set(xlabel='Configured delay after scan request [s]',xticks=[.25,.5,1,2,5]);ax.set_xticklabels(['0.25','0.5','1','2','5']);ax.grid(alpha=.2);ax.legend(fontsize=8)
    fig.suptitle('Controlled Pi Beacon pilot: D transmitter / C receiver; not packet delivery rate')
    fig.tight_layout();fig.savefig(a.results/'scan-interval-comparison.png',dpi=170);plt.close(fig)


if __name__=='__main__':main()
