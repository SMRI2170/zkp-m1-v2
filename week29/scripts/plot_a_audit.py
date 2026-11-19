#!/usr/bin/env python3
"""Plot aggregate capture coverage and positive error evidence, never inferred uptime."""
import argparse,csv,datetime as dt,json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager

def main():
 p=argparse.ArgumentParser();p.add_argument('--analysis',type=Path,required=True);p.add_argument('--inventory',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
 font=next((f.fname for f in font_manager.fontManager.ttflist if f.name=='Hiragino Sans'),None)
 if font:font_manager.fontManager.addfont(font);plt.rcParams['font.family']=font_manager.FontProperties(fname=font).get_name()
 plt.rcParams.update({'font.size':11,'axes.spines.top':False,'axes.spines.right':False,'axes.axisbelow':True,'axes.unicode_minus':False})
 s=json.loads((a.analysis/'summary.json').read_text());files=json.loads(a.inventory.read_text())['files'];blue='#2f64a1';red='#c44343';gray='#738496'
 def save(fig,name):
  fig.savefig(a.output/(name+'.png'),dpi=170,bbox_inches='tight');fig.savefig(a.output/(name+'.svg'),bbox_inches='tight');plt.close(fig)
 # A zero is a verified timestamp-filter count, not receiver availability or packet reception probability.
 fig,axes=plt.subplots(2,1,figsize=(10,6),sharex=True);fig.suptitle('A：実験時間帯に該当するUTC付き記録の確認',fontsize=17)
 for ax,k,title in zip(axes,['rx','sensor'],['受信観測','GPS・BME280センサ記録']):
  ax.set_xlim(14,18);ax.set_ylim(0,1);ax.set_yticks([0,1]);ax.set_ylabel('記録件数／30分');ax.set_title(title,loc='left',fontsize=12)
  rows=[r for r in csv.DictReader((a.analysis/'field_30min_counts.csv').open()) if r['scope']=='active' and r['kind']==k]
  vals=[int(r['rows']) for r in rows];ax.plot([14.25+i*.5 for i in range(8)],vals,'o',color=blue)
  for i,v in enumerate(vals):ax.annotate(str(v),(14.25+i*.5,v),xytext=(0,9),textcoords='offset points',ha='center')
  ax.grid(axis='y',alpha=.15)
 axes[-1].set_xticks([14,15,16,17,18],['14:00','15:00','16:00','17:00','18:00']);axes[-1].set_xlabel('2026-11-16 日本時間（記録UTCから換算）')
 fig.text(.1,.015,'0件＝指定時刻に一致する保存行なし。電源OFF・未受信・電波なしを意味しない。\n予備送信ログはUTCを持たないため、この図では時刻を割り当てていない。',fontsize=10,color=red);fig.tight_layout(rect=[0,.10,1,.94]);save(fig,'01_field_window_coverage')
 # Failure evidence is measured on per-boot monotonic time, robust to wall clock jumps.
 fig,ax=plt.subplots(figsize=(10,5.8));bs={x['label']:x for x in s['boot_errors']};names=['boot -2','boot -1','boot 0'];labels=['直近3起動：1回目','直近3起動：2回目','現在の起動'];kinds=['sensor','rx','tx'];jp=['センサ記録','受信','予備送信'];colors=[blue,gray,red]
 for j,(k,lab,c) in enumerate(zip(kinds,jp,colors)):
  ys=[i+(j-1)*.21 for i in range(3)];vals=[bs[n]['first_budget_errors'][k]['since_boot_s'] for n in names]
  ax.scatter(vals,ys,label=lab,color=c,s=60)
  for x,y in zip(vals,ys):ax.annotate(f'{x:.1f}秒',(x,y),xytext=(7,0),textcoords='offset points',va='center')
 ax.set_xlim(0,53);ax.set_yticks(range(3),labels);ax.invert_yaxis();ax.set_xlabel('OS起動から最初の記録上限エラーまで［秒］');ax.set_title('A：再起動しても、起動後17〜44秒で上限エラー',fontsize=16,pad=50);ax.grid(axis='x',alpha=.2);ax.legend(loc='lower center',bbox_to_anchor=(.5,1.01),ncol=3,frameon=False)
 fig.text(.12,.015,'journalの起動後時刻による。再起動間の空白長・実際の電源OFF時間は、この図からは決められない。',fontsize=9.5,color=red);fig.tight_layout(rect=[0,.07,1,1]);save(fig,'02_budget_errors_after_boot')
 fig,ax=plt.subplots(figsize=(10,5.6));sizes=[]
 for sub in ['flight-tx','flight-sensors']:
  sizes.append(sum(f['size'] for f in files if '/kit-509808cf5258-c838fbec/captures/'+sub+'/' in f['path'])/1024**2)
 ax.barh([1,0],sizes,height=.42,color=[blue,gray]);limits=[128,192]
 for y,v,limit in zip([1,0],sizes,limits):
  ax.vlines(limit,y-.32,y+.32,color=red,linewidth=2.5);ax.text(v+4,y,f'{v:.2f} MiB  ／ 上限 {limit} MiB',va='center',fontsize=12)
 ax.set_xlim(0,295);ax.set_yticks([1,0],['予備送信の記録','センサ記録']);ax.set_xlabel('保存量［MiB］（1 MiB = 1,048,576 bytes）');ax.set_title('A：保存先に残る旧記録が、設定上限に到達',fontsize=16,pad=18);ax.grid(axis='x',alpha=.18)
 fig.text(.12,.025,'読取り時点の量。SD全体の空きは約9.2GiBあり、SD満杯とアプリの記録上限は別。\n受信側は共通capturesの総量＋次区間64MiBが256MiBを超えると停止する設計。',fontsize=10,color=red);fig.tight_layout(rect=[0,.12,1,1]);save(fig,'03_saved_bytes_vs_budget')
 print('Generated 3 PNG + 3 SVG')
if __name__=='__main__':main()
