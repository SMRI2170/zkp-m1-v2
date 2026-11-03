"""Japanese aggregate-only sensitivity/temporal figures."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt
from plot_paired_attacks import font_setup, export

COLORS={10.:'#788e9c',30.:'#37866e',50.:'#c08722',100.:'#c54a3e'}
NAMES={'normal':'正常','position_only':'③ 位置のみ','exact_compensation':'④ 理想補償','bounded_3db':'④ ±3dB','mismatched_n2':'④ 攻撃側n=2'}


def frame(ax,title,xlabel,ylabel='警報率（%）：48分割の平均'):
    ax.set(title=title,xlabel=xlabel,ylabel=ylabel);ax.grid(alpha=.2)


def footer(fig,text):
    fig.subplots_adjust(bottom=.27,top=.88)
    text+='\n地上送信→UAV受信のLoRa実測＋合成攻撃。Remote ID実機の評価ではない。'
    fig.text(.12,.035,text,fontsize=10,color='#555555')


def draw(root):
    font=font_setup();j=json.loads((root/'summary.json').read_text());out=root/'figures';out.mkdir(exist_ok=True)
    baseline=j['aggregates']['power_cap'][0]['mean_baseline_alarm_rate']*100
    # Absolute attacker exponent: same value is applied to every fitted detector model.
    fig,(ax,hist)=plt.subplots(2,1,figsize=(8.8,7.2),gridspec_kw={'height_ratios':[3,1]},sharex=True)
    for delta,color in COLORS.items():
        rows=[r for r in j['aggregates']['absolute_exponent'] if r['shift_m']==delta]
        ax.plot([r['attacker_n'] for r in rows],[r['mean_alarm_rate']*100 for r in rows],lw=2,color=color,label=f'{int(delta)}m外向き')
    ref=next(r for r in j['aggregates']['absolute_exponent'] if r['shift_m']==100 and r['attacker_n']==2.)
    ax.scatter([2.],[ref['mean_alarm_rate']*100],color='black',s=35,zorder=5)
    ax.annotate('n=2：15.51%',(2.,ref['mean_alarm_rate']*100),xytext=(2.7,30),arrowprops={'arrowstyle':'->'},fontsize=11)
    ax.axhline(baseline,color='#555555',ls='--',label='正常4.90%');ax.set_ylim(0,100);ax.legend(fontsize=10)
    frame(ax,'攻撃側が一律のnを使うと、補償誤差が残る','')
    with (root/'n2_explanation-fold.csv').open() as stream:models=[float(r['detector_n']) for r in csv.DictReader(stream)]
    hist.hist(models,bins=np.arange(.5,5.01,.25),color='#345f85',edgecolor='white')
    hist.set(xlabel='上：攻撃側の固定n ／ 下：学習した検出器nの分布',ylabel='モデル数',xlim=(.5,5))
    hist.grid(alpha=.2)
    fig.subplots_adjust(bottom=.20,top=.90,hspace=.13)
    fig.text(.12,.035,'検出器の推定nは真の物理量ではない。共有runを含む48モデル。\n上限なしの合成電力補償。地上送信→UAV受信の代理評価。',fontsize=10,color='#555555')
    export(fig,out,'01_absolute_exponent')
    fig,ax=plt.subplots(figsize=(8.8,5.8))
    for delta,color in COLORS.items():
        rows=[r for r in j['aggregates']['relative_exponent'] if r['shift_m']==delta]
        ax.plot([(r['n_ratio']-1)*100 for r in rows],[r['mean_alarm_rate']*100 for r in rows],lw=2,color=color,label=f'{int(delta)}m外向き')
    ax.axhline(baseline,color='#555555',ls='--',label='正常4.90%');ax.axvline(0,color='#555555',ls=':')
    ax.set(ylim=(0,100),xlim=(-75,75));ax.legend(fontsize=10)
    frame(ax,'検出器nに対するモデル不一致を変える','相対誤差 100 × (n攻撃 / n検出 − 1)（%）')
    footer(fig,'誤差0%は検出器モデル既知の理想条件。物理的な真のnとの差ではない。\n元の実測残差と閾値は保持。送信ごとの合成電力補償は上限なし。')
    export(fig,out,'02_relative_model_error')
    fig,ax=plt.subplots(figsize=(8.8,5.8))
    for delta,color in COLORS.items():
        rows=[r for r in j['aggregates']['power_cap'] if r['shift_m']==delta and r['cap_db'] is not None]
        ax.plot([r['cap_db'] for r in rows],[r['mean_alarm_rate']*100 for r in rows],'o-',lw=2,ms=4,color=color,label=f'{int(delta)}m外向き')
    ax.axhline(baseline,color='#555555',ls='--',label='正常／上限なし：4.90%');ax.set(ylim=(0,100),xlim=(0,30),xticks=[0,1,3,6,10,15,20,30]);ax.legend(fontsize=10)
    frame(ax,'補償可能な電力幅を広げると警報はどう変わるか','相対的な送信電力変更の上限 ±B（dB）')
    footer(fig,'検出器nと距離を知る仮定。0dBは位置変更のみ、±3dBは既往条件。\n受信可否・干渉・飽和の変化は含まない。実EIRPの上限ではない。')
    export(fig,out,'03_power_cap')
    fig,ax=plt.subplots(figsize=(9.4,6.8))
    ratios=j['config']['n_ratio'];caps=j['config']['power_caps_db'];cells=[]
    for cap in caps:
        cells.append([next(r['mean_excess_alarm_pp'] for r in j['aggregates']['joint'] if r['n_ratio']==ratio and r['cap_db']==cap) for ratio in ratios])
    matrix=np.array(cells);limit=max(1.,float(np.max(np.abs(matrix))))
    im=ax.imshow(matrix,origin='lower',aspect='auto',cmap='Reds',vmin=0,vmax=limit)
    ticks=list(range(0,len(ratios),5));ax.set_xticks(ticks);ax.set_xticklabels([f'{(ratios[t]-1)*100:+.0f}' for t in ticks])
    ax.set_yticks(range(len(caps)));ax.set_yticklabels(['上限なし' if c is None else f'±{c:g}' for c in caps])
    frame(ax,'100m外向き：モデル誤差 × 電力上限','検出器nに対する相対誤差（%）','評価した電力上限（dB、段階表示）')
    fig.colorbar(im,ax=ax,label='警報率 − 正常時警報率（ポイント）')
    footer(fig,'白に近いほど正常との警報率差が小さい。安全・危険の二値判定ではない。\n各マスを実際に計算した離散グリッド。未評価条件へ補間していない。')
    export(fig,out,'04_joint_sensitivity')
    with (root/'n2_explanation-fold.csv').open() as stream:rows=list(csv.DictReader(stream))
    fig,ax=plt.subplots(figsize=(8.8,5.8))
    x=[float(r['rms_shift_db']) for r in rows];y=[float(r['alarm_rate'])*100 for r in rows]
    colors=[float(r['detector_n']) for r in rows]
    scatter=ax.scatter(x,y,c=colors,cmap='viridis',s=40,edgecolor='white',lw=.4)
    ax.axhline(baseline,color='#555555',ls='--',label='正常の分割平均4.90%');ax.set_ylim(0,100);ax.legend(fontsize=10)
    frame(ax,'なぜ攻撃側n=2の警報率が15.51%になるのか','補償後に残るモデルずれのRMS（dB）')
    fig.colorbar(scatter,ax=ax,label='検出器が学習したn')
    footer(fig,'各点は100m外向きの1分割。nの違いと距離比で、残るずれが変わる。\n元の残差・閾値にも依存し、nだけから一意に警報率は決まらない。')
    export(fig,out,'05_n2_explanation')
    temporal=j['aggregates']['temporal'];labels=[NAMES[r['variant']] for r in temporal]
    fig,(ax,bx)=plt.subplots(1,2,figsize=(11.5,6.0));positions=np.arange(len(temporal));width=.36
    ax.bar(positions-width/2,[r['mean_packet_alarm_rate']*100 for r in temporal],width,label='パケット単位',color='#345f85')
    ax.bar(positions+width/2,[r['mean_window_median_alarm_rate']*100 for r in temporal],width,label='10秒窓・別閾値',color='#bb7f25')
    ax.set(title='判定単位を分けて評価する',ylabel='警報率（%）：48分割の平均',ylim=(0,100));ax.legend(fontsize=10)
    bars=bx.bar(positions,[r['pooled_packets_per_episode'] for r in temporal],color='#388477')
    for bar,r in zip(bars,temporal):bx.text(bar.get_x()+bar.get_width()/2,bar.get_height()+.5,f"{r['pooled_packets_per_episode']:.1f}",ha='center',fontsize=10)
    bx.set(title='連続警報をまとめると',ylabel='警報区間あたりのパケット数（全分割合計の比）',ylim=(0,36))
    for axis in (ax,bx):axis.set_xticks(positions);axis.set_xticklabels(labels,rotation=35,ha='right',fontsize=10);axis.grid(axis='y',alpha=.2)
    fig.subplots_adjust(bottom=.34,top=.88,wspace=.35)
    fig.text(.12,.035,'10秒窓は正常データから別に校正。パケット率と窓率は母数が異なる。\n区間も窓も独立事象とは仮定しない。2秒超の受信空白で警報区間を分断。\n地上送信→UAV受信のLoRa実測＋合成攻撃。Remote ID実機の評価ではない。',fontsize=10,color='#555555')
    export(fig,out,'06_temporal_units')
    files=[Path(__file__),Path(__file__).with_name('plot_paired_attacks.py')]
    manifest=dict(font=font,plot_code_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
                  outputs={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.iterdir()) if p.suffix in ('.png','.svg')})
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('result',type=Path);draw(p.parse_args().result)
