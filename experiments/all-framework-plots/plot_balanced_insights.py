"""Tradeoff scatter and labelled metric heatmap from exported aggregate metrics."""
import argparse
import hashlib
import json
from pathlib import Path


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    rows = json.loads(a.data.read_text())
    if not rows or any(r['n'] != 21 for r in rows):
        raise SystemExit('Expected complete n=21 aggregate rows')
    a.out.mkdir(parents=True, exist_ok=False)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.ticker import FuncFormatter
    plt.rcParams.update({'font.family': 'Hiragino Sans', 'font.size': 12})
    labels = [r['framework'].replace('circom-', 'Circom + ').replace('gnark-', 'gnark / ')
              .replace('halo2-', 'Halo2 / ') for r in rows]
    note = ('各n=21。同一Pi・CPU 25%・1スレッド。CircomはWitness生成・CLI起動・共通native検証を含む。\n'
            '他構成と測定範囲の細部が異なります。メモリは全実行の最大値。証明サイズは保存形式差を含みます。')
    fig, ax = plt.subplots(figsize=(12, 8))
    offsets = [(10,-20), (10,12), (10,8), (-95,-25), (-105,15), (25,20),
               (30,-28), (-95,15), (-150,-28)]
    for r, label, offset in zip(rows, labels, offsets):
        x, y = r['flow_mean_ms']/1000, r['memory_peak_MiB']
        color = '#dc792f' if r['framework'].startswith('circom-') else '#3274a1'
        ax.scatter(x, y, s=90, color=color, edgecolor='white', zorder=3)
        ax.annotate(label, (x,y), xytext=offset, textcoords='offset points', fontsize=11,
                    arrowprops={'arrowstyle': '-', 'color': '#8895a1', 'lw': .8})
    ax.set_xscale('log'); ax.set_yscale('log')
    ax.set_xlim(.12, 28); ax.set_ylim(6, 150)
    ax.set_xticks([.2,.5,1,2,5,10,20]); ax.set_yticks([8,16,32,64,128])
    for axis in [ax.xaxis, ax.yaxis]: axis.set_major_formatter(FuncFormatter(lambda v,_: f'{v:g}'))
    ax.set_xlabel('平均処理時間（秒・対数軸）'); ax.set_ylabel('最大メモリ（MiB・対数軸）')
    ax.grid(alpha=.2, which='major')
    ax.set_title('速度とメモリの関係', loc='left', fontsize=22, weight='bold', pad=35)
    ax.text(0, 1.025, '左下ほど短時間・省メモリ  ｜  青：native構成　オレンジ：Circom構成',
            transform=ax.transAxes, fontsize=12)
    fig.text(.12,.025,note,fontsize=10,linespacing=1.6)
    fig.subplots_adjust(left=.12,right=.96,top=.83,bottom=.18)
    for ext in ['png','svg']: fig.savefig(a.out / ('time-memory.'+ext), dpi=180)
    plt.close(fig)

    values = np.array([[r['flow_mean_ms']/1000, r['memory_peak_MiB'], r['proof_mean_bytes']] for r in rows])
    logged = np.log(values)
    span = logged.max(axis=0)-logged.min(axis=0)
    normalized = np.divide(logged-logged.min(axis=0), span, out=np.zeros_like(logged), where=span!=0)
    fig, ax = plt.subplots(figsize=(11, 9))
    ax.imshow(normalized, cmap='YlOrRd', vmin=0, vmax=1, aspect='auto')
    for i in range(len(rows)):
        for j in range(3):
            value = values[i,j]
            text = f'{value:.3f} 秒' if j==0 else f'{value:.1f} MiB' if j==1 else f'{value:,.0f} B'
            ax.text(j,i,text,ha='center',va='center',fontsize=14,
                    color='white' if normalized[i,j]>.7 else '#222222',weight='bold')
    ax.set_yticks(range(len(rows)), labels)
    ax.set_xticks(range(3), ['平均処理時間','最大メモリ','証明サイズ'])
    ax.xaxis.tick_top(); ax.tick_params(length=0,pad=12)
    for spine in ax.spines.values(): spine.set_visible(False)
    ax.set_yticks(np.arange(-.5,len(rows),1),minor=True)
    ax.set_xticks(np.arange(-.5,3,1),minor=True)
    ax.grid(which='minor',color='white',linewidth=4); ax.tick_params(which='minor',length=0)
    fig.suptitle('数値と色で見る9構成',x=.30,y=.985,ha='left',fontsize=22,weight='bold')
    fig.text(.30,.89,'薄い黄：値が小さい　濃い赤：値が大きい\n色は各列内で対数正規化。列をまたぐ色の比率や総合点は表しません。',fontsize=11)
    fig.text(.30,.025,note,fontsize=9,linespacing=1.6)
    fig.subplots_adjust(left=.30,right=.97,top=.82,bottom=.15)
    for ext in ['png','svg']: fig.savefig(a.out / ('metric-heatmap.'+ext),dpi=180)
    plt.close(fig)
    (a.out/'sources.json').write_text(json.dumps({'input':str(a.data),
        'sha256':hashlib.sha256(a.data.read_bytes()).hexdigest(),
        'measurements_rerun':False},indent=2)+'\n')


if __name__ == '__main__':
    main()
