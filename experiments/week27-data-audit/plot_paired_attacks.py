"""Aggregate-only Japanese figures. No actual positions or measured packet rows."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt,font_manager

COLORS={'normal':'#555555','position_only':'#cc493d','exact_compensation':'#29836e','bounded_3db':'#c18115','mismatched_n2':'#345fa8'}
LABELS={'normal':'正常（誤警報率）','position_only':'③ 位置申告だけ変更','exact_compensation':'④ 理想補償：検出器モデル既知',
        'bounded_3db':'④ 補償を ±3 dB に制限','mismatched_n2':'④ 攻撃側の伝搬指数を2と仮定'}
DIRS={'outward':'遠ざかる方向','inward':'近づく方向','tangential':'横方向'}


def font_setup():
    names={f.name for f in font_manager.fontManager.ttflist}
    available=next((s for s in ['Hiragino Sans','Noto Sans CJK JP','Yu Gothic','Hiragino Kaku Gothic ProN'] if s in names),None)
    if not available:raise RuntimeError('Japanese font required: install Noto Sans CJK JP')
    plt.rcParams.update({'font.family':available,'font.size':12,'axes.unicode_minus':False})
    return available


def export(fig,out,name):
    fig.savefig(out/(name+'.png'),dpi=170,bbox_inches='tight')
    svg=out/(name+'.svg');fig.savefig(svg,bbox_inches='tight');plt.close(fig)
    svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines())+'\n')


def draw(report,out):
    font=font_setup();out.mkdir(parents=True,exist_ok=True)
    for number,(direction,title) in enumerate(DIRS.items(),1):
        fig,ax=plt.subplots(figsize=(8.4,5.7))
        for variant,color in COLORS.items():
            rows=[r for r in report['aggregate'] if r['direction']==direction and r['variant']==variant]
            ax.plot([r['claim_horizontal_shift_m'] for r in rows],[r['mean_alarm_rate']*100 for r in rows],
                    label=LABELS[variant],color=color,lw=2.3,ls='--' if variant=='normal' else '-',
                    marker='s' if variant=='exact_compensation' else 'o',ms=5)
        ax.set(title=f'申告位置を{title}へずらすとどうなるか',xlabel='水平方向の申告変更量（m）',ylabel='警報率（%）：評価可能な分割の平均',
               ylim=(0,100),xticks=report['config']['horizontal_shift_m'])
        ax.grid(alpha=.22);ax.legend(fontsize=10,loc='upper left')
        fig.subplots_adjust(bottom=.24,top=.88)
        footer='正常と理想補償は重なる。受信済みの同じ標本で比較。\n地上送信→UAV受信の実測＋合成攻撃。Remote ID実機の検出率ではない。'
        if direction=='inward':footer+='\n100mでは30/48分割、対象標本は平均33.5%。送信機を通り越す申告は保留。'
        fig.text(.12,.035,footer,fontsize=10,color='#555555')
        export(fig,out,f'{number:02d}_alarm_{direction}')
    fig,ax=plt.subplots(figsize=(8.4,5.7));distribution=report['normalized_score_distribution']
    x=np.array(distribution['edges'][1:])
    for variant,color in COLORS.items():
        y=distribution['by_variant'][variant]['mean_fold_cdf']
        ax.plot(x,y,color=color,label=('正常' if variant=='normal' else LABELS[variant]),lw=2.2,ls='--' if variant=='normal' else '-',
                marker='s' if variant=='exact_compensation' else None,markevery=12,ms=4)
    ax.axvline(1,color='#222222',ls=':',lw=1.7)
    ax.set(title='100m外向き：正常と攻撃の異常スコア分布',xlabel='異常スコア ÷ 各分割の正常校正閾値',ylabel='この値以下となる割合（48分割の平均）',
           xlim=(0,4),ylim=(0,1.02))
    ax.text(1.05,.12,'1を超えると警報',fontsize=11)
    ax.grid(alpha=.22);ax.legend(fontsize=10,loc='lower right')
    fig.subplots_adjust(bottom=.22,top=.88)
    fig.text(.12,.045,'理想補償の分布は正常と重なる。位置変更だけではスコアが大きくなる。\nモデル既知・送信ごとの電力操作を仮定した反例。新しい実攻撃の測定ではない。',fontsize=10,color='#555555')
    export(fig,out,'04_score_distribution')
    fig,ax=plt.subplots(figsize=(8.4,5.7))
    for direction,color in zip(DIRS,['#345fa8','#c18115','#29836e']):
        rows=[r for r in report['aggregate'] if r['direction']==direction and r['variant']=='exact_compensation']
        ax.plot([r['claim_horizontal_shift_m'] for r in rows],[r['mean_required_power_beyond_3db_fraction']*100 for r in rows],'o-',label=DIRS[direction],color=color,lw=2)
    ax.set(title='完全に補償するために ±3 dB を超える割合',xlabel='水平方向の申告変更量（m）',ylabel='理想補償量が ±3 dB を超える標本（%）',
           ylim=(0,100),xticks=report['config']['horizontal_shift_m'])
    ax.grid(alpha=.22);ax.legend()
    fig.subplots_adjust(bottom=.21,top=.88)
    fig.text(.12,.045,'必要補償量はモデルから計算した合成値。実送信電力の記録ではない。\n受信可否・干渉・受信機飽和の変化は評価していない。',fontsize=10,color='#555555')
    export(fig,out,'05_required_compensation')
    # Entirely illustrative geometry. Never plot raw truth/receiver coordinates into Git.
    fig,ax=plt.subplots(figsize=(8.4,4.8))
    ax.scatter([0],[0],s=100,color='#555555');ax.text(0,-9,'地上の固定送信機',ha='center',fontsize=12)
    ax.scatter([60],[30],s=100,color='#222222');ax.text(60,35,'実際のUAV受信位置',ha='center')
    ax.scatter([110],[30],s=100,color='#345fa8');ax.text(110,35,'変更後の申告位置',ha='center')
    ax.plot([0,60],[0,30],color='#222222',lw=2,label='実測RSSIに対応する距離 d')
    ax.plot([0,110],[0,30],color='#345fa8',ls='--',lw=2,label='申告から計算する距離 d′')
    ax.annotate('',xy=(110,30),xytext=(60,30),arrowprops=dict(arrowstyle='->',color='#cc493d',lw=2))
    ax.text(85,22,'水平に +50 m',ha='center',color='#cc493d')
    ax.set(xlim=(-15,140),ylim=(-15,50),xlabel='局所的な水平方向（m）',ylabel='高さの近似値（m）',title='③は申告だけ変更、④は合成電力補償も追加')
    ax.legend(loc='upper left',fontsize=10);ax.grid(alpha=.2)
    fig.subplots_adjust(bottom=.25,top=.88)
    fig.text(.12,.035,'模式図：座標は説明用で実測位置ではない。\n③ 元のRSSIを保持　④ 元のRSSIに ΔP を加えた別系列を生成\nこのデータではドローンは受信側。ドローン送信型RIDの実証ではない。',fontsize=10,color='#555555')
    export(fig,out,'00_geometry_explanation')
    provenance={'font':font,'plot_code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                'scope':'Aggregate results and synthetic explanatory geometry only; no raw positions',
                'outputs':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.iterdir()) if p.suffix in ('.png','.svg')}}
    (out/'manifest.json').write_text(json.dumps(provenance,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('result',type=Path);a=p.parse_args()
    draw(json.loads((a.result/'summary.json').read_text()),a.result/'figures')
