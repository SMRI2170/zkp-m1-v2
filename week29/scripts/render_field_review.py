#!/usr/bin/env python3
"""Anonymous group figures and a PRIVATE real-event viewer; no new detector."""
import html,json,math
from pathlib import Path
from evaluate_claim_attacks import prediction,compensation


def serializable_series(series):
    output=[]
    for item in series:
        values=[float(v) for v in item['drawn']]
        if not all(math.isfinite(v) for v in values):raise ValueError('Nonfinite plotted series')
        output.append(dict(name=item['name'],drawn=values))
    return output


def synthetic_explanation():
    a,n,d,new,rssi,tau=-40.,2.,10.,40.,-60.,3.
    dp=compensation(d,new,n)
    return dict(source='entirely_synthetic_explanation_not_field_result',intercept=a,n=n,distance=d,modified_distance=new,
        rssi=rssi,threshold=tau,delta_power=dp,baseline_score=abs(rssi-prediction(d,a,n)),
        claim_only_score=abs(rssi-prediction(new,a,n)),compensated_score=abs(rssi+dp-prediction(new,a,n)))


def private_view(events,model,path,gated_rows=None):
    # No embedded identifiers, coordinates or UTC times; still private individual evidence.
    data=json.dumps(events,ensure_ascii=False,allow_nan=False).replace('<','\\u003c')
    held_data=json.dumps([r for r in (gated_rows or []) if not r['selected']],ensure_ascii=False,allow_nan=False).replace('<','\\u003c')
    threshold=model['frozen_model']['threshold_db']
    template='''<!doctype html><meta charset="utf-8"><title>Private field proxy explanation</title>
<style>body{font:14px system-ui;background:#f6f8fc;color:#142b49;margin:18px;max-width:1400px}h1{font-size:23px;margin:4px 0}h2{font-size:18px;margin:4px 0 10px}p{margin:7px 0}header,.box{background:white;padding:14px;border-radius:12px;margin:8px 0}.eventGrid{display:grid;grid-template-columns:1fr 1fr;gap:14px}select{font:inherit;padding:5px;margin:4px}table{width:100%;border-collapse:collapse}td,th{padding:6px;text-align:left;border-bottom:1px solid #ddd}.badge{color:#b54708;font-weight:bold}small{font-size:12px}svg{width:100%;height:235px}@media(max-width:1000px){.eventGrid{grid-template-columns:1fr}}</style>
<header><h1>非公開：1観測の計算と判定理由</h1><p>実測RSSI＋RID申告水平距離／位置・電力変更は合成。独立真位置・実攻撃ラベルなし。</p><p class="badge">同一物理送信：未確認　／　端末間時刻：未確定　／　3D距離：評価不能</p>
<label>評価内の観測 <select id="ordinal"></select></label><label>変更条件 <select id="condition"></select></label></header><div class="eventGrid">
<section class="box"><h2 id="state"></h2><p id="explain"></p><table><tbody id="values"></tbody></table></section>
<section class="box"><h2>スコアと固定閾値</h2><svg id="chart" viewBox="0 0 1000 240"></svg><p>閾値は校正26行のみから固定。評価27行で調整していない。警報はモデル不整合であり、位置偽装や真位置の確定ではない。</p></section>
</div><div class="eventGrid"><section class="box"><h2>採用前に保留した行</h2><select id="heldrow"></select><p id="heldreason"></p><small>品質ゲートで保留した行にはモデル判定を適用しない。</small></section>
<section class="box"><h2>全体結果との対応</h2><p>評価27行の未改変警報：13行（48.15%）。50m遠方変更だけでは27行が警報。そのうち13行は元から警報、14行が新しく警報。同じモデルの理想補償では元の13行がそのまま残る。</p><small>このHTMLは個票を含むのでGitへ追加・外部公開しない。公開図は匿名集計または完全合成の説明例のみ。</small></section></div>
<script>
const rows=DATA;const gates=GATES;
const heldSelect=document.getElementById("heldrow"),heldReason=document.getElementById("heldreason");
gates.forEach((r,i)=>heldSelect.add(new Option(r.node+" / 保留行 "+(r.row_index+1),i)));
function showHeld(){let r=gates[Number(heldSelect.value)];heldReason.textContent=r?"保留理由："+r.reasons.join(", ")+" ／ 元観測対応："+r.raw_association:"このfixtureには保留行なし"};heldSelect.onchange=showHeld;showHeld();
const $=id=>document.getElementById(id);const key=r=>[r.direction,r.shift_m,r.mode].join('/');
[...new Set(rows.map(r=>r.ordinal))].forEach(i=>$('ordinal').add(new Option(String(i+1),i)));
const dirs={away:'遠方',toward:'近方',transverse:'直交方向'};const modes={claim_only:'申告変更のみ',model_matched_unbounded:'同モデルの理想補償',constant_plus6:'RSSI +6dB',constant_minus6:'RSSI -6dB',time_varying6:'時間変動6dB'};
[...new Set(rows.map(key))].forEach(k=>{const [d,x,m]=k.split('/');$('condition').add(new Option(dirs[d]+' '+x+'m / '+(modes[m]||m),k))});
$('condition').value='away/50/claim_only';
function update(){const r=rows.find(x=>x.ordinal===Number($('ordinal').value)&&key(x)===$('condition').value);if(!r)return;
const held=r.status.startsWith('HELD');$('state').textContent=held?'保留：受信局を越える近方変更':(r.changed_alarm?'警報：固定閾値を超過':'閾値以下：真位置が確認できたという意味ではない');
$('explain').textContent=held?'変更後の距離を小さな正数へ丸めず、この条件を評価対象外にした。':'観測・仮定・合成変更を分けて、同じ元観測のスコアを比較する。';
const fields=held?[['状態',r.status]]:[['観測RSSI [dBm]',r.rssi_dbm],['元の申告水平距離 [m]',r.claimed_horizontal_distance_m],['合成変更後の申告距離 [m]',r.modified_distance_m],['合成dB加算 [dB]',r.synthetic_power_added_db],['未改変スコア [dB]',r.baseline_score_db],['変更後スコア [dB]',r.changed_score_db],['固定閾値 [dB]',r.threshold_db],['学習距離域',r.training_support==='outside'?'範囲外':'範囲内'],['独立真値','なし（申告を基準と仮定）']];
$('values').replaceChildren(...fields.map(([k,v])=>{let tr=document.createElement('tr');let a=document.createElement('th'),b=document.createElement('td');a.textContent=k;b.textContent=typeof v==='number'?v.toFixed(4):v;tr.append(a,b);return tr}));
const svg=$('chart');svg.replaceChildren();if(held)return;const max=Math.max(r.threshold_db,r.changed_score_db,r.baseline_score_db)*1.2||1;const scale=v=>220+v/max*700;
function node(tag,attrs,text){let n=document.createElementNS('http://www.w3.org/2000/svg',tag);for(let k in attrs)n.setAttribute(k,attrs[k]);if(text)n.textContent=text;svg.append(n)}
[['未改変',r.baseline_score_db,60,'#254b7b'],['合成変更',r.changed_score_db,130,'#2d82b7']].forEach(([label,v,y,c])=>{node('text',{x:10,y:y+22},label);node('rect',{x:220,y,width:scale(v)-220,height:32,fill:c});node('text',{x:scale(v)+10,y:y+22},v.toFixed(3)+' dB')});node('line',{x1:scale(r.threshold_db),x2:scale(r.threshold_db),y1:30,y2:190,stroke:'#ba3b32','stroke-width':3,'stroke-dasharray':'7 4'});node('text',{x:scale(r.threshold_db),y:220},'固定閾値 '+r.threshold_db.toFixed(3)+' dB');}
$('ordinal').onchange=update;$('condition').onchange=update;update();
</script>'''
    path.write_text(template.replace('DATA',data).replace('GATES',held_data));path.chmod(0o600)


def render(quality,model,paired,sensitivity,events,output,private):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    candidates=['Hiragino Sans','Noto Sans CJK JP','IPAexGothic','DejaVu Sans']
    available={f.name for f in font_manager.fontManager.ttflist}
    plt.rcParams.update({'font.family':next((f for f in candidates if f in available),'DejaVu Sans'),'axes.unicode_minus':False,'font.size':11})
    series=[]
    blue,dark,red,gray='#2585b6','#17395c','#b83b32','#b8c5d1'
    def save(fig,name):fig.savefig(output/name,dpi=170,bbox_inches='tight');plt.close(fig)
    # Counts only: no real locations or individual scores.
    fig,axes=plt.subplots(1,2,figsize=(13,4.8));labels=list(quality['nodes']);selected=[quality['nodes'][k]['selected_rows'] for k in labels];held=[quality['nodes'][k]['held_rows'] for k in labels]
    axes[0].bar(labels,selected,label='水平代理評価へ採用',color=blue);axes[0].bar(labels,held,bottom=selected,label='保留',color=gray)
    for i,(s,h) in enumerate(zip(selected,held)):axes[0].text(i,s+h+4,f'{s}/{s+h}',ha='center')
    axes[0].set(ylabel='保存行数 [行]',title='324行の元レコードを再照合：採用105行',ylim=(0,180));axes[0].legend(fontsize=9)
    axes[1].axis('off');axes[1].text(0,1,'今回実行できること',va='top',weight='bold',fontsize=15,color=dark);axes[1].text(0,.86,'同端末・同bootの水平代理評価',color=blue,fontsize=13)
    axes[1].text(0,.67,'評価不能：独立した根拠が不足',weight='bold',color=red,fontsize=14);axes[1].text(0,.53,'端末間の確定時刻／3D距離\n同一物理送信による電力相殺\n真位置に対するFPR・TPR／PDR\n独立飛行runの信頼区間',va='top',linespacing=1.7)
    series.extend([dict(name='quality_selected',drawn=[p.get_height() for p in axes[0].patches[:len(labels)]]),dict(name='quality_held',drawn=[p.get_height() for p in axes[0].patches[len(labels):]])])
    fig.suptitle('① 品質ゲート：API鮮度・非mock・位置対応を元SQLiteで再確認',weight='bold');fig.tight_layout();save(fig,'01_quality_and_capabilities.png')
    fig,axes=plt.subplots(1,3,figsize=(15,4.8));parts=model['partitions'];names=['学習','校正','評価'];tau=model['frozen_model']['threshold_db']
    med=[p['signed_residual_median_db'] for p in parts];lo=[m-p['signed_residual_q25_db'] for m,p in zip(med,parts)];hi=[p['signed_residual_q75_db']-m for m,p in zip(med,parts)]
    axes[0].errorbar(range(3),med,yerr=[lo,hi],fmt='o',capsize=7,color=dark);axes[0].set(xticks=range(3),xticklabels=names,ylabel='符号付き残差 [dB]',title='中央値と四分位範囲');axes[0].axhline(tau,color=red,ls='--');axes[0].axhline(-tau,color=red,ls='--');axes[0].axhline(0,color=gray,ls=':')
    axes[1].bar(names,[p['alarm_fraction']*100 for p in parts],color=[dark,blue,red]);axes[1].set(ylabel='未改変の警報割合 [%]',ylim=(0,65),title=f'校正のみで固定：閾値{tau:.3f}dB')
    for i,p in enumerate(parts):axes[1].text(i,p['alarm_fraction']*100+2,f"{p['alarm_count']}/{p['n']}",ha='center')
    blocks=model['descriptive_blocks'];axes[2].bar([p['block'] for p in blocks],[p['baseline_alarm_fraction']*100 for p in blocks],color=blue);axes[2].set(ylabel='未改変の警報割合 [%]',ylim=(0,110),xlabel='連続観測ブロック（独立runではない）',title='時間に沿う記述集計')
    for i,p in enumerate(blocks):axes[2].text(i,p['baseline_alarm_fraction']*100+3,f"{p['baseline_alarm_count']}/{p['n']}",ha='center',fontsize=9)
    for ax in axes:ax.grid(axis='y',alpha=.2)
    series.extend([dict(name='partition_alarm_percent',drawn=[p.get_height() for p in axes[1].patches]),dict(name='block_alarm_percent',drawn=[p.get_height() for p in axes[2].patches])])
    fig.suptitle('② 校正と評価で警報割合が変化：評価13/27件は真のFPRではない',weight='bold');fig.tight_layout();save(fig,'02_frozen_model_failure.png')
    focus=[next(p for p in paired if p['direction']=='away' and p['shift_m']==50 and p['mode']==m) for m in ('claim_only','model_matched_unbounded')]
    fig,axes=plt.subplots(1,2,figsize=(13,5));bottom=[0,0]
    for k,label,color in [('alarm_to_alarm','元から警報→警報',red),('quiet_to_alarm','元は閾値以下→警報',blue),('alarm_to_quiet','元は警報→閾値以下','#d7ab62'),('quiet_to_quiet','元も変更後も閾値以下',gray)]:
        v=[p[k] for p in focus];axes[0].bar(['50m申告変更のみ','50m変更＋理想補償'],v,bottom=bottom,label=label,color=color)
        for i,(x,b) in enumerate(zip(v,bottom)):
            if x:axes[0].text(i,b+x/2,str(x),ha='center',va='center',color='white' if color!=gray else dark,weight='bold')
        bottom=[b+x for b,x in zip(bottom,v)]
    axes[0].set(ylabel='同じ元観測27行 [行]',ylim=(0,32),title='100%警報でも13行は元から警報');axes[0].legend(fontsize=9,loc='upper left',bbox_to_anchor=(0,-.16))
    x=synthetic_explanation();axes[1].barh(['未改変','申告だけ変更','変更＋理想補償'],[x['baseline_score'],x['claim_only_score'],x['compensated_score']],color=[gray,blue,dark]);axes[1].axvline(x['threshold'],color=red,ls='--',label='説明用の閾値3dB');axes[1].set(xlabel='絶対残差 [dB]',title='右図は完全合成の説明例（実測ではない）',xlim=(0,15));axes[1].legend(fontsize=9)

    for i,value in enumerate([x['baseline_score'],x['claim_only_score'],x['compensated_score']]):axes[1].text(value+.2,i,f'{value:.2f}',va='center',color=dark)
    axes[1].text(.02,-.25,'d=10m → 40m、n=2\n同じモデルで −12.04dBを加えると残差0へ戻る',transform=axes[1].transAxes,fontsize=10)
    series.extend([dict(name='paired_counts_50m',drawn=[p.get_height() for p in axes[0].patches]),dict(name='synthetic_scores',drawn=[p.get_width() for p in axes[1].patches])])
    fig.suptitle('③ 何が増えた警報か／電力補償で何が元に戻るか',weight='bold');fig.tight_layout();save(fig,'03_paired_alarms_and_synthetic_example.png')
    fig,ax=plt.subplots(figsize=(10,5));deltas=[0,20,50,100];totals=[quality['selected_rows']]+[sum(x['after_claim_change_selected'] for x in sensitivity if x['synthetic_away_shift_m']==d) for d in deltas[1:]]
    ax.plot(deltas,totals,'o-',color=blue,linewidth=2);ax.axhline(quality['selected_rows'],color=gray,ls='--',label='実際に評価へ採用した凍結105行');ax.set(xticks=deltas,ylim=(0,370),xlabel='申告のみを受信局から遠ざける合成変位 [m]',ylabel='条件を通る行数（全324行）',title='④ 採用条件も申告距離に依存：検出性能の改善ではない')
    for d,n in zip(deltas,totals):ax.annotate(str(n),(d,n),xytext=(0,10),textcoords='offset points',ha='center')
    ax.text(.03,.06,'精度申告 ÷ 申告距離 が0.25以下となる条件の感度分析\n元の採用マスク・学習・閾値は変更していない',transform=ax.transAxes,fontsize=11);ax.legend();ax.grid(alpha=.2);series.append(dict(name='selection_counts',drawn=list(ax.lines[0].get_ydata())));save(fig,'04_claim_dependent_gate.png')
    (output/'figure-series.json').write_text(json.dumps(serializable_series(series),indent=2,allow_nan=False)+'\n')
    private_view(events,model,private/'event-explanation-private.html',json.loads((private/'row-gates-private.json').read_text()))
    (output/'synthetic-explanation.json').write_text(json.dumps(synthetic_explanation(),indent=2)+'\n')
