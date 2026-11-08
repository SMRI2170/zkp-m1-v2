"""Alternative views of existing D1 input aggregates, NOT detection performance.

Creates new artifacts; never overwrites the original experiment or manifests.
"""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager


def read(path):
    with path.open() as f:return list(csv.DictReader(f))


def select(rows,k,missing=0.,span=.2,lag=0.):
    return [r for r in rows if int(r['k'])==k and float(r['missing'])==missing and float(r['max_span_s'])==span and float(r['lag_s'])==lag]


def rates(rows):return np.array([100*int(r['complete_windows'])/int(r['reference_windows']) for r in rows])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True);parser.add_argument('--out',type=Path,required=True)
    a=parser.parse_args()
    if a.out.exists():parser.error('New gallery directory required; keep previous figures')
    a.out.mkdir(parents=True)
    summary=json.loads((a.source/'summary.json').read_text())
    availability=read(a.source/'availability.csv');rss=read(a.source/'rss-time-blocks.csv')
    names={f.name for f in font_manager.fontManager.ttflist}
    plt.rcParams.update({'font.family':next((n for n in ['Hiragino Sans','Noto Sans CJK JP','IPAexGothic'] if n in names),'DejaVu Sans'),
                         'font.size':11,'axes.unicode_minus':False,'svg.fonttype':'none'})
    blue='#16365d';orange='#db7e36';green='#288879';gray='#dedfe3';catalog=[]
    def save(fig,name,title,caption):
        caption='\n'.join(caption[i:i+58] for i in range(0,len(caption),58))
        fig.text(.06,.015,caption,fontsize=9,color='#444')
        fig.tight_layout(rect=(0,.13,1,.97))
        for ext in ['png','svg']:
            p=a.out/(name+'.'+ext);fig.savefig(p,dpi=180)
            if ext=='svg':p.write_text('\n'.join(l.rstrip() for l in p.read_text().splitlines())+'\n')
        plt.close(fig);catalog.append(dict(file=name,title=title,caption=caption))
    # Heatmap: only measured design cells, never interpolate missing K2/K3.
    ks=[1,4,5];missing=[0.,.1,.3,.5]
    table=np.array([[rates(select(availability,k,m)).mean() for m in missing] for k in ks])
    fig,ax=plt.subplots(figsize=(9,5.5));im=ax.imshow(table,vmin=0,vmax=100,cmap='Blues',aspect='auto')
    for i in range(3):
        for j in range(4):ax.text(j,i,f'{table[i,j]:.1f}%',ha='center',va='center',color='white' if table[i,j]>55 else blue,fontsize=16,fontweight='bold')
    ax.set_xticks(range(4),['0%','10%','30%','50%']);ax.set_yticks(range(3),['1局','4局','5局'])
    ax.set(xlabel='合成欠測率',ylabel='必要な受信局数',title='何局・どの欠測率なら、入力が揃うか')
    fig.colorbar(im,ax=ax,label='5秒窓に5候補が揃う割合 [%]')
    save(fig,'05_missing_heatmap','欠測率×局数のヒートマップ','実測時刻＋合成欠測。時刻幅200ms、評価54窓。欠測ありは20マスク平均。検出率ではなく入力成立率。')
    # Stacked bars use the SAME window denominator on both sides.
    fig,ax=plt.subplots(figsize=(9,5.5));ready=table[:,2];not_ready=100-ready
    ax.barh(range(3),ready,color=blue,label='入力が揃う');ax.barh(range(3),not_ready,left=ready,color=gray,label='入力不足')
    for i,(yes,no) in enumerate(zip(ready,not_ready)):
        ax.text(yes/2,i,f'{yes:.1f}%',ha='center',va='center',color='white',fontweight='bold',fontsize=14 if yes>10 else 10)
        if no>10:ax.text(yes+no/2,i,f'{no:.1f}%',ha='center',va='center',color='#444')
    ax.set_yticks(range(3),['1局','4局','5局']);ax.invert_yaxis();ax.set(xlim=(0,100),xlabel='評価窓の割合 [%]',title='30%欠測した場合：使える入力と不足する入力')
    ax.set_title('30%欠測した場合：使える入力と不足する入力',pad=43)
    ax.legend(loc='lower center',bbox_to_anchor=(.5,1.01),ncols=2,fontsize=9);ax.grid(axis='x',alpha=.15)
    save(fig,'06_ready_vs_unavailable','入力成立／不足の積み上げ棒','同じ54窓が分母。20マスクの平均。灰色は不正の見逃しではなく、必要な観測が不足した窓。')
    # Distribution across synthetic masks, not across actual flights.
    fig,ax=plt.subplots(figsize=(9,5.5));values=[rates(select(availability,k,.3)) for k in ks]
    box=ax.boxplot(values,tick_labels=['1局','4局','5局'],patch_artist=True,widths=.45,showfliers=False)
    for p in box['boxes']:p.set(facecolor='#dce8f3',edgecolor=blue)
    rng=np.random.default_rng(27)
    for i,v in enumerate(values,1):ax.scatter(i+rng.uniform(-.1,.1,len(v)),v,s=28,color=blue,alpha=.6,zorder=3)
    ax.set(ylim=(-3,104),xlabel='必要な受信局数',ylabel='5秒窓の入力成立率 [%]',title='30%欠測：20パターンのばらつき');ax.grid(axis='y',alpha=.2)
    save(fig,'07_mask_boxplot','欠測パターンごとの箱ひげ図','点は合成欠測20マスク。左右のずれは重なり回避用。実飛行は1つであり、20回の飛行結果や信頼区間ではない。')
    # RSS is shown on a COMMON colour scale, with missing bins masked.
    times=sorted({int(r['elapsed_start_s']) for r in rss});vmin=min(float(r['median_rss']) for r in rss);vmax=max(float(r['median_rss']) for r in rss)
    fig,axes=plt.subplots(2,1,figsize=(12,7.5),sharex=True,layout='constrained')
    # Use regular layout below so every exported figure has the same caption seam.
    fig.set_layout_engine(None)
    cmap=plt.get_cmap('viridis').copy();cmap.set_bad('#eeeeee')
    for ch,ax in enumerate(axes,1):
        grid=np.full((5,len(times)),np.nan)
        for r in rss:
            if int(r['channel'])==ch:grid[int(r['station'][2:])-1,times.index(int(r['elapsed_start_s']))]=float(r['median_rss'])
        im=ax.imshow(np.ma.masked_invalid(grid),origin='upper',extent=[times[0],times[-1]+20,5.5,.5],aspect='auto',vmin=vmin,vmax=vmax,cmap=cmap)
        ax.set_yticks(range(1,6),[f'LW{i}' for i in range(1,6)]);ax.set_title(f'ch{ch}：20秒区間の実測RSS中央値',loc='left')
        for boundary in [.4,.45,.65,.7]:ax.axvline(boundary*summary['source']['duration_s'],color='white',ls='--',lw=.9,alpha=.8)
        fig.colorbar(im,ax=ax,label='保存RSS [dB]',pad=.015)
    axes[-1].set_xlabel('LW1先頭RSSからの経過時間 [s]')
    save(fig,'08_rss_time_heatmap','局×時間のRSSヒートマップ','D1実測。全局・両chで同じ色尺度。灰色は区間データなし。局間の受信ゲイン差を含み、独立校正済み絶対電力や位置の地図ではない。')
    # Waterfall: all four bars are observations, never mixed with window counts.
    row=select(availability,5)[0];total=int(row['reference_rows']);candidate=int(row['candidate_complete']);unique=int(row['unique_complete'])
    drop1=total-candidate;drop2=candidate-unique
    fig,ax=plt.subplots(figsize=(10,5.8))
    ax.bar([0,3],[total,unique],color=blue,width=.62)
    ax.bar(1,drop1,bottom=candidate,color=orange,width=.62);ax.bar(2,drop2,bottom=unique,color='#b5b7c1',width=.62)
    for left,right,level in [(0,1,total),(1,2,candidate),(2,3,unique)]:ax.plot([left+.31,right-.31],[level,level],color='#888',ls='--',lw=1)
    for i,v,y in [(0,str(total),total),(1,f'−{drop1}',candidate+drop1/2),(2,f'−{drop2}',unique+drop2/2),(3,str(unique),unique)]:
        ax.text(i,y+15 if i in [0,3] else y,v,ha='center',va='bottom' if i in [0,3] else 'center',fontsize=14,color=blue if i in [0,3] else '#222',fontweight='bold')
    ax.set_xticks(range(4),['参照観測','時刻・分割条件で除外','元観測の再利用を除外','残る近接候補'])
    ax.set(ylabel='観測候補数 [件]',ylim=(0,total*1.17),title='1,099件から666件へ：何が除かれたか');ax.grid(axis='y',alpha=.15)
    save(fig,'09_candidate_waterfall','候補の絞り込みウォーターフォール','5局・時刻幅200ms・追加遅れ／人工欠測なし。単位は全て観測候補数。残る666件も同一送信と確認されたものではない。')
    # A time line explains the embargo, instead of representing it as missing RF.
    duration=summary['source']['duration_s'];fig,ax=plt.subplots(figsize=(12,3.5))
    segments=[(0,.4,blue,'学習\n40%'),(.4,.45,gray,'隔離\n5%'),(.45,.65,green,'校正\n20%'),(.65,.7,gray,'隔離\n5%'),(.7,1,orange,'評価\n30%')]
    for left,right,color,label in segments:
        ax.broken_barh([(left*duration,(right-left)*duration)],(.2,.6),facecolors=color,edgecolors='white')
        ax.text((left+right)*duration/2,.5,label,ha='center',va='center',fontsize=10,color='#333' if color==gray else 'white',fontweight='bold')
    ax.set(xlim=(0,duration),ylim=(0,1),yticks=[],xlabel='LW1先頭RSSからの経過時間 [s]',title='時間順の分割：同じ観測を学習と評価へ混ぜない')
    for spine in ['top','left','right']:ax.spines[spine].set_visible(False)
    save(fig,'10_split_timeline','学習・校正・評価の時系列図','同じ1飛行の時系列分割。各隔離区間は約46秒。隔離はRF欠測ではなく評価手順で、別飛行への一般化を確認したものではない。')
    (a.out/'catalog.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+'\n')
    (a.out/'missing-heatmap.csv').write_text('receivers,missing0,missing10,missing30,missing50\n'+'\n'.join(str(k)+','+','.join(map(str,v)) for k,v in zip(ks,table))+'\n')
    index=['# Dataset-21：図の一覧','', '**全て入力診断。位置偽装の検出率ではない。新しい実験は実行せず、保存済み集計を別の形で描画した。**','', '| 形 | 読み取ること |','|---|---|']
    for r in catalog:index.append(f'| [{r["title"]}]({r["file"]}.png) | {r["caption"].replace(chr(10), "")} |')
    index+=['','## 元の4図','']
    for name,title in [('01_measured_rss','折れ線：実測RSSの時間変動'),('02_receiver_availability','折れ線：局数と近接候補率'),('03_missingness','折れ線：欠測率と入力成立率'),('04_observation_lag','折れ線：観測時刻差と入力成立率')]:
        relative=os.path.relpath((a.source/'figures'/(name+'.png')).resolve(),a.out.resolve())
        index.append(f'- [{title}]({relative})')
    index+=['','各図はPNGと編集可能なSVGを保存。','', '再現：`.cache/issue77/python/bin/python experiments/week27-data-audit/plot_dataset21_gallery.py --source week27/results/dataset21-eval-20261108-e --out 新しい出力先`']
    (a.out/'README.md').write_text('\n'.join(index)+'\n')
    manifest=dict(source_files={name:hashlib.sha256((a.source/name).read_bytes()).hexdigest() for name in ['summary.json','availability.csv','rss-time-blocks.csv']},
                  code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),new_experiments=0,geometric_detection_executed=False,
                  outputs={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(a.out.iterdir()) if p.is_file()})
    (a.out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(f'Generated {len(catalog)} alternative figures, PNG/SVG; no new detection results.')


if __name__=='__main__':main()
