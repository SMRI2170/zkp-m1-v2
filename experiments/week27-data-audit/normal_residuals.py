"""Normal-only residual audit using already acquired UAV-received LoRa data.

This is an extension of Week26, not a new flight or AADM substitute.
"""
import argparse
import csv
import importlib.util
import json
from pathlib import Path
import numpy as np


def analyze(archive):
    module_path=Path(__file__).resolve().parents[1]/'week26-rssi-privacy/recheck_lora.py'
    spec=importlib.util.spec_from_file_location('verified_lora',module_path)
    source=importlib.util.module_from_spec(spec);spec.loader.exec_module(source)
    groups,inventory,sources=source.load(archive)
    metrics=[];hist={};edges=np.arange(-50,52,2)
    for condition,runs in groups.items():
        if len(runs)!=3:continue
        ids=sorted(runs)
        for fold in range(3):
            train,cal,test=[runs[ids[(fold+i)%3]] for i in range(3)]
            empirical=source.fit_model(train)
            fixed=np.array([np.mean(train['r']+20*np.log10(train['d'])),-20.])
            for model_name,model in [('empirical_slope',empirical),('fixed_n_2',fixed)]:
                calibration=cal['r']-source.expected(model,cal['d'])
                residual=test['r']-source.expected(model,test['d'])
                threshold=float(np.quantile(np.abs(calibration),.95))
                adjacent=np.diff(test['t'])<=2
                lag=None
                if adjacent.sum()>2:
                    a=residual[:-1][adjacent];b=residual[1:][adjacent]
                    if a.std()>0 and b.std()>0:lag=float(np.corrcoef(a,b)[0,1])
                metrics.append(dict(condition=condition,fold=fold,model=model_name,
                    training_run=ids[fold],calibration_run=ids[(fold+1)%3],evaluation_run=ids[(fold+2)%3],
                    n_fit=float(-model[1]/10),evaluation_received_packets=len(residual),
                    residual_mean_db=float(residual.mean()),residual_sd_db=float(residual.std(ddof=1)),
                    rmse_db=float(np.sqrt(np.mean(residual**2))),normal_threshold_db=threshold,
                    normal_alarm_rate=float(np.mean(np.abs(residual)>threshold)),lag1_received_packet_corr=lag))
                counts,_=np.histogram(residual,edges)
                old=hist.setdefault(model_name,dict(counts=np.zeros(len(edges)-1,dtype=int),below=0,above=0))
                old['counts']+=counts;old['below']+=int(np.sum(residual<edges[0]));old['above']+=int(np.sum(residual>edges[-1]))
    means={}
    for model in hist:
        rows=[r for r in metrics if r['model']==model]
        means[model]={key:float(np.mean([r[key] for r in rows])) for key in ['rmse_db','normal_alarm_rate','residual_sd_db','residual_mean_db','lag1_received_packet_corr']}
    return dict(source_url=source.URL,source_sha256=source.SHA256,
        raw_observations=sum(x['rows'] for x in inventory),conditions=len(groups),run_groups=len(inventory),
        comparison_conditions=len({r['condition'] for r in metrics}),folds_per_model=len(metrics)//2,
        distance_label='Flat-terrain slant-range proxy from UAV AGL and buried fixed transmitter',
        scope='Previously acquired real UAV-receiver LoRa, normal received packets only; no Remote ID or synthetic attacks',
        split='Within each condition, 3 cyclic train/calibration/test run roles. Shared runs: folds are not independent.',
        baseline='n=2 assumed; intercept OLS mean fitted to training run. Empirical slope OLS fitted to training run.',
        threshold='95th percentile absolute residual on separate calibration run; no evaluation-time recalibration',
        means=means,metrics=metrics,
        histogram=dict(edges_db=edges.tolist(),models={k:dict(counts=v['counts'].tolist(),below=v['below'],above=v['above']) for k,v in hist.items()}),
        limits=['Fixed ground transmitter to flying UAV receiver, opposite to RID monitoring',
                'Actual transmit power and multipath contributions cannot be separated from RSSI',
                'Packets are received samples, not a known full-transmission population',
                'Unequal packet counts and shared conditions; means are descriptive, not independent-trial confidence intervals'])


def plot(report, out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(1,3,figsize=(14,4.5),layout='constrained')
    colors={'empirical_slope':'#205383','fixed_n_2':'#bb7430'}
    labels={'empirical_slope':'Fitted slope (train run)','fixed_n_2':'Assumed n=2 (train intercept)'}
    edges=np.array(report['histogram']['edges_db']);centers=(edges[1:]+edges[:-1])/2
    for model in colors:
        rows=[r for r in report['metrics'] if r['model']==model]
        counts=np.array(report['histogram']['models'][model]['counts'])
        total=counts.sum()+report['histogram']['models'][model]['below']+report['histogram']['models'][model]['above']
        ax[0].plot(centers,counts/total*100,label=labels[model],color=colors[model])
        # Aggregate per condition; do not draw individual measured packet records.
        conditions=sorted({r['condition'] for r in rows})
        fpr=[np.mean([r['normal_alarm_rate'] for r in rows if r['condition']==c])*100 for c in conditions]
        ax[1].plot(range(len(fpr)),fpr,'o-',label=labels[model],color=colors[model])
        correlations=[r['lag1_received_packet_corr'] for r in rows]
        ax[2].hist(correlations,bins=np.linspace(-1,1,21),histtype='step',lw=2,label=labels[model],color=colors[model])
    ax[0].set(title='Held-out normal residuals',xlabel='Measured - predicted RSSI (dB)',ylabel='Received packets (%) per 2 dB bin')
    ax[1].axhline(5,color='gray',ls='--',label='Calibration target 5%')
    ax[1].set_ylim(0,10)
    ax[1].set(title='Normal alarms on other runs',xlabel='Condition (3 cyclic splits averaged)',ylabel='Alarm rate (%)',xticks=range(16))
    ax[1].set_xticklabels(conditions,rotation=70,fontsize=8)
    ax[2].set(title='Adjacent residuals are correlated',xlabel='Lag-1 correlation (gaps <= 2 s)',ylabel='Fold count')
    for a in ax:a.grid(alpha=.2);a.legend(fontsize=7)
    fig.suptitle('Real UAV-received LoRa: normal data audit; not RID spoofing detection',fontsize=12)
    fig.savefig(out/'normal-residual-audit.png',dpi=160);fig.savefig(out/'normal-residual-audit.svg');plt.close(fig)
    svg=out/'normal-residual-audit.svg'
    svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines())+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--archive',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    if a.out.exists():raise ValueError('Use a new output directory; preserving prior evidence')
    result=analyze(a.archive);a.out.mkdir(parents=True)
    (a.out/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    with (a.out/'fold-metrics.csv').open('w') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(result['metrics'][0]),lineterminator='\n');writer.writeheader();writer.writerows(result['metrics'])
    plot(result,a.out)
    print(json.dumps({k:result[k] for k in ('raw_observations','comparison_conditions','folds_per_model','means')},indent=2))
