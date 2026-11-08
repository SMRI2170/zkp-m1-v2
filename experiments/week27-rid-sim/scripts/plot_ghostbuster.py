"""Readable x=spoof displacement, y=alarm fraction; no interpolated claims."""
import argparse
import csv
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager


def read(path):
    with path.open() as f: rows=list(csv.DictReader(f))
    for r in rows:
        for k in ['k','offset_m']:r[k]=int(float(r[k]))
        for k in ['alarm_all_mean','alarm_all_low','alarm_all_high','eligible_mean']:
            r[k]=float(r[k]) if r[k] else float('nan')
    return rows


def subset(rows,**conditions):
    return sorted([r for r in rows if all(str(r[k])==str(v) for k,v in conditions.items())],key=lambda r:r['offset_m'])


def line(ax,rows,label,color):
    if not rows:return
    x=[r['offset_m'] for r in rows]
    ax.plot(x,[100*r['alarm_all_mean'] for r in rows],'o-',label=label,color=color,lw=2,ms=4)
    ax.fill_between(x,[100*r['alarm_all_low'] for r in rows],[100*r['alarm_all_high'] for r in rows],color=color,alpha=.12)


def finish(ax,title):
    ax.set_title(title,fontsize=13,loc='left',fontweight='bold')
    ax.set_xlabel('申告位置の偽装距離 [m]')
    ax.set_ylabel('警報の割合 [%：全評価窓が分母]')
    ax.set_ylim(-2,102);ax.set_yticks([0,20,40,60,80,100])
    ax.axhline(95,color='#999999',ls=':',lw=1)
    ax.text(.99,.94,'95%',transform=ax.transAxes,ha='right',fontsize=9,color='#777777')
    ax.grid(alpha=.2);ax.spines[['top','right']].set_visible(False)
    ax.legend(fontsize=9,loc='best')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--synthetic',type=Path,required=True);p.add_argument('--native',type=Path,required=True);p.add_argument('--counterfactual',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    available={font.name for font in font_manager.fontManager.ttflist}
    font=next((v for v in ['Hiragino Sans','Noto Sans CJK JP','IPAexGothic'] if v in available),'DejaVu Sans')
    plt.rcParams.update({'font.family':font,'font.size':10,'axes.unicode_minus':False,'svg.fonttype':'none'})
    rows=read(a.synthetic/'aggregate.csv');native=read(a.native/'aggregate.csv');control=read(a.counterfactual/'aggregate.csv')
    outputs=[];colors=['#16365d','#1684c0','#dd762c','#773e9a']
    def save(fig,name,caption):
        fig.text(.06,.015,caption,fontsize=9,color='#444444')
        fig.tight_layout(rect=(0,.07,1,.96))
        for ext in ['png','svg']:
            target=a.out/f'{name}.{ext}'
            fig.savefig(target,dpi=180)
            if ext=='svg':target.write_text('\n'.join(line.rstrip() for line in target.read_text().splitlines())+'\n')
        plt.close(fig);outputs.append(dict(file=name,caption=caption))
    fig,ax=plt.subplots(figsize=(9,5.5))
    for k,c in zip([1,4,5,12],colors):
        line(ax,subset(rows,k=k,noise_sd_db='3.5',direction='transverse_rx0',attack='position_only',threshold_policy='q95_normal'),f'{k}局',c)
    finish(ax,'既知電力：受信局数によって何mの偽装から警報が増えるか')
    save(fig,'01_receivers','合成LDPL・SD3.5dB・5パケット/窓。局数と配置は同時に変化。0mは正常時の誤警報。帯は20seedの95%区間。')
    fig,axes=plt.subplots(1,2,figsize=(12,5.5))
    for ax,k in zip(axes,[1,5]):
        for attack,label,c in [('position_only','位置のみ変更',colors[0]),('power_compensation_rx0','位置＋局0向け電力補償',colors[2])]:
            line(ax,subset(rows,k=k,noise_sd_db='3.5',direction='away_rx0',attack=attack,threshold_policy='q95_normal'),label,c)
        curve=subset(control,k=k,attack='honest_at_claimed_position',threshold_policy='q95_normal')
        ax.plot([r['offset_m'] for r in curve],[100*r['alarm_all_mean'] for r in curve],'s--',
                color='#168b74',label='申告地点に本当にいる正常機',lw=1.7,ms=3)
        finish(ax,f'{k}局：局0から遠ざかる位置偽装')
        ax.set_xlabel('元位置からの申告位置のずれ [m]')
    save(fig,'02_power_attack','共通補償±10dB。正常対照は実位置が移動。1局では補償が上限内なら正常対照と観測が同一。警報増加だけで識別成功と言えない。')
    fig,ax=plt.subplots(figsize=(9,5.5))
    for sd,c in zip(['1.0','3.5','6.0'],colors):
        line(ax,subset(rows,k=5,noise_sd_db=sd,direction='transverse_rx0',attack='position_only',threshold_policy='q95_normal'),f'雑音SD {sd} dB',c)
    finish(ax,'5局：雑音が大きいほど、どの程度の偽装を見逃すか')
    save(fig,'03_noise','合成LDPL・既知電力・5パケット/窓。各雑音条件の正常200窓で個別に閾値校正。マルチパスの実測ではない。')
    fig,ax=plt.subplots(figsize=(9,5.5))
    for policy,label,c in [('max_normal','論文型：正常校正の最大誤差',colors[0]),('q95_normal','比較：正常校正の95%点',colors[2])]:
        line(ax,subset(rows,k=5,noise_sd_db='3.5',direction='transverse_rx0',attack='position_only',threshold_policy=policy),label,c)
    finish(ax,'閾値の選び方：誤警報を減らすと、小さな偽装も見逃す')
    save(fig,'04_threshold','同じ合成RSS・同じ推定位置を使用。最大正常誤差を使っても、未知の正常データで誤警報ゼロは保証されない。')
    fig,axes=plt.subplots(1,2,figsize=(12,5.5))
    for ax,k in zip(axes,[4,5]):
        normal=subset(native,k=k,attack='normal',threshold_policy='q95_normal')
        for attack,label,c in zip(['position_only','reference_rx0','schedule_aware','schedule_blind'],['位置のみ','局0向け補償','選択局を知る補償','全局平均を使う補償'],colors):
            curve=normal+subset(native,k=k,attack=attack,threshold_policy='q95_normal')
            line(ax,curve,label,c)
        finish(ax,f'既存INETログへの適用：{k}局')
        ax.set_xticks([0,30,100])
    save(fig,'05_native_replay','保存済みPR5の再解析。20飛行×4非重複窓。0/30/100mのみ評価。FreeSpace＋Dipole、正常のみで伝搬モデルを学習。実測ではない。')
    fig,ax=plt.subplots(figsize=(9,5.5))
    for k,c in zip([1,4,5,12],colors):
        curve=subset(rows,k=k,noise_sd_db='3.5',direction='transverse_rx0',attack='position_only',threshold_policy='q95_normal')
        ax.plot([r['offset_m'] for r in curve],[100*r['eligible_mean'] for r in curve],'o-',color=c,label=f'{k}局')
    finish(ax,'判定できた窓の割合：数値計算の失敗を検出成功に数えない')
    ax.set_ylabel('判定可能な窓の割合 [%]')
    save(fig,'06_eligibility','各パケットで80%以上の組合せが収束し、窓内5パケット全てが成立した場合だけ判定。受信欠落は合成実験では未導入。')
    fig,ax=plt.subplots(figsize=(9,5.5))
    for k,c in zip([1,4,5,12],colors):
        curve=[r for r in subset(rows,k=k,noise_sd_db='3.5',direction='transverse_rx0',attack='position_only',threshold_policy='q95_normal') if r['offset_m']<=300]
        line(ax,curve,f'{k}局',c)
    finish(ax,'0〜300mを拡大：30m・100mの偽装を区別できるか')
    ax.set_xticks([0,30,100,200,300])
    save(fig,'07_close_range','合成LDPL・既知電力。0mの誤警報率に近い警報率では、位置偽装を十分に区別できたとは言えない。')
    from run_ghostbuster import receiver_layout
    fig,axes=plt.subplots(1,3,figsize=(12,4.7))
    for ax,k in zip(axes,[4,5,12]):
        r=receiver_layout(k)
        ax.scatter(r[:,0],r[:,1],s=65,marker='s',color=colors[0],label='地上受信局')
        for i,p in enumerate(r):ax.annotate(f'{i}',p[:2],xytext=(5,5),textcoords='offset points')
        ax.fill([68,432,432,68],[68,68,432,432],alpha=.09,color=colors[1],label='UAVの水平位置範囲')
        ax.set_title(f'{k}局の宣言配置');ax.set_xlabel('東西 [m]');ax.set_ylabel('南北 [m]')
        ax.set_aspect('equal');ax.set_xlim(-40,540);ax.set_ylim(-40,540);ax.grid(alpha=.2)
    axes[0].legend(fontsize=8)
    save(fig,'08_layouts','合成ローカル座標。開始位置80〜420m、高度40〜100m。1秒間隔×5パケット（先頭〜末尾4秒）。5局目のみ高さ8m、他は2m。')
    (a.out/'figures.json').write_text(json.dumps(dict(font=font,figures=outputs),ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':main()
