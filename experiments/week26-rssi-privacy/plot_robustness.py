"""Plots of saved robustness aggregates only; no refitting."""
import argparse
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def main():
    p=argparse.ArgumentParser();p.add_argument('run',type=Path);a=p.parse_args()
    s=json.loads((a.run/'summary.json').read_text())['summaries']
    plt.rcParams.update({'font.size':10,'axes.titlesize':11,'axes.labelsize':10,'xtick.labelsize':9,'ytick.labelsize':9})
    colors=['#2F64A1','#D39341','#558466','#8C6BAD']
    def get(study,**kw):return next(v for v in s[study] if all(v[k]==x for k,x in kw.items()))
    def save(fig,name,note):
        fig.text(.5,.015,note,ha='center',fontsize=8)
        fig.tight_layout(rect=(0,.06,1,1))
        for ext in ['png','svg']:fig.savefig(a.run/f'{name}.{ext}',dpi=180)
        plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(12,5))
    noise_names=[('gaussian2','Gaussian SD2',colors[0]),('gaussian_matched_rms','Gaussian same RMS',colors[1]),('empirical','Indoor BLE residuals',colors[2])]
    envs=['matched','gain_shift6','exponent_shift05','combined_shift'];x=np.arange(4)
    for i,(noise,label,color) in enumerate(noise_names):
        rows=[v for v in s['empirical_sync'] if v['noise_model']==noise and v['receivers']==10 and v['environment']=='matched']
        axes[0].plot([v['delta_m'] for v in rows],[v['alarm_rate']*100 for v in rows],marker='o',label=label,color=color)
        axes[1].bar(x+(i-1)*.24,[100*get('empirical_sync',noise_model=noise,receivers=10,environment=env,delta_m=0)['alarm_rate'] for env in envs],.24,label=label,color=color)
    axes[0].set(title='10 RX: displacement alarms',xlabel='Horizontal claim displacement (m)',ylabel='Alarm rate (%)',ylim=(0,100),xticks=[0,30,50,100,200]);axes[0].legend(fontsize=8)
    axes[1].set(title='Normal observations: false alarms after shift',ylabel='False alarm rate (%)',xticks=x,xticklabels=['Matched','Angular gain\namp.6dB','PLE +0.5','Both'],ylim=(0,100))
    axes[1].axhline(5,color='gray',linestyle=':',linewidth=1)
    for ax in axes:ax.grid(axis='y',alpha=.2)
    save(fig,'empirical-noise-and-shift','Indoor residual stress, independent virtual links and held-out sectors; not a UAV or actual multi-RX experiment.')
    fig,axes=plt.subplots(1,2,figsize=(11,5))
    for ax,pattern,sd in [(axes[0],'random_rows',1),(axes[1],'whole_flights',4)]:
        for model,label,color in [('shared','Shared model',colors[3]),('mean','Mean offset',colors[0]),('median','Median offset',colors[1]),('huber','Huber offset',colors[2])]:
            rows=[v for v in s['poisoning'] if v['model']==model and v['flight_sd_db']==sd and v['pattern']==pattern and v['distance_multiplier']==4 and v['scenario']=='normal']
            ax.plot([v['corrupt_fraction']*100 for v in rows],[v['mae_m'] for v in rows],marker='o',label=label,color=color)
        ax.set(title=f'{pattern.replace("_"," ")}, flight SD={sd}dB',xlabel='Enrollment distance labels corrupted (%)',ylabel='Future normal-flight MAE (m)',xticks=[0,10,30,50,70],ylim=(0,140));ax.grid(alpha=.2)
    axes[0].legend(fontsize=8)
    save(fig,'poisoning','100 enrollment labels/RID; poisoned labels claim 4x distance. Global training is clean; correction shrinkage is shared.')
    cases=['normal','step_before8','step_before16','step_after8','cloned_rid'];labels=['Normal','+8dB before\nanchor','+16dB before\nanchor','+8dB after\nanchor','Cloned RID'];x=np.arange(5)
    fig,axes=plt.subplots(1,2,figsize=(12,5))
    gated=[get('anchor_gate',flight_sd_db=1,anchor_count=5,scenario=case,model='rid_gated') for case in cases]
    unchecked=[get('anchor_gate',flight_sd_db=1,anchor_count=5,scenario=case,model='rid_unchecked') for case in cases]
    bars=axes[0].bar(x,[v['accept_rate']*100 for v in gated],color=colors[0]);axes[0].bar_label(bars,fmt='%.1f',padding=3,fontsize=8)
    axes[0].set(title='Fresh-anchor check: accepted flights',ylabel='Accepted anchor units (%)',ylim=(0,110),xticks=x,xticklabels=labels)
    axes[1].bar(x-.18,[v['mae_m'] for v in unchecked],.34,label='No gate: all queries',color=colors[3])
    vals=[np.nan if v['mae_m'] is None else v['mae_m'] for v in gated]
    axes[1].bar(x+.18,vals,.34,label='Gated: accepted only',color=colors[0])
    for i,v in enumerate(vals):
        if np.isnan(v):axes[1].text(i+.18,2,'No accepted\nqueries',ha='center',fontsize=8)
    axes[1].set(title='Prediction error and abstention must be read together',ylabel='Distance MAE (m)',xticks=x,xticklabels=labels);axes[1].legend(fontsize=8)
    for ax in axes:ax.grid(axis='y',alpha=.2)
    save(fig,'fresh-anchor-gate','Five protected true-distance anchor readings, flight SD1dB. A change after the anchor bypasses this check; no identity guarantee.')
    gaps=[3,60,3600,86400];assumptions=['none',30,600,86400]
    fig,axes=plt.subplots(1,2,figsize=(11,5))
    coverage=np.array([[get('time_mismatch',true_tau_s=600,assumed_tau_s=tau,gap_s=gap,scenario='normal')['interval_coverage']*100 for gap in gaps] for tau in assumptions])
    mae=np.array([[get('time_mismatch',true_tau_s=600,assumed_tau_s=tau,gap_s=gap,scenario='normal')['mae_m'] for gap in gaps] for tau in assumptions])
    for ax,values,title in [(axes[0],coverage,'True tau=10min: interval coverage (%)'),(axes[1],mae,'True tau=10min: distance MAE (m)')]:
        img=ax.imshow(values,cmap='YlGnBu',aspect='auto');fig.colorbar(img,ax=ax,shrink=.8)
        for i in range(4):
            for j in range(4):
                norm=(values[i,j]-values.min())/(values.max()-values.min()+1e-12)
                ax.text(j,i,f'{values[i,j]:.1f}',ha='center',va='center',color='white' if norm>.6 else 'black')
        ax.set(title=title,xticks=range(4),xticklabels=['3s','1min','1h','1day'],yticks=range(4),yticklabels=['No history','Assume 30s','Assume 10min','Assume 1day'],xlabel='Gap from independent true-distance anchor')
    save(fig,'time-constant-mismatch','The time constant is hypothetical. Assuming slow change can make intervals too narrow after the real correlation has decayed.')
    print('Four PNG/SVG pairs saved.')


if __name__=='__main__':main()
