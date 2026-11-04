"""Aggregate figures for the external-data audit and condition-block spread."""
import hashlib,json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from plot_paired_attacks import font_setup,export

root=Path(__file__).resolve().parents[2]/'week27/results'
font_setup()
x=json.loads((root/'cluster-uncertainty-20261103/summary.json').read_text())
labels=['正常','位置のみ','理想補償','±3dB補償','攻撃側n=2']
fig,ax=plt.subplots(figsize=(10,6));rates=np.array([r['mean_alarm_rate']*100 for r in x['estimates']]);interval=np.array([r['cluster_percentile_95'] for r in x['estimates']])*100
ax.errorbar(np.arange(5),rates,yerr=np.array([rates-interval[:,0],interval[:,1]-rates]),fmt='o',capsize=7,color='#345f85')
ax.set_xlim(-.5,4.7);ax.set_xticks(range(5),labels);ax.set_ylim(0,100);ax.set_ylabel('警報率（%）');ax.set_title('100m申告変更：条件の違いを残して評価する');ax.grid(axis='y',alpha=.2)
for i,y in enumerate(rates):ax.text(i+.12,y,f'{y:.2f}%',fontsize=11)
fig.subplots_adjust(bottom=.28)
fig.text(.12,.035,'16条件をまとまりとして10,000回再標本化。線は中央95%範囲。\n学習済み結果を固定した条件付きの広がり。新しい現場の性能保証ではない。\n地上送信→UAV受信のLoRa実測＋合成攻撃。Remote ID実機の評価ではない。',fontsize=10,color='#555555')
export(fig,root/'cluster-uncertainty-20261103','condition-block-spread')
x=json.loads((root/'loraiq-v2-audit-20261103/summary.json').read_text())
fig,(a,b)=plt.subplots(1,2,figsize=(11,6));a.bar(['全UAV行','位置あり','位置欠損'],[x['uav_rows'],x['position_available_uav_rows'],x['uav_rows_missing_position']],color=['#345f85','#388477','#b77e25']);a.set_title('UAV受信行の位置情報');a.set_ylabel('受信行数')
b.bar(['全UAV送信ID','厳格な採用候補'],[x['uav_frames']['transmissions'],x['uav_frames']['complete_consistent_multi_receiver_groups']],color=['#345f85','#388477']);b.set_title('同一送信の複数局比較候補');b.set_ylabel('送信グループ数')
for ax in [a,b]:
 ax.grid(axis='y',alpha=.2);ax.set_ylim(0,ax.get_ylim()[1]*1.12)
 for p in ax.patches:ax.text(p.get_x()+p.get_width()/2,p.get_height(),f'{p.get_height():,.0f}',ha='center',va='bottom')
fig.subplots_adjust(bottom=.29,wspace=.35)
fig.text(.12,.035,'採用候補：全受信行の位置あり・ペイロードと識別情報一致・局重複なし。\nCSVはSNRのみ。dBm RSSIとUAV高度はなく、位置偽装の検出率は未評価。\nLoRaIQ v2：UAV送信→屋上受信。左右で集計単位が異なる。',fontsize=10,color='#555555')
export(fig,root/'loraiq-v2-audit-20261103','data-gates')

for dirname in ['cluster-uncertainty-20261103','loraiq-v2-audit-20261103']:
    out=root/dirname
    manifest=dict(plot_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  helper_code_sha256=hashlib.sha256(Path(__file__).with_name('plot_paired_attacks.py').read_bytes()).hexdigest(),
                  outputs={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.suffix in ('.png','.svg')})
    (out/'figure-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
