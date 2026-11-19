#!/usr/bin/env python3
"""Plot anonymous short foreground/background study outcomes, never packet delivery rate."""
import argparse,json
from pathlib import Path


def main():
    p=argparse.ArgumentParser();p.add_argument('--results',type=Path,required=True);a=p.parse_args();nodes=json.loads((a.results/'summary.json').read_text())['nodes']
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(12,4.8));names=['Foreground','Home','Screen off','Forced Doze'];colors=['#1C659C','#D3752C']
    for j,n in enumerate(nodes):
        x=[v-.18+j*.36 for v in range(4)];vals=[p['target_distinct_vendor_contents'] for p in n['phases']]
        axes[0].bar(x,vals,width=.34,label=n['node'],color=colors[j])
        for at,v in zip(x,vals):axes[0].text(at,v+.1,str(v),ha='center')
    axes[0].set(xticks=range(4),xticklabels=names,ylabel='Distinct target vendor contents [count]',title='Each phase: about 20 seconds');axes[0].legend();axes[0].grid(axis='y',alpha=.2)
    data=[next(p for p in n['phases'] if p['name']=='forced_doze')['target_new_timestamp_bins_5s'] for n in nodes]
    image=axes[1].imshow(data,cmap='Blues',vmin=0,vmax=max(2,max(max(x) for x in data)),aspect='auto')
    axes[1].set(xticks=range(4),xticklabels=['0-5','5-10','10-15','15-20'],yticks=range(2),yticklabels=[n['node'] for n in nodes],xlabel='Elapsed time within forced Doze [s]',title='New target scan-cache timestamps')
    for i,row in enumerate(data):
        for j,v in enumerate(row):axes[1].text(j,i,str(v),ha='center',va='center',color='white' if v else '#333333')
    fig.colorbar(image,ax=axes[1],label='Count')
    fig.suptitle('ASUS Android 7.0, controlled Pi Beacon | FGS alive does not guarantee fresh RF observations')
    fig.tight_layout();fig.savefig(a.results/'background-target-and-doze.png',dpi=170);plt.close(fig)
    fig,ax=plt.subplots(figsize=(8,4.5))
    for n,c in zip(nodes,colors):ax.plot(names,[p['pss_max_kib']/1024 for p in n['phases']],'o-',label=n['node'],color=c)
    ax.set(ylabel='App PSS maximum among samples [MiB]',title='Short-window memory samples; different Wi-Fi retention settings')
    ax.grid(alpha=.2);ax.legend();fig.tight_layout();fig.savefig(a.results/'background-memory.png',dpi=170);plt.close(fig)


if __name__=='__main__':main()
