"""Scientific PR5 plots from public seed aggregates; never renders raw XYZ."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import statistics

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from run_observer_attack import bootstrap

CASES=['position_only','reference_rx0','schedule_aware','schedule_blind']
COLORS=['#b97616','#b13e45','#175d9c','#2d805b']
NAMES=['A: position only','B: receiver 0 compensation','C: selected-receiver oracle','D: blind receiver prior']


def read(path):
    with path.open() as f:return list(csv.DictReader(f))


def number(row,key):return float(row[key]) if row and row[key] not in ['','None'] else np.nan


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('results',type=Path);p.add_argument('mlat',type=Path);a=p.parse_args()
    rows=read(a.results/'aggregate-metrics.csv');factors=read(a.results/'factor-aggregate.csv')
    out=a.results/'figures';out.mkdir(exist_ok=True)
    def find(link,case,offset,bound,method='SingleResidual',phy='default'):
        selected=[r for r in rows if r['phy']==phy and r['link']==link and r['attack_case']==case and int(r['offset_m'])==offset and int(r['bound_db'])==bound and r['method']==method]
        return selected[0] if len(selected)==1 else None
    def save(fig,name):
        for ext in ['png','svg']:fig.savefig(out/f'{name}.{ext}',dpi=160)
        plt.close(fig)
    def error_curve(ax,x,selected,metric,**kwargs):
        y=np.array([100*number(r,metric+'_mean') for r in selected]);low=np.array([100*number(r,metric+'_low') for r in selected]);high=np.array([100*number(r,metric+'_high') for r in selected])
        ax.errorbar(x,y,yerr=np.maximum(0,np.array([y-low,high-y])),capsize=3,marker='o',**kwargs)
    plt.rcParams.update({'font.size':10,'axes.spines.right':False,'axes.spines.top':False})
    for method in ['SingleResidual','KF_NIS','DRSS5']:
        fig,axes=plt.subplots(2,2,figsize=(14,9),layout='constrained',sharey=True)
        for ax,(link,offset) in zip(axes.flat,[(l,o) for l in ['strong','edge'] for o in [30,100]]):
            for case,color,label in zip(CASES,COLORS,NAMES):
                selected=[find(link,case,offset,0 if case=='position_only' else bound,method) for bound in [3,6,10,20]]
                error_curve(ax,[3,6,10,20],selected,'alarm_scored',color=color,label=label)
            normal=find(link,'normal',0,0,method)
            fpr=100*number(normal,'alarm_scored_mean')
            if np.isfinite(fpr):ax.axhline(fpr,color='#555555',linestyle=':',label='Normal FPR')
            ax.set(title=f'{link}, {offset} m claim offset',xticks=[3,6,10,20],ylim=(-3,105),xlabel='Attack compensation bound (+/- dB)',ylabel='Alarm / scored transmissions (%)');ax.grid(alpha=.2)
        handles,labels=axes.flat[0].get_legend_handles_labels();fig.legend(handles,labels,loc='outside lower center',ncol=3)
        fig.suptitle(f'{method}: power knowledge and bounds, conditional on scoring\n20 evaluation seeds; normal-only frozen calibration; seed bootstrap 95% CI; missing receptions remain UND. C is a synthetic schedule oracle.')
        save(fig,f'bound-sensitivity-{method}')
    fig,axes=plt.subplots(1,3,figsize=(16,5),layout='constrained',sharey=True)
    for ax,link in zip(axes,['strong','edge','weak']):
        for j,(metric,color,label) in enumerate([('received_rate','#8998a4','Selected RX received'),('alarm_all_tx','#175d9c','FLAG / all TX'),('und_rate','#b97616','UND / all TX')]):
            selected=[find(link,case,100,0 if case=='position_only' else 10) for case in CASES]
            y=[100*number(r,metric+'_mean') for r in selected]
            ax.bar(np.arange(4)+(j-1)*.25,y,width=.24,label=label,color=color)
        ax.set(title=f'{link}: 100 m, +/-10 dB',xticks=range(4),xticklabels=['A','B','C','D'],ylim=(0,105),ylabel='Fraction of all transmissions (%)');ax.grid(axis='y',alpha=.2)
    fig.legend(*axes[0].get_legend_handles_labels(),loc='outside lower center',ncol=3)
    fig.suptitle('SingleResidual: changing received sets and abstentions\nNo reception is not a BELOW-threshold verdict. Same trajectories and schedule, physically different transmit powers.')
    save(fig,'received-and-all-tx')
    fig,axes=plt.subplots(1,2,figsize=(13,5),layout='constrained')
    for ax,metric,title in zip(axes,['attack_bound_clamped_rate_mean','phy_clamped_rate_mean'],['Clipped by attack bound (%)','Clipped by physical output limits (%)']):
        matrix=[];labels=[]
        for link in ['strong','edge']:
            for case in CASES[1:]:
                labels.append(link+' / '+case)
                matrix.append([100*number(next((r for r in factors if r['phy']=='default' and r['link']==link and r['attack_case']==case and int(r['offset_m'])==100 and int(r['bound_db'])==bound),None),metric) for bound in [3,6,10,20]])
        matrix=np.asarray(matrix);image=ax.imshow(matrix,vmin=0,vmax=100,cmap='Blues',aspect='auto')
        ax.set(title=title,xticks=range(4),xticklabels=['3','6','10','20'],yticks=range(len(labels)),yticklabels=labels,xlabel='Compensation bound (+/- dB)')
        for i,j in np.ndindex(matrix.shape):ax.text(j,i,f'{matrix[i,j]:.1f}',ha='center',va='center',color='white' if matrix[i,j]>60 else 'black')
    fig.colorbar(image,ax=axes,label='% of physical transmissions');fig.suptitle('100 m attack: two distinct clipping mechanisms\nCounts can overlap; they are not disjoint failure categories.')
    save(fig,'clipping-mechanisms')
    fig,axes=plt.subplots(2,3,figsize=(16,9),layout='constrained',sharey=True)
    settings=['default','upper13','lower_minus8','upper40'];setting_labels=['[-80,23]','[-80,13]','[-8,23]','[-80,40]']
    for col,link in enumerate(['strong','edge','weak']):
        selected=[find(link,'schedule_aware',100,10,phy=phy) for phy in settings]
        normal=[find(link,'normal',0,0,phy=phy) for phy in settings]
        error_curve(axes[0,col],range(4),selected,'alarm_scored',color='#175d9c',label='C: conditional TPR')
        error_curve(axes[0,col],range(4),normal,'alarm_scored',color='#555555',linestyle=':',label='Normal conditional FPR')
        for metric,color,label in [('alarm_all_tx','#175d9c','FLAG / all TX'),('received_rate','#2d805b','Received / all TX'),('und_rate','#b97616','UND / all TX')]:
            error_curve(axes[1,col],range(4),selected,metric,color=color,label=label)
        for row in range(2):axes[row,col].set(title=link,xticks=range(4),xticklabels=setting_labels,ylim=(-3,105),ylabel='%',xlabel='Physical [minimum, maximum] dBm');axes[row,col].grid(alpha=.2)
    axes[0,0].legend(fontsize=8);axes[1,0].legend(fontsize=8)
    fig.suptitle('C: physical-limit ablation at 100 m / +/-10 dB attack bound\nEach physical setting has its own NORMAL-only calibration. Upper40 is a synthetic stress condition, not a deployable transmitter claim.')
    save(fig,'physical-limits')
    diffs=read(a.results/'B-to-C-paired-difference.csv')
    fig,axes=plt.subplots(1,2,figsize=(13,5),layout='constrained',sharey=True)
    for ax,link in zip(axes,['strong','edge']):
        for method,color in [('SingleResidual','#175d9c'),('KF_NIS','#b97616'),('DRSS5','#2d805b')]:
            selected=[next((r for r in diffs if r['link']==link and int(r['offset_m'])==100 and int(r['bound_db'])==bound and r['method']==method),None) for bound in [3,6,10,20]]
            error_curve(ax,[3,6,10,20],selected,'C_minus_B_alarm_all_tx',color=color,label=method)
        ax.axhline(0,color='#555555',linestyle=':');ax.set(title=link,xticks=[3,6,10,20],xlabel='Compensation bound (+/- dB)',ylabel='C minus B: FLAG / all TX (percentage points)');ax.grid(alpha=.2)
    fig.legend(*axes[0].get_legend_handles_labels(),loc='outside lower center',ncol=3)
    fig.suptitle('Schedule knowledge: paired seed differences, 100 m claim offset\nNegative means fewer flags under C, not a verified position. All-TX denominator retains reception loss and UND.')
    save(fig,'B-to-C-all-tx-difference')
    model_file=a.results/'model-decomposition.csv'
    if model_file.exists():
        component_rows=read(model_file);fig,axes=plt.subplots(1,2,figsize=(13,5),layout='constrained',sharey=True)
        fields=['clipping','antenna','surrogate','observed']
        for ax,phy in zip(axes,['default','upper40']):
            values=[];low=[];high=[]
            selected=[r for r in component_rows if r['phy']==phy and int(r['offset_m'])==100 and int(r['bound_db'])==10]
            for field in fields:
                ci=bootstrap([float(r[f'{field}_centered_mean_abs_db']) for r in selected],1000)
                values.append(ci['mean']);low.append(ci['mean']-ci['low']);high.append(ci['high']-ci['mean'])
            ax.bar(range(4),values,yerr=np.array([low,high]).clip(0),capsize=3,color=['#b97616','#2d805b','#8998a4','#175d9c'])
            ax.set(title=f'C / {phy}: 100 m, +/-10 dB',xticks=range(4),xticklabels=['Power\nclipping','True vs claim\nantenna gain','Normal surrogate\nmodel at claim','Observed\nresidual'],ylabel='Centered mean absolute component (dB)');ax.grid(axis='y',alpha=.2)
        fig.suptitle('Why residuals remain under the schedule oracle\nPosthoc signed identity verified against actual RF. Centered component magnitudes are NOT additive causal shares; no gain-aware RF attack was run.')
        save(fig,'oracle-residual-components')
    mlat=read(a.mlat/'aggregate-metrics.csv');diagnostics=read(a.mlat/'solver-start-summary.csv')
    fig,axes=plt.subplots(1,2,figsize=(13,5),layout='constrained')
    methods=['upstream4','upstream5','multistart4','multistart5']
    for offset,color,label in [(0,'#555555','Normal FPR'),(100,'#175d9c','100 m TPR')]:
        chosen=[next(r for r in mlat if r['method']==m and int(r['offset_m'])==offset) for m in methods]
        error_curve(axes[0],np.arange(4)+(.05 if offset else -.05),chosen,'alarm_scored',linestyle='none',color=color,label=label)
    thresholds=json.loads((a.mlat/'thresholds.json').read_text());axes[1].bar(range(4),[thresholds[m] for m in methods],color=['#555555','#777777','#175d9c','#3786c4'])
    for ax in axes:ax.set(xticks=range(4),xticklabels=['Upstream\n4 RX','Upstream\n5 RX','Multi-start\n4 RX','Multi-start\n5 RX'])
    axes[0].set(ylabel='Conditional alarm (%)',ylim=(-3,105));axes[0].legend();axes[1].set(ylabel='Normal calibration threshold (m)')
    fig.suptitle('MLAT: unchanged upstream baseline versus separately calibrated multi-start\n50 hash-verified PR4 RF scenes reused; no new RF. Truth is never used to initialize or choose solutions.')
    save(fig,'mlat-baseline-and-multistart')
    initializations=list(dict.fromkeys(r['initialization'] for r in diagnostics))
    fig,axes=plt.subplots(1,3,figsize=(17,6),layout='constrained')
    for ax,field,title,percentage in zip(axes,['error_to_truth_m_median','negative_heights','rank_deficient'],['Median of seed median normal error (m)','Negative estimated heights (%)','Rank-deficient Jacobian (%)'],[False,True,True]):
        matrix=[]
        for n in [4,5]:
            line=[]
            for init in initializations:
                group=[r for r in diagnostics if r['role']=='eval' and int(r['offset_m'])==0 and int(r['receivers'])==n and r['initialization']==init]
                line.append(100*sum(int(r[field]) for r in group)/sum(int(r['count']) for r in group) if percentage else statistics.median(float(r[field]) for r in group))
            matrix.append(line)
        matrix=np.asarray(matrix);image=ax.imshow(matrix,cmap='Blues',aspect='auto',vmin=0,vmax=100 if percentage else None)
        ax.set(title=title,xticks=range(len(initializations)),xticklabels=[v.replace('_',' ') for v in initializations],yticks=[0,1],yticklabels=['4 RX','5 RX']);ax.tick_params(axis='x',rotation=70)
        for i,j in np.ndindex(matrix.shape):ax.text(j,i,f'{matrix[i,j]:.1f}',ha='center',va='center',fontsize=8,color='white' if matrix[i,j]>(60 if percentage else np.max(matrix)*.6) else 'black')
        fig.colorbar(image,ax=ax)
    fig.suptitle('Normal MLAT initialization and geometry diagnostics\n4 RX lie on one planar circle: unknown transmit power leaves a scale/height ambiguity. These are optimizer model diagnostics, not RF truth proofs.')
    save(fig,'mlat-initialization-and-rank')
    fig,axes=plt.subplots(2,3,figsize=(17,10),layout='constrained')
    fields=[('cost_median','Objective cost (median)',False),('estimated_power_dbm_median','Estimated power (dBm, median)',False),
            ('converged','Solver converged (%)',True),('power_bound_hits','Estimated-power boundary hits (%)',True),
            ('nfev_median','Function evaluations (median)',False),('column_scaled_condition_median','Column-scaled Jacobian condition',False)]
    for ax,(field,title,percentage) in zip(axes.flat,fields):
        for n,color in [(4,'#175d9c'),(5,'#b97616')]:
            values=[]
            for init in initializations:
                group=[r for r in diagnostics if r['role']=='eval' and int(r['offset_m'])==0 and int(r['receivers'])==n and r['initialization']==init]
                valid=[float(r[field]) for r in group if r[field]!='']
                values.append(100*sum(valid)/sum(int(r['count']) for r in group) if percentage else statistics.median(valid) if valid else np.nan)
            ax.plot(range(len(values)),values,'o-',color=color,label=f'{n} RX')
        ax.set(title=title,xticks=range(len(initializations)),xticklabels=[s.replace('_',' ') for s in initializations]);ax.tick_params(axis='x',rotation=70);ax.grid(alpha=.2)
        if field=='column_scaled_condition_median':ax.set_yscale('log');ax.text(.02,.95,'4 RX: rank-deficient (no finite condition)',transform=ax.transAxes,va='top',fontsize=8)
        if percentage:ax.set_ylim(-3,105)
        if field=='estimated_power_dbm_median':ax.axhline(-50,color='#888888',linestyle=':');ax.axhline(50,color='#888888',linestyle=':')
    fig.legend(*axes.flat[0].get_legend_handles_labels(),loc='outside lower center',ncol=2)
    fig.suptitle('Normal MLAT solver diagnostics across seven observable-only initializations\nConvergence/low cost is not unique-position identification; estimated-power bounds [-50,50]dBm are solver constraints, not PHY output limits.')
    save(fig,'mlat-solver-diagnostics')
    for svg in out.glob('*.svg'):svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines()).rstrip()+'\n')
    manifest=dict(status='GENERATED',matplotlib=matplotlib.__version__,source_sha256={name:hashlib.sha256((a.results/name).read_bytes()).hexdigest() for name in ['aggregate-metrics.csv','factor-aggregate.csv','B-to-C-paired-difference.csv']},
                  scope='Public aggregate figures only; no raw trajectories. CI uses scored seeds only for conditional rates; <2 scored seeds has no CI. Empty points are undefined, not zero.',figures=sorted(p.name for p in out.iterdir() if p.suffix in ['.png','.svg']))
    (out/'provenance.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(manifest,indent=2))


if __name__=='__main__':main()
