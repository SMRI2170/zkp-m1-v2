# coding: utf-8
"""Scientific static figures with explicit measurement/cohort boundaries."""
import argparse,json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Patch
from matplotlib.lines import Line2D
from matplotlib.ticker import LogLocator,FuncFormatter
from collect import collect

BLUE='#2563eb';ORANGE='#d97706';IVC='#9a6700';GRAY='#64748b'

def configure():
    available={f.name for f in font_manager.fontManager.ttflist}
    font=next((f for f in ['Hiragino Sans','Noto Sans CJK JP','Noto Sans CJK SC','IPAexGothic'] if f in available),None)
    if not font:raise RuntimeError('Japanese font required: install Noto Sans CJK JP before plotting')
    plt.rcParams.update({'font.family':font,'font.size':10,'axes.unicode_minus':False,'svg.fonttype':'path',
                         'axes.spines.top':False,'axes.spines.right':False,'figure.facecolor':'white'})
    return font

def save(fig,out):
    out.parent.mkdir(parents=True,exist_ok=True)
    fig.savefig(out.with_suffix('.png'),dpi=180,bbox_inches='tight',facecolor='white')
    fig.savefig(out.with_suffix('.svg'),bbox_inches='tight',facecolor='white')
    svg=out.with_suffix('.svg');svg.write_text('\n'.join(s.rstrip() for s in svg.read_text().splitlines())+'\n')
    plt.close(fig)

def label(r):
    if r['workload']=='signed_observations':
        name=f"{r['observation_count']}観測  {r['run_id']}"
    else:name=r['framework']
    if r['status']=='ivc_only':name+=' [IVC]'
    if r['status']=='partial':name+=' [途中／中断]'
    if r['status']=='stopped':name+=' '+r['run_id'].split('-')[-1]+' [保護停止]'
    return name+f"  n={r['samples']}"

def bytes_label(v):return f'{v:,.0f} B' if v<1024 else f'{v/1024:,.1f} KiB'

def numeric(rows,title,footer,out,signed=False,mac=False):
    cols=4 if signed else 3
    fig,axes=plt.subplots(1,cols,figsize=(20 if signed else 17,max(6.3,0.61*len(rows)+2.7)),sharey=True)
    values=[('setup_ms','setup（秒、対数）')]*signed+[('flow_mean_ms','平均フロー（秒、対数）'),('memory','メモリ（MiB）'),('proof_bytes','serializedサイズ（byte、対数）')]
    for ax,(key,heading) in zip(axes,values):
        ax.set_title(('Macメモリ（MiB）\nRSS／footprintを別記' if mac else 'unitメモリ（MiB）\n色=kernel最大／灰=時間平均') if key=='memory' else heading,pad=13,fontsize=12)
        for i,r in enumerate(rows):
            color=IVC if r['ivc_only'] else ORANGE if r['status'] in ['partial','stopped'] else BLUE
            hatch='//' if r['status'] in ['partial','stopped'] else None
            if key=='memory':
                mean=r['memory_mean_bytes'];peak=r['kernel_peak_bytes'];obs=r['observed_peak_bytes']
                if mean is not None:ax.barh(i+.15,mean/2**20,height=.25,color='#94a3b8');ax.annotate(f'{mean/2**20:.1f}',(mean/2**20,i+.15),xytext=(4,0),textcoords='offset points',va='center',fontsize=8)
                if peak is not None:ax.barh(i-.15,peak/2**20,height=.25,color=color,hatch=hatch);ax.annotate(f'{peak/2**20:.1f}',(peak/2**20,i-.15),xytext=(4,0),textcoords='offset points',va='center',fontsize=8)
                if obs is not None:
                    shape='D' if r['observed_memory_metric']=='peak footprint' else '^' if 'cgroup' in r['observed_memory_metric'] else 'o'
                    ax.scatter(obs/2**20,i,marker=shape,color=color,s=45,zorder=5)
                    tag='footprint' if shape=='D' else 'sampled' if shape=='^' else 'RSS'
                    ax.annotate(f'{obs/2**20:.1f} ({tag})',(obs/2**20,i),xytext=(6,0),textcoords='offset points',va='center',fontsize=8)
                if mean is None and peak is None and obs is None:ax.text(.05,i,'未計測',transform=ax.get_yaxis_transform(),va='center',color=GRAY)
            else:
                value=r[key]
                if value is None:
                    text='最終ZKなし／未計測' if r['ivc_only'] and key=='proof_bytes' else '未完了／未計測'
                    ax.text(.04,i,text,transform=ax.get_yaxis_transform(),va='center',fontsize=9,color=GRAY)
                    continue
                v=value/1000 if key.endswith('_ms') else value
                ax.barh(i,v,height=.52,color=color,hatch=hatch,alpha=.9)
                text=f'{v:.3g}' if key.endswith('_ms') else bytes_label(v)
                if key=='proof_bytes':
                    if r['proof_scope']=='proof + public 16B':text+=' *公開入力込'
                    elif r['proof_scope']=='JSON proof only':text+=' *JSON'
                    elif r['proof_scope']=='Composite receipt':text+=' *receipt'
                ax.annotate(text,(v,i),xytext=(5,0),textcoords='offset points',va='center',fontsize=8)
        ax.set_ylim(len(rows)-.5,-.5);ax.set_yticks(range(len(rows)));ax.grid(axis='x',alpha=.18);ax.set_axisbelow(True)
        if key=='memory':
            candidates=[r[k]/2**20 for r in rows for k in ['memory_mean_bytes','kernel_peak_bytes','observed_peak_bytes'] if r[k] is not None]
            ax.set_xlim(0,max(candidates)*1.65 if candidates else 1)
        else:
            data=[r[key]/1000 if key.endswith('_ms') else r[key] for r in rows if r[key] is not None and r[key]>0]
            ax.set_xscale('log');ax.set_xlim(min(data)/2,max(data)*18)
            ax.xaxis.set_major_locator(LogLocator(base=10,numticks=5));ax.xaxis.set_major_formatter(FuncFormatter(lambda v,_:f'{v:g}'))
    axes[0].set_yticklabels([label(r) for r in rows],fontsize=9)
    fig.suptitle(title,fontsize=15,y=.99)
    legend=[Patch(facecolor=BLUE,label='完走した記録'),Patch(facecolor=ORANGE,hatch='//',label='途中成功／保護停止'),Patch(facecolor=IVC,label='IVCのみ')]
    if not mac:legend+=[Patch(facecolor='#94a3b8',label='unit時間加重平均'),Line2D([],[],color='black',marker='^',linestyle='',label='sampling最大のみ（kernel peak不明）')]
    else:legend+=[Line2D([],[],color='black',marker='o',linestyle='',label='sampled process-tree RSS'),Line2D([],[],color='black',marker='D',linestyle='',label='peak footprint（別指標）')]
    fig.legend(handles=legend,loc='lower center',bbox_to_anchor=(.53,.13 if len(rows)<8 else .10),ncol=3,fontsize=8.5,frameon=False)
    fig.text(.51,.012,footer,ha='center',va='bottom',fontsize=8.5,linespacing=1.6)
    fig.subplots_adjust(left=.24,right=.985,top=.79 if len(rows)<8 else .86,bottom=.27 if len(rows)<8 else .19,wspace=.30)
    save(fig,out)

STATE={
 'verified':('#d1fae5','生成・検証済'), 'ivc_only':('#fef3c7','IVC更新・検証のみ'),
 'partial':('#ffedd5','2件成功・全体は中断'), 'not_run':('#e2e8f0','未実施'),
 'not_summarized':('#f1f5f9','今回の集計対象外'), 'stopped':('#fee2e2','保護停止・proof未検証')}

def status(states,out):
    fig,ax=plt.subplots(figsize=(13,11));columns=['Pi：距離回路','Mac：距離回路','Pi：署名付き観測']
    for i,r in enumerate(states):
        for j,key in enumerate(['pi_distance','mac_distance','pi_signed']):
            color,text=STATE[r[key]]
            if key=='pi_signed' and r[key]=='verified':text='1／2／4観測で成功'
            ax.add_patch(plt.Rectangle((j-.48,i-.43),.96,.86,facecolor=color,edgecolor='white'))
            ax.text(j,i,text,ha='center',va='center',fontsize=9)
    ax.set_xlim(-.5,2.5);ax.set_ylim(len(states)-.5,-1.2);ax.set_xticks(range(3));ax.set_xticklabels(columns,fontsize=12);ax.xaxis.tick_top()
    ax.set_yticks(range(len(states)));ax.set_yticklabels([x['framework'] for x in states],fontsize=10)
    ax.tick_params(length=0)
    for spine in ax.spines.values():spine.set_visible(False)
    fig.suptitle('Week24：全18構成の到達状況',fontsize=18,y=.97)
    fig.text(.52,.025,'「今回の集計対象外」は失敗・非対応を意味しない。成功は各記録の範囲に限定。\nNova／HyperNovaは最終公開用ZK未完成。Jolt等の署名付きproofは未実施。\nGo→Rustのnative互換性40件はZKPではないため、成功欄へ加算しない。',ha='center',fontsize=10,linespacing=1.7)
    fig.subplots_adjust(left=.25,right=.98,top=.90,bottom=.12)
    save(fig,out)

def main():
    p=argparse.ArgumentParser();p.add_argument('--data',type=Path,default=Path('week24/data/all-frameworks'));p.add_argument('--out',type=Path,default=Path('week24/plots/all-frameworks'));a=p.parse_args()
    font=configure();records,states=collect(a.data);a.out.mkdir(parents=True,exist_ok=True)
    status(states,a.out/'00_status')
    numeric([r for r in records if r['cohort']=='pi_affinity1'],'Pi・距離回路：CPU quota設定なし、1 CPU affinity（12構成）',
            '各方式の記録済み平均。異なる入力7件、gnarkはwarmupを除く20件。IVCは順序付きstep。\n時間はsetup除外、メモリはsetup・負例を含むunit全体。証明形式・安全性・statementが異なり、普遍的な順位ではない。',a.out/'01_pi_distance_affinity1')
    numeric([r for r in records if r['cohort']=='pi_quota25'],'Pi・距離回路：CPUQuota 25%（途中成功も明示）',
            'Joltはquick 1件。Halo2 KZGは独立r改変テストの別run。Plonky2は成功2件のみの平均で全7件は未完了。\nPlonky2のメモリはpartial sampling最大、最終kernel peakは不明。証明サイズはPlonky2だけ公開入力16B込み。',a.out/'02_pi_distance_quota25')
    numeric([r for r in records if r['cohort']=='pi_repeat3'],'Pi・距離回路：CPUQuota 25%、同一入力の短期反復',
            '3–4–5の同一入力、warmup1を除く3回／1 process。独立cold trialや長時間安定性の結果ではない。\nメモリはunit全体。proof形式が異なるため、同一wire formatの比較ではない。',a.out/'03_pi_distance_repeat3')
    numeric([r for r in records if r['cohort']=='mac_distance'],'Mac ARM64・距離回路：追加記録と未完了試行',
            'Macの値をPiへ混ぜない。RSS samplingとpeak footprintは異なる指標。SP1はOS全体swap増分で停止、未検証。\nPlonky2はproof＋public、RISC ZeroはComposite receipt（Groth16 wrapperなし）。Mac nativeとPi portable BLAKE3も別条件。',a.out/'04_mac_distance',mac=True)
    numeric([r for r in records if r['cohort']=='pi_signed'],'Pi・gnark署名付き観測：CPUQuota 25%、1／2／4観測',
            'MiMC＋EdDSA＋Session/Policy/RID/index拘束。各完走processでwarmup1＋測定3。旧4観測partialも保持。\n平均フローは署名生成・setup・queue待ちを除く。別日・fresh setup/key。有限3batch入力であり持続1Hz成功ではない。',a.out/'05_pi_signed',signed=True)
    numeric([r for r in records if r['cohort']=='mac_signed'],'Mac・gnark署名付き観測：独立processと保護停止',
            '各processでfresh setup/key。完全同一Witnessのcold反復ではない。4観測v2はOS全体swap増分で停止。\n中断runの平均・サイズは記録済みの検証成功2件だけ。RSSはrun全体のsampling最大、Pi cgroupとは別指標。',a.out/'06_mac_signed',signed=True,mac=True)
    (a.out/'render-metadata.json').write_text(json.dumps({'matplotlib':matplotlib.__version__,'font':font,'new_measurements':False,'figure_count':7,'svg_fonts':'embedded paths'},ensure_ascii=False,indent=2)+'\n')
    print('Generated 7 PNG + 7 SVG; 18 configurations, 38 metric records; no new proof runs')

if __name__=='__main__':main()
