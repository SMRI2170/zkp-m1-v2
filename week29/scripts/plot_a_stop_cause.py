#!/usr/bin/env python3
"""Scientific plots of the reconstructed history; no simulated RF measurements."""
import argparse,csv,json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager

def main():
 p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
 font=next((f.fname for f in font_manager.fontManager.ttflist if f.name=='Hiragino Sans'),None)
 if font:font_manager.fontManager.addfont(font);plt.rcParams['font.family']=font_manager.FontProperties(fname=font).get_name()
 plt.rcParams.update({'font.size':11,'axes.spines.top':False,'axes.spines.right':False,'axes.unicode_minus':False,'axes.axisbelow':True})
 s=json.loads((a.input/'summary.json').read_text());rows=list(csv.DictReader((a.input/'byte_history.csv').open()));x=[float(r['hours']) for r in rows];blue='#2f64a1';red='#c44343';gray='#7d8d9c';amber='#d68c2b'
 def save(fig,n):
  fig.savefig(a.output/(n+'.png'),dpi=170,bbox_inches='tight');fig.savefig(a.output/(n+'.svg'),bbox_inches='tight');plt.close(fig)
 fig,axs=plt.subplots(3,1,figsize=(11,9),sharex=True);fig.suptitle('A：保存量の増加と、実際の上限エラーを照合',fontsize=18)
 config=[('rx','root_completed_mib',192,'受信側が監視する共通保存先（完成時刻で近似）'),('sensor','sensor_mib',192,'GPS・BME280のJSONL（行ごとのバイト数を積算）'),('tx','tx_mib',128,'予備送信JSONL（行ごとのバイト数を積算）')]
 for ax,(k,col,cap,title) in zip(axs,config):
  y=[float(r[col]) for r in rows];ax.plot(x,y,color=blue,lw=2,label='履歴から算出した累積量');ax.axhline(cap,color=red,ls='--',lw=1.5,label=f'停止判定の境界 {cap} MiB');ax.set_ylim(0,max(y)*1.13);ax.set_title(title,loc='left',fontsize=12);ax.set_ylabel('累積量［MiB］');ax.grid(alpha=.18)
  v=s['stops'][k];t=v['hours_since_start'];value=v[col.replace('_mib','_mib')] if col in v else None
  if k=='rx':value=v['root_completed_mib']
  elif k=='sensor':value=v['sensor_jsonl_mib']
  else:value=v['tx_jsonl_mib']
  ax.axvline(t,color=gray,lw=1);ax.scatter([t],[value],color=red,zorder=4,s=38)
  label=f'停止ログ：{t:.2f}時間後\n{value:.2f} MiB'
  ax.annotate(label,(t,value),xytext=(-100,-48) if k!='sensor' else (15,-48),textcoords='offset points',color=red,fontsize=11,bbox={'facecolor':'white','edgecolor':'none','alpha':.9})
 axs[0].legend(loc='upper left',fontsize=9);axs[-1].set_xlabel('現行保存先での最初のセンサ記録からの経過時間［時間］');axs[-1].set_xlim(0,14)
 fig.text(.1,.015,'記録上の開始：11/14 17:43 JST。同一起動の経過時刻で照合し、UTCの独立校正はしていない。\n受信の192MiB境界は256MiB予算から次区間用64MiBを引いた値。補助ファイルの書込み途中の量は未計測。',fontsize=10,color=gray);fig.tight_layout(rect=[0,.07,1,.95]);save(fig,'01_cumulative_bytes_and_actual_stops')
 fig,ax=plt.subplots(figsize=(11,5.5));vr=list(csv.DictReader((a.input/'voltage_history.csv').open()));vx=[float(r['hours_start'])+.25 for r in vr];vy=[int(r['low_voltage_events']) for r in vr]
 ax.bar(vx,vy,width=.43,color=amber,label='低電圧警告の件数／30分')
 for k,label,c in [('rx','受信の上限停止',gray),('sensor','センサの上限停止',blue),('tx','送信の上限停止',red)]:ax.axvline(s['stops'][k]['hours_since_start'],color=c,ls='--',label=label)
 ax.set_xlim(0,14);ax.set_xlabel('最初のセンサ記録からの経過時間［時間］');ax.set_ylabel('警告件数／30分');ax.set_title('低電圧警告も併存。ただし、記録上限エラーとは別の証拠',fontsize=16,pad=65);ax.legend(loc='lower center',bbox_to_anchor=(.5,1.01),fontsize=9,ncol=2,frameon=False);ax.grid(axis='y',alpha=.2)
 fig.text(.1,.025,'カーネルの警告回数であり、独立した電源断の回数ではない。\n取得ログにOOM・SD I/Oエラーの該当メッセージは0件。電源品質が他の動作へ与えた影響は未確定。',fontsize=10,color=gray);fig.tight_layout(rect=[0,.10,1,1]);save(fig,'02_voltage_warnings_and_stops')
 fig,ax=plt.subplots(figsize=(10,5.5));sensor=s['rates']['sensor']['four_hour_jsonl_mib'];tx=s['rates']['tx']['four_hour_jsonl_mib'];total=sensor+tx
 ax.barh([1],[sensor],color=blue,label='センサJSONL');ax.barh([1],[tx],left=[sensor],color=gray,label='送信JSONL');ax.barh([0],[s['receiver_probe']['snapshot_used_bytes']/1024**2],color='#b7c7d5',label='回収時の共通保存先')
 ax.axvline(192,color=red,ls='--',label='受信の実効境界192MiB');ax.set_yticks([1,0],['空から4時間分を書く想定','旧記録が残った実際の保存先']);ax.set_xlim(0,365);ax.text(total+5,1,f'{total:.2f} MiB',va='center',fontsize=12);ax.text(328,0,f"{s['receiver_probe']['snapshot_used_bytes']/1024**2:.2f} MiB",va='center',fontsize=12);ax.set_xlabel('容量［MiB］');ax.set_title('過去の書込み速度で算出：4時間分は約116MiB（2種類のみ）',fontsize=15,pad=18);ax.legend(loc='lower right',fontsize=9);ax.grid(axis='x',alpha=.18)
 fig.text(.1,.025,'上段は過去の平均書込み速度×4時間の試算。11/16の実測記録量ではない。\n受信・診断・一時ファイルは別途必要。長時間連続運用や今後のデータ量を保証する値ではない。',fontsize=10,color=gray);fig.tight_layout(rect=[0,.10,1,1]);save(fig,'03_four_hour_storage_estimate')
 print('Saved 3 PNG and 3 SVG')
if __name__=='__main__':main()
