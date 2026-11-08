"""Plots of aggregate time-match coverage and RT-derived offsets only."""
import argparse
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager


def main():
    p=argparse.ArgumentParser();p.add_argument('folder',type=Path);a=p.parse_args()
    x=json.loads((a.folder/'summary.json').read_text())
    names={f.name for f in font_manager.fontManager.ttflist}
    font=next((n for n in ['Hiragino Sans','Noto Sans CJK JP','IPAexGothic'] if n in names),'DejaVu Sans')
    plt.rcParams.update({'font.family':font,'axes.unicode_minus':False,'svg.fonttype':'none'})
    out=a.folder/'figures';out.mkdir(exist_ok=True)
    fig,ax=plt.subplots(figsize=(9,5.3))
    t=x['tolerances'];ax.plot([r['max_recorded_span_ms'] for r in t],
                            [100*r['nearest_time_candidate_rows']/r['reference_rows'] for r in t],'o-',color='#16365d')
    ax.axvline(20,color='#c4572a',ls='--',label='20ms：論文の記録区間長（参考）')
    ax.set(xlabel='5局の記録時刻に許す最大幅 [ms]',ylabel='近接時刻候補の割合 [%：LW1の3,530件が分母]',ylim=(-2,102),
           title='近い時刻へ揃えられても、同じ送信とは確認できない')
    ax.grid(alpha=.2);ax.legend(fontsize=9);ax.spines[['top','right']].set_visible(False)
    fig.text(.07,.015,'0〜20msは0件。時計精度・送信IDは未確認。近接候補を同一パケットや独立試行と数えない。',fontsize=10)
    fig.tight_layout(rect=(0,.07,1,1));save(fig,out/'01_time_coverage')
    fig,ax=plt.subplots(figsize=(9,5.3));positions=list(range(5));width=.34
    for channel,color,shift in [(1,'#16365d',-.17),(2,'#1684c0',.17)]:
        values=[r['d3_offset_db'] for r in x['calibration'] if r['channel']==channel]
        ax.bar([v+shift for v in positions],values,width,color=color,label=f'USRP ch{channel}')
    ax.set_xticks(positions,['LW1','LW2','LW3','LW4','LW5'])
    ax.set(xlabel='受信局',ylabel='D3で加算されたRSSオフセット [dB]',title='局ごと・チャネルごとに異なる、RTへの合わせ込み')
    ax.axhline(0,color='#777',lw=.8);ax.grid(axis='y',alpha=.2);ax.legend();ax.spines[['top','right']].set_visible(False)
    fig.text(.07,.015,'LW1〜4は全軌跡のRT誤差を最小化。LW5は両ch −10dBを手動指定。独立した絶対電力校正ではない。',fontsize=10)
    fig.tight_layout(rect=(0,.07,1,1));save(fig,out/'02_rt_offsets')


def save(fig,path):
    for ext in ['png','svg']:
        target=path.with_suffix('.'+ext);fig.savefig(target,dpi=180)
        if ext=='svg':target.write_text('\n'.join(v.rstrip() for v in target.read_text().splitlines())+'\n')
    plt.close(fig)


if __name__=='__main__':main()
