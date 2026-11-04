"""Render only saved study aggregates; no fitting and no real capture data."""
import argparse
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import ScalarFormatter


def main():
    parser=argparse.ArgumentParser();parser.add_argument('run',type=Path);args=parser.parse_args()
    plt.rcParams.update({'font.size':10,'axes.titlesize':11,'axes.labelsize':10,
                         'xtick.labelsize':9,'ytick.labelsize':9,'legend.fontsize':8})
    r=json.loads((args.run/'summary.json').read_text());s=r['summaries']
    def save(fig,name,note):
        fig.text(.5,.012,note,ha='center',fontsize=8)
        fig.tight_layout(rect=(0,.055,1,1))
        for ext in ['png','svg']:fig.savefig(args.run/f'{name}.{ext}',dpi=180)
        plt.close(fig)
    colors=['#2F64A1','#D39341','#558466','#8C6BAD','#64788C']
    fig,axes=plt.subplots(1,2,figsize=(11,4.8))
    for ax,band in zip(axes,['20-40m','80-120m']):
        for attack,label,color in [('position_only','Position only',colors[0]),('joint_unbounded','Joint unrestricted',colors[1]),('joint_bounded8','Joint limited to 8dB',colors[2])]:
            rows=[v for v in s['position'] if v['direction']=='out' and v['range_bin']==band and v['attack']==attack]
            ax.plot([v['delta_m'] for v in rows],[v['alarm_rate']*100 for v in rows],marker='o',label=label,color=color)
        ax.axhline(rows[0]['matched_normal_fpr']*100,color='gray',linestyle=':',label='Matched normal alarms')
        ax.set(title=f'True distance {band}: outward displacement',xlabel='Additional claimed range (m)',ylabel='Alarm rate (%)',ylim=(0,100),xticks=[0,30,50,100,200]);ax.grid(alpha=.2)
    axes[0].legend(fontsize=8)
    save(fig,'spoof-distance','One RSSI per event. Calibration target FPR=5% globally, not within each true-distance band. Synthetic assumptions.')
    fig,axes=plt.subplots(1,2,figsize=(11,4.8))
    for ax,noise in zip(axes,[2,6]):
        for n,color in zip([1,2,3,5,10],colors):
            rows=[v for v in s['synchronous'] if v['aperture_radius_m']==100 and v['link_noise_sd_db']==noise and v['receivers']==n and v['direction']=='random_horizontal']
            ax.plot([v['delta_m'] for v in rows],[v['alarm_rate']*100 for v in rows],marker='o',label=f'{n} RX',color=color)
        ax.set(title=f'Same packet: link noise SD={noise}dB',xlabel='Claim displacement (m)',ylabel='Alarm rate (%)',ylim=(0,100),xticks=[0,30,50,100,200]);ax.grid(alpha=.2)
    axes[0].legend(ncol=2,fontsize=8)
    save(fig,'synchronous-count','Separate favorable baseline: 100m aperture radius, known geometry/exponent, common TX power, no censoring or NLOS.')
    fig,axes=plt.subplots(1,2,figsize=(10.5,4.8))
    for case,label,color in [('normal','Normal',colors[0]),('range_shift30','Range +30m',colors[1]),('range_shift30_joint','Range +30m and power',colors[2])]:
        rows=[v for v in s['asynchronous'] if v['scenario']==case]
        axes[0].plot([v['receivers'] for v in rows],[v['mae_m'] for v in rows],marker='o',label=label,color=color)
        axes[1].plot([v['receivers'] for v in rows],[v['alarm_rate']*100 for v in rows],marker='o',label=label,color=color)
    for ax,title,y in zip(axes,['Fixed-budget asynchronous GP','Asynchronous residual alarms'],['Distance MAE (m)','Alarm rate (%)']):
        ax.set(title=title,xlabel='Receiver nodes',ylabel=y,xticks=[1,2,3,5,10]);ax.grid(alpha=.2)
    axes[0].legend(fontsize=8);axes[1].legend(fontsize=8)
    axes[0].set_ylim(0,45);axes[1].set_ylim(0,15)
    save(fig,'asynchronous-count','Fixed event and label budgets. Exactly one RX per event; changing the RX label adds no simultaneous geometry.')
    fig,axes=plt.subplots(2,3,figsize=(12,7.5))
    for col,tau in enumerate([30,600,86400]):
        for method,label,color in [('no_history','No history',colors[0]),('hold_last','Hold last',colors[1]),('ou_matched','Matched OU',colors[2])]:
            rows=[v for v in s['time'] if v['tau_s']==tau and v['scenario']=='normal' and v['model']==method]
            for ax,key in [(axes[0,col],'mae_m'),(axes[1,col],'interval_coverage')]:
                ax.plot([v['gap_s'] for v in rows],[v[key]*(100 if key=='interval_coverage' else 1) for v in rows],marker='o',label=label,color=color)
        axes[0,col].set_title(f'Power correlation time: {tau}s')
        axes[1,col].axhline(90,color='gray',linestyle=':',linewidth=1)
        axes[1,col].set_ylim(0,105)
        for row in range(2):
            axes[row,col].set_xscale('log');axes[row,col].set_xticks([1,60,3600,86400],['1s','1min','1h','1day']);axes[row,col].grid(alpha=.2)
        axes[0,col].set_ylim(0,max(v['mae_m'] for v in s['time'] if v['scenario']=='normal')*1.1)
        axes[1,col].set_xlabel('Gap from independently labeled anchor')
    axes[0,0].set_ylabel('Distance MAE (m)');axes[1,0].set_ylabel('Interval coverage (%)');axes[0,0].legend(fontsize=8)
    save(fig,'time-gap','New conditional Gaussian power experiment, not paper reproduction. OU time constant is known; +8dB OOD results are in CSV.')
    model_names=[('global','Shared',colors[0]),('rid_offset','RID offset',colors[1]),('rid_shrinkage','RID shrinkage',colors[2]),('rid_full_ols','RID full OLS',colors[3])]
    fig,axes=plt.subplots(1,2,figsize=(11,4.8))
    for ax,case in zip(axes,['normal','cloned_rid']):
        for model,label,color in model_names:
            rows=[v for v in s['personalization'] if v['profile']=='stable_id6' and v['scenario']==case and v['model']==model]
            ax.plot([v['labeled_per_rid'] for v in rows],[v['mae_m'] for v in rows],marker='o',label=label,color=color)
        ax.set_xscale('symlog',linthresh=1);ax.set_xticks([0,1,3,10,30,100],['0','1','3','10','30','100'])
        ax.set_xlim(-.3,180)
        ax.set_yscale('log');ax.set_ylim(10,800);ax.set_yticks([10,20,40,100,200,600]);ax.yaxis.set_major_formatter(ScalarFormatter())
        ax.set(title='Stable identity, normal test' if case=='normal' else 'Different transmitter claims same RID',xlabel='True-distance labels per RID',ylabel='Distance MAE (m, log scale)');ax.grid(alpha=.2)
    axes[0].legend(fontsize=8)
    save(fig,'rid-learning','Assumed persistent ID variation SD=6dB and flight variation SD=1dB. OLS failures fall back and are counted.')
    profiles=[p['name'] for p in r['config']['personalization']['profiles']];x=np.arange(len(profiles))
    fig,ax=plt.subplots(figsize=(10.5,5))
    for i,(case,label,color) in enumerate([('normal','Normal',colors[0]),('tx_step8','Future TX +8dB',colors[1]),('cloned_rid','Cloned RID',colors[2])]):
        values=[]
        for profile in profiles:
            global_row=next(v for v in s['personalization'] if v['profile']==profile and v['scenario']==case and v['model']=='global' and v['labeled_per_rid']==30)
            rid_row=next(v for v in s['personalization'] if v['profile']==profile and v['scenario']==case and v['model']=='rid_shrinkage' and v['labeled_per_rid']==30)
            values.append(100*(1-rid_row['mae_m']/global_row['mae_m']))
        ax.bar(x+(i-1)*.24,values,.24,label=label,color=color)
    ax.set(xticks=x,xticklabels=['No ID\ndifference','ID SD3\nflight SD1','ID SD6\nflight SD1','ID SD6\nflight SD4','ID SD6\nflight SD8','ID + slope\nvariation'],ylabel='MAE reduction vs shared model (%)',title='30 labels per RID: personalization can help or hurt')
    ax.axhline(0,color='black',linewidth=1);ax.legend();ax.grid(axis='y',alpha=.2)
    save(fig,'rid-benefit-and-failure','Conditional synthetic improvements only; negative values mean worse. Enrollment flights are held out from test flights.')
    print('Six figure pairs saved (PNG/SVG).')


if __name__=='__main__':main()
