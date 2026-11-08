"""Rebuild scientific figures from PUBLIC aggregate CSV only; no raw positions."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

METHODS=['FreePowerUND','SingleResidual','KF_NIS','DRSS2','DRSS3','DRSS4','DRSS5','MLAT4','MLAT5']
MODELS=['fixed','uniform','slew','adaptive']


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('results',type=Path);a=p.parse_args()
    source=a.results/'aggregate-metrics.csv'
    with source.open() as f:rows=list(csv.DictReader(f))
    def value(row,key):return float(row[key]) if row and row[key] not in ['','None'] else np.nan
    def find(link,model,offset,method):
        found=[r for r in rows if r['risk_scenario']=='False' and r['link']==link and r['model']==model and int(r['offset_m'])==offset and r['method']==method]
        return found[0] if len(found)==1 else None
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    out=a.results/'figures';out.mkdir(exist_ok=True)
    for link in ['strong','edge','weak']:
        fig,axes=plt.subplots(2,2,figsize=(17,10),sharey=True,layout='constrained')
        for ax,model in zip(axes.flat,MODELS):
            for offset,color,label in [(0,'#444444','Normal: FPR'),(30,'#e28a16','30 m claim offset: TPR'),(100,'#135b9e','100 m claim offset: TPR')]:
                selected=[find(link,model,offset,m) for m in METHODS]
                y=np.array([100*value(r,'alarm_scored_mean') for r in selected])
                low=np.array([100*value(r,'alarm_scored_low') for r in selected]);high=np.array([100*value(r,'alarm_scored_high') for r in selected])
                x=np.arange(len(METHODS))+(offset/100-0.45)*.15
                ax.errorbar(x,y,yerr=np.array([y-low,high-y]).clip(0),fmt='o',capsize=3,color=color,label=label)
            ax.axhline(5,color='#999999',linestyle=':',linewidth=1,label='Calibration target (not a guarantee)')
            ax.set(xticks=np.arange(len(METHODS)),xticklabels=['Free P\nUND','Residual\nM0','KF/NIS\nM0','DRSS\n2 RX','DRSS\n3 RX','DRSS\n4 RX','DRSS\n5 RX','MLAT\n4 RX','MLAT\n5 RX'],xlim=(-.5,8.5),ylim=(-3,105),title=f'{model}: {link} link',ylabel='Alarm among scored transmissions (%)')
            ax.text(0,18,'UND\n100%',ha='center',fontsize=8,color='#777777');ax.grid(axis='y',alpha=.2)
        handles,labels=axes.flat[0].get_legend_handles_labels();fig.legend(handles,labels,loc='outside lower center',ncol=4)
        fig.suptitle('Conditional detection, NOT a true-position guarantee\n20 evaluation seeds; 20 dependent packets/seed. CIs use scored seeds only (counts in CSV); 1 scored seed: no CI. Coverage is separate.')
        for suffix in ['png','svg']:fig.savefig(out/f'detection-{link}.{suffix}',dpi=160)
        plt.close(fig)
    for link in ['edge','weak']:
        fig,axes=plt.subplots(1,2,figsize=(15,7),layout='constrained')
        labels=[f'{model} / {offset} m' for model in MODELS for offset in [0,30,100]]
        for ax,metric,title in zip(axes,['received_rate_mean','eligible_rate_mean'],['At least one selected RX received (%)','Scored / all transmitted (%)']):
            matrix=np.array([[100*value(find(link,model,offset,method),metric) for model in MODELS for offset in [0,30,100]] for method in METHODS])
            image=ax.imshow(matrix,vmin=0,vmax=100,cmap='Blues',aspect='auto')
            ax.set(xticks=range(len(labels)),xticklabels=labels,yticks=range(len(METHODS)),yticklabels=METHODS,title=title)
            ax.tick_params(axis='x',rotation=65)
            for i,j in np.ndindex(matrix.shape):
                if np.isfinite(matrix[i,j]):ax.text(j,i,f'{matrix[i,j]:.0f}',ha='center',va='center',fontsize=7,color='white' if matrix[i,j]>65 else 'black')
        fig.colorbar(image,ax=axes,label='%');fig.suptitle(f'{link.capitalize()}-link coverage: missing receptions and computation/startup failures remain UND\nM0: one RSSI per distinct packet. DRSS/MLAT: same physical packet, extra receivers.')
        for suffix in ['png','svg']:fig.savefig(out/f'coverage-{link}.{suffix}',dpi=160)
        plt.close(fig)
    risk=a.results/'risk30-per-seed.csv'
    if risk.exists():
        with risk.open() as f:risk_rows=list(csv.DictReader(f))
        fig,axes=plt.subplots(1,2,figsize=(15,5),layout='constrained')
        for ax,model in zip(axes,['fixed','adaptive']):
            selected=[[r for r in risk_rows if r['model']==model and r['method']==method] for method in METHODS]
            total=np.array([sum(int(r['tx_count']) for r in group) for group in selected],dtype=float)
            bottom=np.zeros(len(METHODS))
            for key,color,label in [('flag_count','#135b9e','FLAG'),('below_count','#e28a16','BELOW threshold'),('und_count','#b8bec4','UNDETERMINED')]:
                y=np.divide([100*sum(int(r[key]) for r in group) for group in selected],total,out=np.zeros(len(total)),where=total>0)
                ax.bar(range(len(METHODS)),y,bottom=bottom,color=color,label=label);bottom+=y
            ax.set(xticks=range(len(METHODS)),xticklabels=METHODS,ylim=(0,100),title=f'{model}: true distance <30 m, claim >=30 m',ylabel='Fraction of risky transmissions (%)');ax.tick_params(axis='x',rotation=45)
        handles,labels=axes[0].get_legend_handles_labels();fig.legend(handles,labels,loc='outside lower center',ncol=3)
        fig.suptitle('Fully synthetic pedestrian trajectory; aggregate counts, NOT safety validation\n100 m claim offset; no measured smartphone data; graph is descriptive (no packet-independent CI).')
        for suffix in ['png','svg']:fig.savefig(out/f'risk30.{suffix}',dpi=160)
        plt.close(fig)
    for svg in out.glob('*.svg'):
        svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines()).rstrip()+'\n')
    receipt=dict(source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),matplotlib=matplotlib.__version__,
                 figures=sorted(f.name for f in out.iterdir()),scope='Static aggregate plots. No real UAV measurements or inferred truth. Zero eligible scores are absent from conditional-performance curves, not plotted as 0% FPR/TPR.')
    (out/'provenance.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt,indent=2))


if __name__=='__main__':main()
