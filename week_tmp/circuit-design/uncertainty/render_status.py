"""Render public aggregate CSV only; no private input access."""
import argparse,csv
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
p=argparse.ArgumentParser();p.add_argument('results',type=Path);a=p.parse_args()
rows=list(csv.DictReader((a.results/'sensitivity.csv').open()))
names=['point','phone_x1','phone_x1_rid_reported','phone_x1_rid_speed15_clock2']
fig,axes=plt.subplots(1,3,figsize=(13,5),sharey=True)
for ax,attack in zip(axes,['unmodified','claim_away_50m','claim_away_50m_ideal_power']):
 vals=[next(r for r in rows if r['scenario']==name and r['attack']==attack) for name in names];bottom=[0]*len(vals)
 for status,color in [('consistent','#285b8e'),('hold','#e0a93a'),('alarm','#b44d4d')]:
  fractions=[int(r[status])/int(r['n'])*100 for r in vals]
  ax.bar(range(len(vals)),fractions,bottom=bottom,color=color,label=status)
  for i,(v,r) in enumerate(zip(fractions,vals)):
   if v>0:ax.text(i,bottom[i]+v/2,str(r[status]),ha='center',va='center',color='white' if status!='hold' else 'black',fontsize=9)
  bottom=[x+y for x,y in zip(bottom,fractions)]
 ax.set(xticks=range(4),xticklabels=['Point','Phone','+ RID','+ Motion\n& clock'],title=attack.replace('_',' '),ylim=(0,105))
axes[0].set_ylabel('Same 27 evaluation records [%]; labels = record counts');axes[-1].legend(loc='upper right',fontsize=8)
fig.suptitle('More assumed uncertainty can replace alarms with HOLD; not verified spoof detection')
fig.tight_layout();fig.savefig(a.results/'04_status_comparison.png',dpi=170)
