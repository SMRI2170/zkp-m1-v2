"""Actual D1 input diagnostics; never draw missing FPR/TPR as zero."""
import argparse
from collections import defaultdict
import csv
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager


def read(path):
    with path.open() as f:return list(csv.DictReader(f))


def save(fig,out,name,caption):
    caption='\n'.join(caption[i:i+58] for i in range(0,len(caption),58))
    fig.text(.06,.015,caption,fontsize=9,color='#444')
    fig.tight_layout(rect=(0,.11,1,.97))
    for ext in ['png','svg']:
        p=out/(name+'.'+ext);fig.savefig(p,dpi=180)
        if ext=='svg':p.write_text('\n'.join(l.rstrip() for l in p.read_text().splitlines())+'\n')
    plt.close(fig)


def first_distance(rows):
    accepted=[r for r in rows if r.get('status','').startswith('EXECUTED') and r.get('tpr') not in (None,'')]
    valid=[r for r in accepted if float(r['tpr'])>=.95 and float(r['fpr'])<=.05 and float(r['und_rate'])<=.05]
    return min(float(r['offset_m']) for r in valid) if valid else None


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('folder',type=Path);a=p.parse_args()
    x=json.loads((a.folder/'summary.json').read_text());out=a.folder/'figures';out.mkdir(exist_ok=True)
    available={f.name for f in font_manager.fontManager.ttflist}
    plt.rcParams.update({'font.family':next((v for v in ['Hiragino Sans','Noto Sans CJK JP','IPAexGothic'] if v in available),'DejaVu Sans'),'axes.unicode_minus':False,'svg.fonttype':'none'})
    rows=read(a.folder/'rss-time-blocks.csv');duration=x['source']['duration_s']
    lower=np.floor(min(float(v['q25_rss']) for v in rows)/5)*5-5
    upper=np.ceil(max(float(v['q75_rss']) for v in rows)/5)*5+5
    fig,axes=plt.subplots(5,1,figsize=(11,12),sharex=True)
    for j,ax in enumerate(axes,1):
        for ch,color in [(1,'#16365d'),(2,'#1684c0')]:
            r=[v for v in rows if v['station']==f'LW{j}' and v['channel']==str(ch)]
            t=[float(v['elapsed_start_s'])+10 for v in r]
            ax.plot(t,[float(v['median_rss']) for v in r],label=f'ch{ch}',color=color,lw=1.4)
            ax.fill_between(t,[float(v['q25_rss']) for v in r],[float(v['q75_rss']) for v in r],alpha=.12,color=color)
        ax.set_ylabel(f'LW{j}\n保存RSS [dB]');ax.set_ylim(lower,upper);ax.grid(alpha=.2)
        for left,right,color in [(0,.4,'#1684c0'),(.45,.65,'#379469'),(.7,1,'#dc863e')]:ax.axvspan(left*duration,right*duration,color=color,alpha=.08)
    axes[0].legend(loc='best');axes[0].set_title('D1実測RSSの時間変動：青＝学習、緑＝校正、橙＝評価、空白＝隔離区間',fontsize=12)
    axes[-1].set_xlabel('LW1の先頭RSSからの経過時間 [s]')
    save(fig,out,'01_measured_rss','全局で同じ縦軸。20秒区間の中央値と四分位帯。D3のRT補正は不使用。独立校正済み絶対dBmやパケット受信成功を示す図ではない。')
    availability=read(a.folder/'availability.csv')
    fig,ax=plt.subplots(figsize=(9,5.5))
    for span,color in [(.02,'#16365d'),(.1,'#1684c0'),(.2,'#dc863e'),(.5,'#783f99')]:
        curve=sorted([r for r in availability if float(r['max_span_s'])==span and float(r['missing'])==0 and float(r['lag_s'])==0],key=lambda r:int(r['k']))
        ax.plot([int(r['k']) for r in curve],[100*float(r['candidate_rate']) for r in curve],'o-',color=color,label=f'記録時刻幅 {span*1000:g}ms以内')
    ax.set(xlabel='選択する局数（LW1から順に追加）',ylabel='再利用を除いた近接観測候補率 [%]',xticks=[1,2,3,4,5],ylim=(-2,102),title='実測入力の可用性：候補数と検出率を混同しない');ax.legend();ax.grid(alpha=.2)
    save(fig,out,'02_receiver_availability','評価区間のLW1 1,099観測が分母。局の追加は同じ送信の追加受信ではない。位置偽装の検出率・判定可能率ではない。')
    fig,ax=plt.subplots(figsize=(9,5.5))
    for k,color in [(1,'#16365d'),(4,'#1684c0'),(5,'#dc863e')]:
        means=[];low=[];high=[]
        for missing in [0,.1,.3,.5]:
            rr=[r for r in availability if int(r['k'])==k and float(r['max_span_s'])==.2 and float(r['lag_s'])==0 and float(r['missing'])==missing]
            v=[100*int(r['complete_windows'])/int(r['reference_windows']) for r in rr]
            means.append(np.mean(v));low.append(min(v));high.append(max(v))
        xx=[0,10,30,50];ax.plot(xx,means,'o-',label=f'{k}局',color=color);ax.fill_between(xx,low,high,color=color,alpha=.12)
    ax.set(xlabel='人工的に欠測させた元観測の割合 [%]',ylabel='5秒窓に5候補を用意できた割合 [%]',ylim=(-2,102),title='実測系列＋合成欠測：再利用なしの5候補が必要');ax.legend();ax.grid(alpha=.2)
    save(fig,out,'03_missingness','記録時刻幅200ms。帯は合成欠測20パターンの範囲で、独立飛行の信頼区間ではない。GhostBuster検出率ではない。')
    fig,ax=plt.subplots(figsize=(9,5.5))
    for k,color in [(4,'#1684c0'),(5,'#dc863e')]:
        rr=sorted([r for r in availability if int(r['k'])==k and float(r['max_span_s'])==.2 and float(r['missing'])==0],key=lambda r:float(r['lag_s']))
        ax.plot([float(r['lag_s']) for r in rr],[100*int(r['complete_windows'])/int(r['reference_windows']) for r in rr],'o-',label=f'{k}局',color=color)
    ax.set_xscale('symlog',linthresh=.05);ax.set_xticks([0,.05,.2,1,10,3600],['0','0.05','0.2','1','10','3600'])
    ax.set(xlabel='後段局が選ぶ実測時刻の追加遅れ [s]',ylabel='5秒窓に5候補を用意できた割合 [%]',ylim=(-2,102),title='別時刻の観測を選択：時刻ラベルの改竄ではない');ax.legend();ax.grid(alpha=.2)
    save(fig,out,'04_observation_lag','RSSと元時刻の対応は保持。記録時刻幅200msゲートによる可用性の検査。遅れが大きいと使えないのは設定上の制約で、検知性能の成果ではない。')
    metric=read(a.folder/'metrics.csv')
    if not x['geometric_detection_executed']:
        (out/'position_detection_graph_NOT_GENERATED.md').write_text('受信局座標・共有高さ基準が未確認のため、位置偽装の検出率／電力操作の検出性能グラフは未生成。空欄を0%に置換しない。\n')
    else:
        fig,ax=plt.subplots(figsize=(9,5.5))
        for k,color in [(1,'#16365d'),(4,'#1684c0'),(5,'#dc863e')]:
            rr=sorted([r for r in metric if r['status'].startswith('EXECUTED') and r['channel']=='1' and int(r['k'])==k and r['power']=='unchanged' and float(r['lag_s'])==0 and float(r['missing'])==0],key=lambda r:float(r['offset_m']))
            if rr:
                ax.plot([float(r['offset_m']) for r in rr],[100*float(r['tpr']) for r in rr],'o-',color=color,label=f'{k}局 TPR')
                ax.axhline(100*float(rr[0]['fpr']),color=color,ls='--',label=f'{k}局 正常FPR')
        ax.set(xlabel='合成した東方向の位置偽装距離 [m]',ylabel='警報率 [%：全5秒窓が分母]',ylim=(-2,102));ax.legend();ax.grid(alpha=.2)
        save(fig,out,'05_detection','生RSSはD1実測、申告は補間GPSから合成。多局は近接時刻の静止近似であり同一送信ではない。1飛行内の評価で一般的性能ではない。')
        fig,axes=plt.subplots(1,2,figsize=(12,5.5))
        for ax,k in zip(axes,[1,5]):
            for power,color in [('unchanged','#16365d'),('constant_plus6db','#1684c0'),('sinusoid_6db_period2s','#dc863e'),('reference0_compensation_clip10db_n2','#783f99')]:
                rr=sorted([r for r in metric if r['status'].startswith('EXECUTED') and r['channel']=='1' and int(r['k'])==k and r['power']==power and float(r['lag_s'])==0 and float(r['missing'])==0],key=lambda r:float(r['offset_m']))
                if rr:ax.plot([0]+[float(r['offset_m']) for r in rr],[100*float(rr[0]['fpr'])]+[100*float(r['tpr']) for r in rr],'o-',color=color,label=power)
            ax.set(title=f'{k}局：電力操作への応答',xlabel='合成位置偽装距離 [m]',ylabel='警報率 [%：全5秒窓が分母]',ylim=(-2,102));ax.legend(fontsize=7);ax.grid(alpha=.2)
        save(fig,out,'06_power_detection','0mはその電力条件で位置を変えていない正常対照。電力・位置変更は合成で、RF受信欠落の変化を実測した結果ではない。')
    # A distance is meaningful only under the predeclared FPR/TPR/UND criteria.
    groups=defaultdict(list)
    for r in metric:
        key=tuple(r.get(v,'') for v in ['channel','k','lag_s','missing','seed','power'])
        groups[key].append(r)
    with (a.folder/'detection-distance.csv').open('w',newline='') as f:
        w=csv.writer(f,lineterminator='\n');w.writerow(['channel','k','lag_s','missing','seed','power','first_tested_distance_m','status'])
        for key,rr in groups.items():
            distance=first_distance(rr);w.writerow([*key,distance,'NOT_RUN' if not any(r['status'].startswith('EXECUTED') for r in rr) else ('NOT_ESTABLISHED' if distance is None else 'CONDITIONAL_SINGLE_FLIGHT_POINT')])


if __name__=='__main__':main()
