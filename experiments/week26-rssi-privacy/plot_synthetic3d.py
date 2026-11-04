"""Plot saved independent simulation summaries. No model is refitted here."""
import argparse
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def main():
    p=argparse.ArgumentParser();p.add_argument('run',type=Path);a=p.parse_args()
    r=json.loads((a.run/'summary.json').read_text())
    rows={(v['channel'],v['scenario'],v['model']):v for v in r['summary']}
    cases=['normal','shift8','position_only','joint_bounded8','joint','whitebox']
    labels=['Normal','TX +8dB','Position\nonly','Joint\nbounded 8dB','Joint\nunbounded','Whitebox']
    models=['PathLoss','Bayesian','GP','MLP'];colors=['#A4B5C7','#D39341','#2F64A1','#558466']
    def save(fig,name,note):
        fig.text(.5,.015,note,ha='center',fontsize=8)
        fig.tight_layout(rect=(0,.06,1,1))
        for ext in ['png','svg']:fig.savefig(a.run/f'{name}.{ext}',dpi=180)
        plt.close(fig)
    x=np.arange(len(cases));fig,ax=plt.subplots(figsize=(10,5.5))
    for i,(model,color) in enumerate(zip(models,colors)):
        ax.bar(x+(i-1.5)*.19,[rows['mixed',s,model]['mae_m'] for s in cases],.19,label=model,color=color)
    ax.set(xticks=x,xticklabels=labels,ylabel='Distance MAE (m)',title='Independent 3D simulation: received events only')
    ax.legend(ncol=4);ax.grid(axis='y',alpha=.2)
    save(fig,'distance-mae','Illustrative uncalibrated model, 10 seeds; new implementation, not reproduction of document 04.')
    fig,axes=plt.subplots(1,2,figsize=(11,4.8))
    for model,color in [('Bayesian',colors[1]),('GP',colors[2]),('MLP',colors[3])]:
        for ax,key in zip(axes,['interval_coverage','undetermined_rate']):
            ax.plot(x,[rows['mixed',s,model][key]*100 for s in cases],marker='o',label=model,color=color)
    for ax,title in zip(axes,['True-distance interval coverage','Undetermined at 30m']):
        ax.set(xticks=x,xticklabels=labels,ylim=(0,105),ylabel='Received events (%)',title=title)
        ax.tick_params(axis='x',labelsize=8);ax.grid(alpha=.2)
    axes[0].axhline(90,color='gray',linestyle=':',linewidth=1);axes[0].legend()
    save(fig,'coverage-and-hold','GP/MLP: flight-max conformal intervals; Bayesian: model-based intervals. No attack coverage guarantee.')
    fig,ax=plt.subplots(figsize=(9,5))
    for i,(key,label,color) in enumerate([('alarm_rate','Residual alarms','#D39341'),('reception_rate','Reception rate','#2F64A1')]):
        vals=[rows['mixed',s,'GP'][key]*100 for s in cases]
        bars=ax.bar(x+(i-.5)*.35,vals,.35,label=label,color=color)
        ax.bar_label(bars,fmt='%.1f',padding=3,fontsize=8)
    ax.set(xticks=x,xticklabels=labels,ylabel='Events (%)',ylim=(0,110),title='Alarms and reception carry different information')
    ax.legend();ax.grid(axis='y',alpha=.2)
    save(fig,'alarm-and-reception','Alarm denominator: received events. Reception denominator: emitted events. Whitebox is a strong hypothetical attacker.')
    fig,ax=plt.subplots(figsize=(8.5,5))
    variants=r['config']['channel_variants'];x=np.arange(len(variants))
    for i,(model,color) in enumerate(zip(models,colors)):
        ax.bar(x+(i-1.5)*.19,[rows[v,'normal',model]['mae_m'] for v in variants],.19,label=model,color=color)
    names={'mixed':'Mixed LOS/NLOS','los_only':'LOS only','ideal':'Idealized channel'}
    ax.set(xticks=x,xticklabels=[names[v] for v in variants],ylabel='Distance MAE (m)',title='Normal TX: channel assumptions change the result')
    ax.legend(ncol=4);ax.grid(axis='y',alpha=.2)
    save(fig,'channel-ablation','Same 10 seeds. Idealized still retains TX randomness, fast fading, antenna gain and quantization.')
    print('Four plots saved as PNG and SVG.')


if __name__=='__main__':main()
