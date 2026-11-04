"""Standalone scientific figures from saved explanation aggregates."""
import argparse,json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

p=argparse.ArgumentParser();p.add_argument('result',type=Path);args=p.parse_args()
s=json.loads((args.result/'summary.json').read_text());rows=s['metrics'];hist=s['histograms']
plt.rcParams.update({'font.family':['Hiragino Sans','DejaVu Sans'],'font.size':11,'axes.spines.top':False,'axes.spines.right':False})
blue,red='#2F64A1','#D52B2B'
def get(**kw):return next(r for r in rows if all(str(r.get(k,''))==str(v) for k,v in kw.items()))
def save(fig,name):
 fig.tight_layout();fig.savefig(args.result/(name+'.png'),dpi=180);fig.savefig(args.result/(name+'.svg'));plt.close(fig)
fig,ax=plt.subplots(figsize=(8,4.8));x=np.arange(2)
for i,(case,label,c) in enumerate([('normal','正常',blue),('position30','申告を外向きに+30m',red)]):
 y=[100*get(study='position30',case=case,range_bin=b)['conditional_alarm_rate'] for b in ['20-40m','80-120m']]
 ax.bar(x+(i-.5)*.32,y,.32,label=label,color=c)
 for xx,v in zip(x+(i-.5)*.32,y):ax.text(xx,v+.3,f'{v:.2f}%',ha='center')
ax.set(xticks=x,xticklabels=['真距離20–40m\n同じ1,388件','真距離80–120m\n同じ5,047件'],ylim=(0,20),ylabel='受信記録中の警報率（%）',title='実験1：位置のみを改変したときの正常との差（合成10 seed）');ax.legend();save(fig,'01-position-normal-control')
fig,ax=plt.subplots(figsize=(8,4.8));cases=['normal','position100','joint100'];y=[100*get(study='power100',case=c,cohort='paired')['conditional_alarm_rate'] for c in cases]
ax.bar(np.arange(3),y,color=[blue,red,'#8CA7C3']);ax.set(xticks=range(3),xticklabels=['正常','申告+100m\n電力は元のまま','申告+100m\n電力も補償'],ylabel='共通標本中の警報率（%）',ylim=(0,40),title='実験2：全条件で同じ12,294件に限定した比較（合成）')
for x,v in enumerate(y):ax.text(x,v+.5,f'{v:.3f}%',ha='center')
save(fig,'02-power-fixed-cohort')
fig,ax=plt.subplots(figsize=(8,4.8));x=np.arange(3)
for i,(sd,c) in enumerate([(2,blue),(6,red)]):
 y=[100*get(study='common5',case=f'position{d}',noise_sd_db=sd)['conditional_alarm_rate'] for d in [0,30,100]]
 ax.bar(x+(i-.5)*.32,y,.32,color=c,label=f'独立雑音SD{sd}dB')
 for xx,v in zip(x+(i-.5)*.32,y):ax.text(xx,v+.5,f'{v:.2f}%',ha='center')
ax.set(xticks=x,xticklabels=['正常','水平位置+30m','水平位置+100m'],ylim=(0,100),ylabel='全72000送信中の警報率（%）',title='実験3：同じ送信を同じ5台で受信（合成10 seed）');ax.legend();save(fig,'03-common-event-noise')
fig,ax=plt.subplots(figsize=(8,4.8));x=np.arange(5)
for i,(case,label,c) in enumerate([('normal','正常',blue),('position30','申告+30m',red)]):
 a=sorted([r for r in hist if r['study']=='position30' and r['case']==case and r['range_bin']=='20-40m'],key=lambda r:r['bin'])
 ax.bar(x+(i-.5)*.32,[100*r['fraction'] for r in a],.32,label=label,color=c)
ax.axvline(1.5,color='#555555',linestyle='--',label='警報境界');ax.set(xticks=x,xticklabels=['0–0.5','0.5–1','1–1.5','1.5–2','2超'],ylabel='標本の割合（%）',xlabel='スコア÷閾値（1超で警報）',title='実験1：正常と改変のスコア分布の重なり（真距離20–40m）');ax.legend();save(fig,'04-score-overlap')
print('Saved 4 PNG/SVG figure pairs')
