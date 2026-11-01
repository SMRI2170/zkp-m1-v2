"""Scientific plots of saved M0/M1/M2 aggregates; no invented measurements."""
import argparse
import hashlib
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from directional_observations import pattern


def main():
    parser=argparse.ArgumentParser();parser.add_argument('result',type=Path);args=parser.parse_args()
    root=args.result;s=json.loads((root/'summary.json').read_text());rows=s['metrics']
    plt.rcParams.update({'font.family':['Hiragino Sans','DejaVu Sans'],'font.size':11,
                         'axes.spines.top':False,'axes.spines.right':False,'axes.unicode_minus':False})
    blue,red,green,gray='#2F64A1','#C73E3E','#00867C','#818C9A';figures=[]
    def get(**kw):
        default=dict(study='main',noise_sd_db=2,antennas=4,power_mode='joint_unbounded',scenario='ideal',distance_m=0,gap_s=0)
        default.update(kw)
        matched=[r for r in rows if all(r.get(k)==v for k,v in default.items())]
        if len(matched)!=1: raise ValueError((default,len(matched)))
        return matched[0]
    def vals(data,metric='alarm_conditional'):
        y=np.array([r[metric]*100 for r in data])
        error=np.array([[100*r[metric+'_lo'] for r in data],[100*r[metric+'_hi'] for r in data]])
        return y,np.maximum(np.array([y-error[0],error[1]-y]),0)
    def save(fig,name,caption):
        fig.text(.5,.018,caption,ha='center',fontsize=9,color='#444444')
        fig.tight_layout(rect=(0,.08,1,.95))
        for ext in ('png','svg'): fig.savefig(root/(name+'.'+ext),dpi=180)
        plt.close(fig);figures.append(dict(name=name,caption=caption))
    fig=plt.figure(figsize=(7.8,5.5));ax=fig.add_subplot(111,projection='polar');theta=np.linspace(-np.pi,np.pi,361)
    for i in range(4): ax.plot(theta,np.maximum(pattern(theta,4)[:,i]+12,0),label=f'アンテナ{i+1}')
    ax.set_yticks([0,6,12],['−12 dB','−6 dB','0 dB']);ax.set_title('M1：仮定した4方向の受信利得',pad=24)
    ax.legend(loc='upper left',bbox_to_anchor=(1.05,1));save(fig,'01-antenna-model','解析式 6(cos(θ−φ)−1) dB。方位のみ、仰角情報なし。実測アンテナパターンではない。')
    fig,ax=plt.subplots(figsize=(9,5));x=np.arange(3)
    for j,(case,label,color) in enumerate([('normal','正常',gray),('outward100','同じ方向へ100m',blue),('tangential100','横方向へ100m',red)]):
        a=[get(model=m,case=case) for m in ('M0_stat','M1','M2')];y,e=vals(a)
        ax.bar(x+(j-1)*.24,y,.24,yerr=e,label=label,color=color,capsize=3)
    ax.set(xticks=x,xticklabels=['M0-stat\n単独RSSI・正常分布に依存','M1\n1局・4方向同時受信','M2\n5局・同一送信'],ylabel='判定可能な送信中の警報率（%）',ylim=(0,100),title='位置と電力の同時攻撃：観測方式による違い');ax.legend(fontsize=10)
    save(fig,'02-model-comparison','全受信・雑音SD2dB、20 seed。棒＝平均、線＝seed単位95% bootstrap区間。M0-freeは全保留。')
    fig,axes=plt.subplots(1,2,figsize=(12,4.8),sharey=True)
    for ax,direction,title in zip(axes,['outward','tangential'],['同じ方向へ遠ざける偽装','横方向の偽装']):
        matrix=np.array([[get(study='distance',model='M1',case=f'{direction}{delta}',distance_m=d)['alarm_conditional']*100
                          for delta in (10,30,50,100)] for d in (30,100,300)])
        image=ax.imshow(matrix,vmin=0,vmax=100,cmap='Blues',aspect='auto')
        labels=[f'{d}m\n正常 {100*get(study="distance",model="M1",case="normal",distance_m=d)["alarm_conditional"]:.1f}%' for d in (30,100,300)]
        ax.set(xticks=range(4),xticklabels=[10,30,50,100],yticks=range(3),yticklabels=labels,xlabel='申告の水平変位（m）',title=title)
        for i in range(3):
            for j in range(4):ax.text(j,i,f'{matrix[i,j]:.1f}%',ha='center',va='center',color='white' if matrix[i,j]>50 else '#222222')
    axes[0].set_ylabel('受信局からの真の水平距離');fig.colorbar(image,ax=axes.ravel().tolist(),label='警報率（%）',fraction=.025,pad=.03)
    fig.suptitle('M1：距離と偽装方向によって検知しやすさが変わる')
    # Colorbar requires explicit margins rather than tight_layout.
    fig.text(.5,.018,'同じ校正閾値を使用。距離帯別の正常誤警報率も併記。SD2dB・4方向・全受信の合成20 seed。',ha='center',fontsize=9)
    fig.subplots_adjust(left=.12,right=.85,bottom=.19,top=.80,wspace=.3)
    for ext in ('png','svg'):fig.savefig(root/('03-distance-direction.'+ext),dpi=180)
    plt.close(fig);figures.append(dict(name='03-distance-direction',caption='Fixed global calibration; per-distance normal FPR shown.'))
    fig,axes=plt.subplots(1,2,figsize=(11,4.8),sharey=True)
    for ax,case,title in zip(axes,['tangential30','tangential100'],['横方向30m偽装','横方向100m偽装']):
        for count,color in zip((2,4,6),(gray,blue,red)):
            a=[get(model='M1',case=case,antennas=count,noise_sd_db=sd) for sd in (1,2,4,6)];y,e=vals(a)
            ax.errorbar([1,2,4,6],y,yerr=e,marker='o',capsize=2,color=color,label=f'{count}方向：偽装')
            a=[get(model='M1',case='normal',antennas=count,noise_sd_db=sd) for sd in (1,2,4,6)]
            ax.plot([1,2,4,6],[100*r['alarm_conditional'] for r in a],color=color,linestyle=':',alpha=.7)
        ax.set(title=title,xlabel='独立RSSI雑音 SD（dB）',xticks=[1,2,4,6],ylim=(0,100));ax.legend(fontsize=9)
    axes[0].set_ylabel('警報率（%）');save(fig,'04-noise-antennas','点線＝各構成の正常誤警報率。方向数増加には同時受信チェーン増加が必要。独立雑音の合成条件。')
    stress=['ideal','gain_drift2','yaw5','nlos','rf_missing','quantization','n_mismatch','switched_packets']
    names=['基準','利得ずれ\nSD2dB','方位ずれ\nSD5°','反射方向\n＋遮蔽','受信感度\n＋欠落','1dB\n量子化','伝搬指数\n＋0.3','別パケット\nを切替']
    fig,axes=plt.subplots(2,1,figsize=(12,7),sharex=True,gridspec_kw={'height_ratios':[2,1]});x=np.arange(len(stress))
    for j,(case,label,color) in enumerate([('normal','正常',gray),('tangential100','横方向100m',red)]):
        a=[get(study='stress',model='M1',case=case,scenario=sc) for sc in stress];y,e=vals(a)
        axes[0].bar(x+(j-.5)*.32,y,.32,yerr=e,color=color,label=label,capsize=2)
        axes[1].bar(x+(j-.5)*.32,[100*r['abstain_rate'] for r in a],.32,color=color)
    axes[0].set(ylabel='判定可能中の警報率（%）',ylim=(0,100),title='M1：モデルのずれで誤警報・保留が増える');axes[0].legend()
    axes[1].set(xticks=x,xticklabels=names,ylabel='全送信中の保留（%）',ylim=(0,100))
    save(fig,'05-robustness','基本SD2dB・4方向。受信/量子化は校正にも適用。その他は校正後の変化。各要因の単独ストレスで、実環境再現ではない。')
    fig,axes=plt.subplots(1,2,figsize=(11,4.8),sharey=True)
    for ax,case,title in zip(axes,['normal','tangential100'],['正常時の誤警報率','横方向100m偽装の警報率']):
        for scenario,label,color in [('ideal','校正が安定',blue),('async_drift','経過時間に応じ利得がずれる',red)]:
            a=[get(study='async',model='M1',case=case,scenario=scenario,gap_s=gap) for gap in (0,10,3600,86400)];y,e=vals(a)
            ax.errorbar(range(4),y,yerr=e,marker='o',capsize=3,color=color,label=label)
        ax.set(xticks=range(4),xticklabels=['0秒','10秒','1時間','1日'],xlabel='局所観測間の最大時刻差',ylim=(0,100),title=title);ax.legend(fontsize=9)
    axes[0].set_ylabel('警報率（%）');save(fig,'06-asynchronous-local-check','各観測は自身の時刻の申告と比較。別時刻の方向を交差させない。ドリフト0.5dB/√時間は仮定値。')
    if s['empirical_sources']:
        fig,axes=plt.subplots(1,2,figsize=(11,4.8),sharey=True);x=np.arange(3)
        for parity,ax in enumerate(axes):
            for j,(case,label,color) in enumerate([('normal','正常',gray),('tangential100','横方向100m',red)]):
                a=[get(study=f'empirical_parity{parity}',noise_sd_db=0,scenario='empirical_indoor',model=m,case=case) for m in ('M0_stat','M1','M2')];y,e=vals(a)
                ax.bar(x+(j-.5)*.32,y,.32,yerr=e,color=color,label=label,capsize=3)
            ax.set(xticks=x,xticklabels=['M0-stat','M1','M2'],ylim=(0,100),title=f'校正：セクタ番号の剰余{parity}／評価：反対側');ax.legend()
        axes[0].set_ylabel('警報率（%）');save(fig,'07-indoor-empirical-stress','固定屋内BLEの残差を独立に再標本化。実UAV・複数アンテナ間相関・RID検知性能の検証ではない。')
    fig,ax=plt.subplots(figsize=(9,5));x=np.arange(3)
    for j,(case,label,color) in enumerate([('normal','正常',gray),('outward100','基準局から外向き100m',blue),('tangential100','基準局に対し横方向100m',red)]):
        a=[get(study='layout',model='M2',case=case,scenario=sc) for sc in ('ideal','layout_line','layout_cluster')];y,e=vals(a)
        ax.bar(x+(j-1)*.24,y,.24,yerr=e,color=color,label=label,capsize=3)
    ax.set(xticks=x,xticklabels=['既存の分散配置','直線上・全幅240m','10m四方に集中'],ylabel='警報率（%）',ylim=(0,100),title='M2：同じ5局でも配置によって結果が変わる');ax.legend(fontsize=10)
    save(fig,'08-m2-layout','同じ軌跡・申告・共通電力・雑音、全5局受信。配置ごとに正常校正。配置と開口の複合比較。')
    fig,ax=plt.subplots(figsize=(8,5))
    for direction,label,color in [('outward','遠ざける',blue),('inward','近づける',green),('tangential','横へずらす',red)]:
        a=[get(model='M1',case=f'{direction}{shift}') for shift in (10,30,50,100)];y,e=vals(a)
        ax.errorbar([10,30,50,100],y,yerr=e,marker='o',capsize=3,label=label,color=color)
    normal=get(model='M1',case='normal')['alarm_conditional']*100
    ax.axhline(normal,color=gray,linestyle='--',label=f'正常 {normal:.2f}%')
    ax.set(xlabel='申告の水平変位（m）',ylabel='警報率（%）',ylim=(0,100),title='M1：変位の大きさだけでは検知性能を説明できない');ax.legend()
    save(fig,'09-displacement-direction','SD2dB・4方向・電力同時補償。内向きで受信局を通り越すと方向が反転する。水平真距離は約17～318m。')
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir() if p.suffix in ('.png','.svg')}
    (root/'figures.json').write_text(json.dumps(dict(figures=figures,sha256=hashes,
        source_summary_sha256=hashlib.sha256((root/'summary.json').read_bytes()).hexdigest(),
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()),ensure_ascii=False,indent=2)+'\n')
    print(f'Saved {len(figures)} PNG/SVG pairs')


if __name__=='__main__': main()
