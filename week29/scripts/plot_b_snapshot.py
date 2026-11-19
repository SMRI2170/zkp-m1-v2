#!/usr/bin/env python3
"""Aggregate B RSSI plots; no MAC, ID or coordinates in public output."""
import argparse,csv,json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager

def main():
 p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--private-input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
 if not a.private_input.resolve().is_relative_to(Path(__file__).resolve().parents[2]/'captures'):raise ValueError('Row-level input stays in captures/')
 font=next((f.fname for f in font_manager.fontManager.ttflist if f.name=='Hiragino Sans'),None)
 if font:font_manager.fontManager.addfont(font);plt.rcParams['font.family']=font_manager.FontProperties(fname=font).get_name()
 plt.rcParams.update({'font.size':11,'axes.spines.top':False,'axes.spines.right':False,'axes.unicode_minus':False})
 s=json.load((a.input/'summary.json').open());rows=list(csv.DictReader((a.private_input/'source_rssi.csv').open()));blue='#2f64a1';red='#c44343';gray='#697d8f'
 def save(fig,n):
  fig.savefig(a.output/(n+'.png'),dpi=170,bbox_inches='tight');fig.savefig(a.output/(n+'.svg'),bbox_inches='tight');plt.close(fig)
 fig,ax=plt.subplots(figsize=(9,5));vals=[s['roles'].get('onboard_pi',0),s['reference']['attempted']];bars=ax.bar(['登録済みPi（Aとして登録）','未登録・Protocol 0'],vals,color=[blue,red],width=.55)
 for b,v in zip(bars,vals):ax.text(b.get_x()+b.get_width()/2,v+1200,f'{v:,}行',ha='center',fontsize=14)
 ax.set_ylim(0,62000);ax.set_ylabel('保存行数');ax.set_title('B：現行保存先に54,858行。未解析の531行も残っていた',fontsize=15,pad=20);ax.grid(axis='y',alpha=.2)
 fig.text(.1,.02,'時計ずれがあるため、今回の実験4時間の件数とはまだ断定しない。\n保存行数は無線パケット数・独立試行数ではない。申告IDの分類は機体認証ではない。',fontsize=10,color=gray);fig.tight_layout(rect=[0,.12,1,1]);save(fig,'01_saved_rows_by_source')
 fig,axs=plt.subplots(2,1,figsize=(11,7),sharey=True);fig.suptitle('B：時計対応が異なる区間を分けたRSSI履歴',fontsize=17)
 for ax,group in zip(axs,['C1','C2']):
  for kind,label,c,marker in [('registered_pi','登録済みPi',blue,'.'),('unregistered_candidate','未登録・Protocol 0',red,'o')]:
   rr=[r for r in rows if r['clock_group']==group and r['source_class']==kind]
   if rr:ax.scatter([float(r['elapsed_s_within_clock_group'])/60 for r in rr],[float(r['rssi_dbm']) for r in rr],s=7 if kind=='registered_pi' else 10,alpha=.4 if kind=='registered_pi' else .75,label=label,c=c,marker=marker)
  ax.set_title(f'時計区間 {group}',loc='left',fontsize=12);ax.set_ylabel('RSSI［dBm］');ax.grid(alpha=.18);ax.legend(loc='lower right',fontsize=9);ax.set_xlabel('各時計区間の最初の観測からの経過［分］');ax.set_ylim(-95,-10)
 fig.text(.1,.015,'C1/C2はUTCと起動後時刻の対応で分離。別起動・時計補正の可能性があり、単一のUTC軸へ接続しない。\nC2の約60分の空白は、電源OFF・送信停止・未受信等のどれか未確定。',fontsize=10,color=gray);fig.tight_layout(rect=[0,.10,1,.94]);save(fig,'02_rssi_by_clock_group')
 vals=sorted(float(r['positive_cache_update_interval_s']) for r in csv.DictReader((a.private_input/'candidate_intervals.csv').open()))
 fig,(ax1,ax2)=plt.subplots(1,2,figsize=(11,4.6));ax1.plot(vals,[(i+1)/len(vals)*100 for i in range(len(vals))],c=red);ax1.set_xlim(0,20);ax1.set_ylim(0,102);ax1.set_xlabel('更新間隔［秒］（0〜20秒へ拡大）');ax1.set_ylabel('累積割合［%］');ax1.grid(alpha=.2)
 ax1.axvline(s['candidate_intervals']['median_s'],c=blue,ls='--',label=f"中央値 {s['candidate_intervals']['median_s']:.2f}秒");ax1.axvline(s['candidate_intervals']['p95_s'],c=gray,ls='--',label=f"95百分位 {s['candidate_intervals']['p95_s']:.2f}秒");ax1.legend(loc='lower right',fontsize=9)
 ax2.hist(vals,bins=[0,1,2,5,10,20,60,300,4000],color=red,edgecolor='white');ax2.set_xscale('symlog',linthresh=1);ax2.set_xlabel('更新間隔［秒］（長い空白も含む）');ax2.set_ylabel('件数');ax2.grid(axis='y',alpha=.2);ax2.text(.95,.92,f"最大 {s['candidate_intervals']['max_s']/60:.2f}分",transform=ax2.transAxes,ha='right',color=red,fontsize=12)
 fig.suptitle('未登録送信元：更新間隔と長い観測空白を分離',fontsize=16);fig.text(.1,.015,'完全一致重複24行を除外した507行。間隔506件の記述集計で、パケット損失率や独立試行の検定ではない。',fontsize=9.5,color=gray);fig.tight_layout(rect=[0,.08,1,.92]);save(fig,'03_candidate_update_intervals')
 print('B plots: 3 PNG + 3 SVG generated')
if __name__=='__main__':main()
