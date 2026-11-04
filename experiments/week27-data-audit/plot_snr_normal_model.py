"""Normal-only model transfer diagnostics using saved aggregate rows."""
import argparse,hashlib,json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np
from plot_paired_attacks import font_setup,export

METHODS=['constant','horizontal_geometry'];LABELS=['局ごとの一定差','一定差＋水平距離差'];COLORS=['#345f85','#bb7f25']

def footer(fig,text):
    fig.text(.09,.025,text+'\nUAV送信→屋上4局のLoRa SNR。高度未取得の2次元代理評価。攻撃検出率ではない。',fontsize=10,color='#555555')

def bars(ax,rows,sessions,field,factor=1):
    positions=np.arange(len(sessions))
    for i,(method,label,color) in enumerate(zip(METHODS,LABELS,COLORS)):
        groups=[[r[field]*factor for r in rows if r['method']==method and r['evaluation_session']==s] for s in sessions]
        means=np.array([np.mean(g) for g in groups]);lo=np.array([min(g) for g in groups]);hi=np.array([max(g) for g in groups])
        ax.bar(positions+(i-.5)*.34,means,.34,color=color,label=label,yerr=[means-lo,hi-means],capsize=4)
    ax.set_xticks(positions,sessions);ax.grid(axis='y',alpha=.2)


def draw(root):
    font=font_setup();j=json.loads((root/'summary.json').read_text());rows=j['rows'];out=root/'figures';out.mkdir(exist_ok=True)
    los=[r for r in rows if r['domain']=='LoS_holdout']
    fig,(a,b)=plt.subplots(1,2,figsize=(12,6.5));bars(a,los,['S1','S2','S3','S4'],'centered_snr_rmse_db')
    a.set(title='正常SNR差の予測誤差',ylabel='中心化SNRのRMSE（dB）',ylim=(0,9))
    bars(b,los,['S1','S2','S3','S4'],'normal_alarm_rate',100)
    b.axhline(5,color='#555555',ls='--',lw=1,label='校正目標5%');b.set(title='別セッションの正常警報率',ylabel='正常時の警報率（%）',ylim=(0,50))
    fig.suptitle('予測誤差が下がっても、警報閾値が通用するとは限らない',fontsize=17)
    fig.legend(*b.get_legend_handles_labels(),loc='upper center',bbox_to_anchor=(.5,.92),ncol=3,frameon=False)
    fig.subplots_adjust(top=.78,bottom=.24,wspace=.28)
    footer(fig,'訓練2・校正1・評価1のLoSセッション分離。棒は3分割平均、線は最小〜最大。\n分割はセッションを共有する。線は信頼区間ではない。S4で正常警報が増加。')
    export(fig,out,'01_los_prediction_and_normal_alarms')
    fig,ax=plt.subplots(figsize=(9.5,7));markers={'S1':'o','S2':'s','S3':'^','S4':'D'}
    limit=max(max(r['threshold_db'],r['score_p95_db']) for r in los)*1.1
    ax.plot([0,limit],[0,limit],ls='--',color='#555555',label='閾値＝評価スコア95%点')
    for i,method in enumerate(METHODS):
        for session,marker in markers.items():
            subset=[r for r in los if r['method']==method and r['evaluation_session']==session]
            ax.scatter([r['threshold_db'] for r in subset],[r['score_p95_db'] for r in subset],color=COLORS[i],marker=marker,s=65)
            if session=='S4' and method=='horizontal_geometry':
                for index,r in enumerate(sorted(subset,key=lambda r:r['threshold_db'])):
                    ax.annotate(f"S4・{r['normal_alarm_rate']*100:.1f}%",(r['threshold_db'],r['score_p95_db']),xytext=[(4.,9.7),(6.5,5.5),(4.3,11.2)][index],textcoords='data',fontsize=10,arrowprops=dict(arrowstyle='-',color='#777777'))
    ax.set(xlim=(0,limit),ylim=(0,limit),xlabel='別の正常セッションで校正した閾値（dB）',ylabel='評価セッションの正常スコア95%点（dB）',title='S4では、校正閾値より評価スコアが高い')
    handles=[Line2D([0],[0],color=c,marker='o',ls='',label=l) for c,l in zip(COLORS,LABELS)]
    handles += [Line2D([0],[0],color='#666666',marker=m,ls='',label=s) for s,m in markers.items()]
    ax.legend(handles=handles,ncol=3,fontsize=10);ax.grid(alpha=.2)
    fig.subplots_adjust(bottom=.25,top=.91)
    footer(fig,'各点は1分割・1方式。破線より上では正常スコア95%点が閾値を超える。\n訓練・校正・評価は別セッションだが、分割間には共有がある。')
    export(fig,out,'02_calibration_transfer')
    nlos=[r for r in rows if r['domain']=='NLoS_transfer']
    fig,(a,b)=plt.subplots(1,2,figsize=(11.5,6));bars(a,nlos,['S5','S6'],'normal_alarm_rate',100)
    a.axhline(5,color='#555555',ls='--',label='LoSでの校正目標5%');a.set(title='LoSで校正した閾値をNLoSへ適用',ylabel='正常時の警報率（%）',ylim=(0,35));a.legend(fontsize=10)
    counts=[next(r['evaluation_windows'] for r in nlos if r['evaluation_session']==s) for s in ['S5','S6']]
    b.bar(['S5：228送信','S6：48送信'],counts,color='#388477');b.set(title='時間区間を評価できるか',ylabel='10秒・5送信以上の集計区間数',ylim=(0,9))
    for i,n in enumerate(counts):b.text(i,n+.15,str(n),ha='center')
    b.grid(axis='y',alpha=.2);fig.subplots_adjust(top=.86,bottom=.25,wspace=.3)
    footer(fig,'NLoSは学習・校正に使用せず、12設定で繰り返し評価。線は設定間の最小〜最大。\n低い正常警報率は攻撃検出能力を意味しない。S6の時間区間は評価不可。')
    export(fig,out,'03_nlos_transfer_scope')
    code=[Path(__file__),Path(__file__).with_name('plot_paired_attacks.py')]
    manifest=dict(font=font,input_summary_sha256=hashlib.sha256((root/'summary.json').read_bytes()).hexdigest(),
        code_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in code},
        outputs={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.suffix in ('.png','.svg')})
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('result',type=Path);a=p.parse_args();draw(a.result)
