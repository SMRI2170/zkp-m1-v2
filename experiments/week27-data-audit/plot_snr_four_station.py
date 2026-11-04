"""Render aggregate four-station SNR results; no raw captures required."""
import argparse,hashlib,json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from plot_paired_attacks import font_setup,export

COLORS=['#345f85','#bb7f25','#388477','#ae5555','#8263a5','#6a747a']

def footer(fig,text):
    fig.text(.09,.025,text+'\nUAV送信→屋上4局受信のLoRa実測。RSSI・受信機固有の校正値・攻撃検出率ではない。',fontsize=10,color='#555555')

def draw(root):
    font=font_setup();data=json.loads((root/'summary.json').read_text());tables=data['tables'];out=root/'figures';out.mkdir(exist_ok=True)
    quality=tables['session_quality'];sessions=[r['session'] for r in quality];pairs=['1-2','1-3','1-4','2-3','2-4','3-4']
    labels={r['session']:r['session']+(' LoS' if r['area_types']=='drone_los' else ' NLoS') for r in quality}
    fig,axes=plt.subplots(2,3,figsize=(12.5,8.0),sharey=True)
    for ax,pair in zip(axes.flat,pairs):
        bounds=[]
        for i,session in enumerate(sessions):
            rows=[r for r in tables['histograms'] if r['kind']=='pair' and r['quantity']==pair and r['session']==session]
            rows.sort(key=lambda r:r['lower_db']);counts=np.array([r['count'] for r in rows]);upper=np.array([r['upper_db'] for r in rows]);lo=rows[0]['lower_db']
            ax.step(np.r_[lo,upper],np.r_[0,np.cumsum(counts)/counts.sum()],where='post',color=COLORS[i],label=labels[session])
            occupied=np.flatnonzero(counts)
            bounds.extend([rows[occupied[0]]['lower_db'],rows[occupied[-1]]['upper_db']])
        ax.set_title(f'RRH{pair[0]} − RRH{pair[2]}');ax.set_xlim(min(bounds)-2,max(bounds)+2);ax.set_ylim(0,1.02)
        ax.set_xlabel('同一送信のSNR差（dB）');ax.grid(alpha=.2)
    for ax in axes[:,0]:ax.set_ylabel('累積割合（2dB幅の集計）')
    fig.suptitle('4局の同一送信：局ペアのSNR差分布',fontsize=18,y=.985)
    fig.legend(*axes.flat[0].get_legend_handles_labels(),loc='upper center',bbox_to_anchor=(.5,.94),ncol=6,frameon=False)
    fig.subplots_adjust(top=.83,bottom=.19,hspace=.38,wspace=.25)
    footer(fig,'6,728送信の完全ケース。各曲線は別セッション。6ペアは代数的に独立ではない。')
    export(fig,out,'01_pair_distributions')
    matrix=np.array([[next(r['median_db'] for r in tables['station_stats'] if r['session']==s and r['quantity']==str(i)) for i in range(1,5)] for s in sessions])
    drift=np.array([[next(r['late_minus_early_db'] for r in tables['station_stats'] if r['session']==s and r['quantity']==str(i)) for i in range(1,5)] for s in sessions],dtype=float)
    fig,axes=plt.subplots(1,2,figsize=(12,6.5))
    for ax,values,title,scale in zip(axes,[matrix,drift],['局別の中心化SNR中央値','時間の最終1/3 − 最初1/3'],[10,4]):
        cmap=plt.get_cmap('RdBu_r').copy();cmap.set_bad('#dddddd')
        im=ax.imshow(np.ma.masked_invalid(values),cmap=cmap,vmin=-scale,vmax=scale,aspect='auto')
        ax.set_xticks(range(4),[f'RRH{i}' for i in range(1,5)]);ax.set_yticks(range(6),[labels[s] for s in sessions]);ax.set_title(title)
        for iy,ix in np.ndindex(values.shape):
            v=values[iy,ix];text='評価不可' if np.isnan(v) else f'{v:+.2f}'
            ax.text(ix,iy,text,ha='center',va='center',fontsize=11,color='white' if np.isfinite(v) and abs(v)>scale*.6 else 'black')
        fig.colorbar(im,ax=ax,label='dB',shrink=.9)
    fig.suptitle('局別偏差と時間変化を分けて見る',fontsize=18)
    fig.subplots_adjust(top=.86,bottom=.23,wspace=.4)
    footer(fig,'中心化＝各局SNR − 同じ送信の4局平均。伝搬・雑音・受信系統が混在する記述量。\n右は各区間20送信以上で計算。経路・位置が変わるため、ゲイン変動の実証ではない。')
    export(fig,out,'02_station_offsets_and_drift')
    station_windows=[r for r in tables['time_windows'] if r['kind']=='station']
    ybound=max(10,np.ceil(max(abs(r['median_db']) for r in station_windows)/5)*5)
    for kind,filename in [('station','03_station_time_variation'),('pair','04_pair12_time_variation')]:
        fig,axes=plt.subplots(3,2,figsize=(12.5,9.5))
        for ax,q in zip(axes.flat,quality):
            s=q['session'];length=int(np.floor(q['duration_s']/10));x=(np.arange(length)+.5)*10/60
            rows=[r for r in tables['time_windows'] if r['session']==s and r['kind']==kind]
            if not rows:ax.text(.5,.5,'集計可能な10秒区間なし',transform=ax.transAxes,ha='center',color='#666666')
            for i,label in enumerate(['1','2','3','4'] if kind=='station' else ['1-2']):
                selected=[r for r in rows if r['quantity']==label];median=np.full(length,np.nan);lo=median.copy();hi=median.copy()
                for r in selected:
                    k=r['window_index'];median[k]=r['median_db'];lo[k]=r['p05_db'];hi[k]=r['p95_db']
                ax.plot(x,median,color=COLORS[i],marker='.',ms=3,label=f'RRH{label}' if kind=='station' else 'RRH1 − RRH2')
                if kind=='pair':ax.fill_between(x,lo,hi,color=COLORS[i],alpha=.2,label='区間内5〜95%点')
            ax.axhline(0,color='#777777',lw=.7);ax.set_xlim(0,max(q['duration_s']/60,1));ax.set_xlabel('セッション内の経過時間（分）')
            ax.set_ylabel('中心化SNR（dB）' if kind=='station' else 'SNR差（dB）');ax.grid(alpha=.2)
            ax.set_title(f"{labels[s]}：{q['n']:,}送信 / {q['accepted_windows']}区間")
            if kind=='station':ax.set_ylim(-ybound,ybound)
            else:ax.set_ylim(-35,35)
        title='局別の相対SNRは時間とともにどう変わるか' if kind=='station' else 'RRH1 − RRH2：SNR差の時間変動と区間内の広がり'
        fig.suptitle(title,fontsize=17,y=.985)
        fig.legend(*axes.flat[0].get_legend_handles_labels(),loc='upper center',bbox_to_anchor=(.5,.95),ncol=4,frameon=False)
        fig.subplots_adjust(top=.88,bottom=.17,hspace=.6,wspace=.25)
        footer(fig,'10秒区間に5送信以上ある場合だけ集計。欠測区間は線をつながず、補間しない。\n中央値の推移。帯は区間内の記述的な分位点で、信頼区間ではない。' if kind=='pair' else '10秒区間に5送信以上ある場合だけ中央値を集計。欠測区間を補間しない。\n伝搬環境や経路の変化も含むため、受信機・雑音床の安定性だけを測った結果ではない。')
        export(fig,out,filename)
    code=[Path(__file__),Path(__file__).with_name('plot_paired_attacks.py')]
    manifest=dict(font=font,input_summary_sha256=hashlib.sha256((root/'summary.json').read_bytes()).hexdigest(),
        code_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in code},
        outputs={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.suffix in ('.png','.svg')})
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('result',type=Path);a=p.parse_args();draw(a.result)
