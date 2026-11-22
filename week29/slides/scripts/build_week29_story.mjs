import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
// Use the supplied artifact-tool runtime. RUNTIME_NODE_MODULES is required.
const ROOT=path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const MOD=process.env.RUNTIME_NODE_MODULES;
if(!MOD) throw Error('RUNTIME_NODE_MODULES is required');
const {Presentation,PresentationFile}=await import(path.join(MOD,'@oai/artifact-tool/dist/artifact_tool.mjs')).catch(async()=>{
 const {createRequire}=await import('node:module'); const req=createRequire(path.join(MOD,'__runtime__.cjs'));return import(req.resolve('@oai/artifact-tool'));
});
const SKILL=process.env.PRESENTATIONS_SKILL_DIR;
if(!SKILL) throw Error('PRESENTATIONS_SKILL_DIR is required');
const {makeNativeBulletParagraphs,applyPresentationChartFont}=await import(path.join(SKILL,'container_tools/artifact_tool_utils.mjs'));
const BUILD=path.join(ROOT,'.cache/week29-slides-build');await fs.mkdir(BUILD,{recursive:true});
const P=Presentation.create({slideSize:{width:960,height:720}});
const C={ink:'#282629',blue:'#2F64A1',navy:'#2B5581',light:'#EDF3F7',gray:'#F3F4F6',muted:'#66717C',grid:'#DCE3E9',red:'#D63434',pale:'#91A9C1'};
const FONT='Hiragino Kaku Gothic ProN W3';
const FONT_BOLD='Hiragino Kaku Gothic ProN W6';
const titles=[],chartOwners=[],tableOwners=[],sources=[];
function rect(s,x,y,w,h,fill,line='none'){return s.shapes.add({geometry:'rect',position:{left:x,top:y,width:w,height:h},fill,line:{fill:line,width:line==='none'?0:1}})}
function text(s,str,x,y,w,h,size=24,color=C.ink,bold=false,align='left'){
 const q=s.shapes.add({geometry:'textbox',position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
 q.text=str;q.text.style={typeface:bold?FONT_BOLD:FONT,fontSize:size,color,bold,alignment:align,verticalAlignment:'top',autoFit:'none',insets:0};return q;
}
function slide(title,intro='',kind=''){
 const s=P.slides.add();s.background.fill='#FFFFFF';titles.push(title);
 rect(s,0,0,960,67,C.gray);text(s,title,42,12,880,50,34,C.ink,true);
 if(intro){rect(s,42,87,5,26,C.blue);text(s,intro,58,86,860,61,23,C.blue,true);}
 if(kind) text(s,kind,650,146,265,22,17,C.muted,false,'right');
 text(s,'__AUTO_SLIDE__',875,685,40,20,14,'#888888',false,'right');return s;
}
function bullet(s,items,x=47,y=190,w=865,h=390,size=25){
 const q=text(s,'',x,y,w,h,size);q.text=makeNativeBulletParagraphs(items,{marginLeftPoints:22.5,hangingPoints:14,spaceAfterPoints:12});return q;
}
function section(s,heading,items,y){
 const q=text(s,'',43,y,870,34,25,C.blue,true);q.text=makeNativeBulletParagraphs([heading],{marginLeftPoints:20,hangingPoints:20,spaceAfterPoints:0,bulletCharacter:'■'});
 bullet(s,items,48,y+43,860,130,24);
}
function note(s,items,y=594){bullet(s,items,49,y,862,78,21);}
function table(s,headers,rows,widths=null,y=184,h=350,size=22){
 const vals=[headers,...rows];const t=s.tables.add({rows:vals.length,columns:headers.length,left:45,top:y,width:870,height:h,values:vals,...(widths?{columnWidths:widths}:{})});
 for(let r=0;r<vals.length;r++)for(let c=0;c<headers.length;c++){
  const z=t.getCell(r,c);z.fill=r===0?C.navy:(r%2? '#FFFFFF':C.light);z.text.style={typeface:r===0?FONT_BOLD:FONT,fontSize:size,color:r===0?'#FFFFFF':C.ink,bold:r===0,verticalAlignment:'middle',insets:{left:10,right:8,top:7,bottom:7}};
 }
 tableOwners.push(titles.length);return t;
}
function chart(s,cats,series,{ytitle='',max=null,min=0,kind='bar',stack=false,pos=null,format='0.##',legend=false,labels=true}={}){
 const q=s.charts.add(kind,{
  position:pos||{left:65,top:181,width:825,height:376},categories:cats,
  series:series.map((a,i)=>({name:a.name,values:a.values.map(v=>v===null?null:Number(v.toFixed(8))),fill:a.fill||[C.blue,C.pale,'#CDD5DD'][i%3],line:{fill:a.fill||[C.blue,C.pale,'#CDD5DD'][i%3],width:2}})),
  hasLegend:legend,legend:{position:'bottom',textStyle:{typeface:FONT,fontSize:18,fill:C.ink}},
  barOptions:{direction:'column',grouping:stack?'stacked':'clustered',gapWidth:100},
  xAxis:{textStyle:{typeface:FONT,fontSize:19,fill:C.ink},line:{fill:'#B8C0C8',width:1},title:undefined},
  yAxis:{min,...(max!==null?{max}:{}),numberFormatCode:format,textStyle:{typeface:FONT,fontSize:18,fill:C.muted},title:{text:ytitle,textStyle:{typeface:FONT,fontSize:19,fill:C.ink}},majorGridlines:{fill:C.grid,width:0.7}},
  dataLabels:{showValue:labels,position:stack?'center':'outEnd',numberFormatCode:stack?'0;-0;;':format,textStyle:{typeface:FONT,fontSize:20,fill:C.ink}},
 });if(stack) q.series.getItemAt(0).dataLabels={showValue:true,position:'center',numberFormatCode:'0;-0;;',textStyle:{typeface:FONT,fontSize:20,fill:'#FFFFFF'}};applyPresentationChartFont(q,{fontFamily:FONT});chartOwners.push(titles.length);return q;
}
function columns(s,heads,bodies,{y=190}={}){
 heads.forEach((h,i)=>{const w=850/heads.length;const x=45+i*w;text(s,h,x,y,w-28,55,26,C.blue,true);text(s,bodies[i],x,y+70,w-28,260,24);});
}
function seq(s,heads,descs,y=220){
 const n=heads.length,w=840/n;
 heads.forEach((a,i)=>{const x=50+i*w;text(s,a,x,y,w-28,60,26,C.blue,true);text(s,descs[i],x,y+76,w-32,145,23);if(i<n-1)text(s,'→',x+w-34,y+8,30,45,27,C.muted);});
}
let s;
s=slide('実機Remote IDの受信実験');
text(s,'取得データの解析と収録の改善',65,205,830,72,39,C.navy,true);
text(s,'Raspberry Pi・Androidで何が取れたか\nRSSIによる位置申告の検査をどこまで進められるか',65,315,835,100,26);
text(s,'第29回  研究進捗',65,530,800,40,24,C.blue,true);
s=slide('目次');
section(s,'受信実験と取得データ',['実験の構成、保存した記録'],150);
section(s,'記録・取得の問題と修正',['保存上限、スキャン、Androidの復帰'],280);
section(s,'取得データを使った解析',['未改変記録、申告変更、電力補償の比較'],410);
section(s,'まとめ・今後',['今回の結果と、次の実験で揃える条件'],540);


s=slide('今回の作業内容','回収した記録の解析と、収録を続けるための修正');table(s,['区分','実施内容'],[['データ回収','Pi・Androidの記録保全、実機IDの再解析'],['Pi','保存上限への対応、再起動確認、スキャン比較'],['Android','SQLite保全、背景収録、権限復帰の修正'],['品質監査','元DBとの照合、時刻・自己位置・用途の確認'],['RSSI評価','RSSI解析、申告変更・電力補償の比較']], [190,680],180,390);note(s,['実験記録の解析と、後日の動作試験を分けて整理']);


s=slide('今回の実験で調べたいこと','受信したRSSIを、位置申告の検査に使えるか');
section(s,'取得するもの',['ドローンのRemote ID、生の受信情報、RSSI、時刻','Androidでは自身の位置も保存'],175);
section(s,'調べること',['記録が残るか、どの間隔で新しい内容が取れるか','位置申告だけを変えたとき、RSSIとのずれを見つけられるか'],385);
note(s,['送信電力が変わる場合も含め、使える条件と限界を確認']);
s=slide('実験の構成','機体の送信と、各端末の受信・保存');
text(s,'実ドローン',345,175,310,45,29,C.blue,true,'center');
text(s,'Remote IDの送信',335,230,330,40,26,C.ink,false,'center');
text(s,'↓',451,282,80,45,34,C.muted,false,'center');
text(s,'Pi B〜F',120,350,315,46,28,C.blue,true,'center');
text(s,'受信時刻・RSSI・生情報',70,410,405,85,24,C.ink,false,'center');
text(s,'Android',545,350,315,46,28,C.blue,true,'center');
text(s,'受信情報に加え\n端末自身の位置を保存',515,410,375,100,24,C.ink,false,'center');
note(s,['Pi Aは搭載側の受信・予備送信・GPS/BME280記録を担当','役割の模式図。実験時の配置・距離・高さは記録から未確定']);
s=slide('実験の方法','実機の記録を回収し、問題を追加試験で調べる');
table(s,['段階','実施内容'],[['実機の観測','運用者申告：11月16日14〜18時頃'],['受信・保存','Pi・AndroidでWi-Fiスキャン由来の情報を保存'],['回収・解析','JSONL・SQLiteを保持し、実機IDを指定して再解析'],['追加試験','Pi Beaconを使い、スキャン条件・消灯時の動作を比較']], [235,635],180,350);
note(s,['ノード間時計の対応は未確定。申告時間帯と保存時刻を単純には一致させない','追加試験には実ドローンを使用せず、研究用Pi Beaconを使用']);


s=slide('回収した実機IDの記録','保存した生情報を参照デコーダで再解析','実測記録の集計');table(s,['端末','対象IDの保存行','今回の用途'],[['Pi B','531','受信間隔・内容反復の解析'],['Pixel 6 Pro','132','自己位置対応・RSSI解析'],['ASUS-1','146','自己位置・採用条件の確認'],['ASUS-2','46','自己位置・採用条件の確認'],['Pixel 8','0','指定した実機IDの解析対象なし']], [270,210,390],180,375);note(s,['計855保存行。独立した物理パケット数や受信率とは別']);


s=slide('保存したデータ','保存項目と、解析への使い道');table(s,['取得項目','内容・解析での使い道'],[['生の受信情報','Vendor IE・Message Pack。未分類行の再解析'],['RSSI・周波数','保存時の受信強度とチャネル情報'],['時刻','観測・保存時刻、boot・単調時刻による順序確認'],['機体の申告情報','RIDのID・座標・高度等。解釈できた項目を利用'],['Androidの自己位置','位置・測位時刻・provider・OS精度申告']], [255,615],180,375);note(s,['Androidの対象324行には、対応する自己位置の記録あり','Pi Bは自己位置の記録がなく、今回の水平距離解析から除外']);


s=slide('Aノードの記録が少なかった原因','受信ログが少なくても、共通の保存先が上限に到達');
seq(s,['準備中の蓄積','共通の容量判定','記録停止'],['センサ・予備送信も\n同じ保存先に記録','受信ログ以外も含めて\n保存量を計算','空きSDがあっても\n設定した予算で停止']);
section(s,'調査したもの',['保存履歴のバイト数、Aに導入したコード、停止ログ','低電圧警告も確認。全ての空白の原因はまだ確定していない'],490);
s=slide('保存量と停止ログの照合','コードの停止条件と、実際の記録を比較');
table(s,['対象','上限','停止時の量'],[['受信の共通保存先','実効192 MiB','約192.08 MiB'],['センサJSONL','192 MiB','192.008 MiB'],['予備送信JSONL','128 MiB','128.010 MiB']], [320,230,320],185,270);
section(s,'確認したこと',['上限超過と明示的な容量エラーが対応','共通保存量は補助ファイル完成時刻から再構成した近似'],500);


s=slide('保存先と停止処理の修正','旧記録を保持し、停止理由を残す');seq(s,['セッション分離','容量・RAM監視','理由付き停止'],['役割別・起動別に保存\n旧記録と新記録を分離','保存予算と空き容量\nメモリ余力を確認','上限や失敗を明示\n診断情報を保存']);note(s,['B〜Fへ適用し、旧記録の保持とOS再起動後の復帰を確認','実際の電源断・実飛行中の負荷は、今後の確認事項']);


s=slide('修正後の動作確認','旧記録を残し、再起動と待機中の収録を確認');
table(s,['確認内容','結果'],[['B〜Fへの適用','旧記録を保持、OS再起動後の収録復帰を確認'],['C・Dの待機監視','各4時間を完走、health FAULTは0件'],['この試験中の対象RID','0件。全監視サンプルが待機状態']], [305,565],190,265);
section(s,'ここまでで確認できた範囲',['起動・保存・監視の動作を確認','実ドローン受信中の長時間保存は、別の試験が必要'],500);
s=slide('取得頻度の確認','研究用Pi Beaconで、要求間隔とスキャン範囲を比較','制御RF試験');
table(s,['条件','設定'],[['送信・受信','Dから研究用Beaconを送信、Cで受信'],['送信内容','約1秒ごとにカウンタを更新。位置情報なし'],['比較','全チャネル／既知周波数、待ち時間0.5〜5秒'],['区間','各20秒×2巡、2巡目は順序を反転']], [240,630],180,330);
note(s,['短い間隔で要求しても、新しい内容を同じ頻度で取得できるとは限らない','次のページは、要求後0.5秒待ちの条件を比較']);


s=slide('スキャン条件とbusy','要求後の待ち時間0.5秒の条件を比較','制御RF試験');chart(s,['全チャネル\n19 / 26要求','既知周波数のみ\n0 / 79要求'],[{name:'busy割合',values:[100*19/26,0]}],{ytitle:'busy／スキャン要求［%］',max:100,format:'0.0'});note(s,['全チャネルではスキャン中の次要求でbusy（受付失敗）が発生','未知周波数の探索性能は、今回の比較対象外']);


s=slide('画面を消したときの取得','ASUS 2台、各20秒。Doze：OSの省電力状態','制御RF試験');chart(s,['画面表示','ホーム','消灯','強制Doze'],[{name:'ASUS-1',values:[4,4,4,1],fill:C.blue},{name:'ASUS-2',values:[8,7,6,2],fill:C.pale}],{ytitle:'対象Vendor内容の種類数',max:10,format:'0',legend:true});note(s,['消灯中もID・RSSIを保存。省電力状態では新規取得が減少','強制Dozeでは最初の5秒以降、新しい対象観測が0件']);


s=slide('Androidで受信を再開できない不具合','権限取消し後、SQLiteの復旧が必要な状態で停止');
seq(s,['書込み中断','DBを開けず','保全して復旧'],['位置権限の取消し\n復旧用journalが残存','読み取り専用では\n復旧の書込みが不可','元DBとjournalを退避\n標準rollbackを実行']);
section(s,'修正後の確認',['ASUS 2台・Pixel 2台で、旧記録保持と収録再開を確認','強制Dozeの取得停止と、新規GNSS未取得は未解決'],492);
s=slide('RSSIの解析に進む前に','受信記録と、端末自身の位置を対応付ける');
section(s,'必要な記録',['保存RSSI、観測時刻、機体の申告位置','同じ端末の自己位置、測位時刻、OS精度申告'],175);
section(s,'今回の対象',['Androidの324行を元DB・参照デコードと再照合','Pi Bは自己位置が残っていないため、水平距離解析から除外'],390);
note(s,['機体の申告位置は、別の方法で計測した真位置とは区別']);


s=slide('解析に使う記録の絞り込み','時刻差2秒以内、OS精度申告20m以下などで選別','実測記録の集計');chart(s,['Pixel 6 Pro','ASUS-1','ASUS-2'],[{name:'解析に使用',values:[105,0,0],fill:C.blue},{name:'保留',values:[27,146,46],fill:'#C5CDD4'}],{ytitle:'保存行数［行］',max:180,stack:true,legend:true,format:'0'});note(s,['OS精度申告／申告水平距離 ≦ 0.25。全324行から105行を使用','条件を満たす105行を固定。残る219行は、このモデルへ入力しない']);


s=slide('RSSIと申告位置のずれを調べる','申告水平距離から予測し、保存RSSIとの差を計算');text(s,'予測RSSI  =  a － 10 nₕ log₁₀(d)',68,190,830,65,32,C.navy,true);table(s,['記号','意味'],[['d','端末位置とRID申告位置の水平距離［m］'],['a・nₕ','学習区間の記録から求める係数'],['R','端末に保存したRSSI［dBm］']], [170,700],285,200);text(s,'スコア S = | R － 予測RSSI |',68,527,830,52,31,C.navy,true);note(s,['Sが閾値τを超えたら警報。閾値以下でも、位置の正しさは未確認'],608);


s=slide('今回の解析条件','同じ105行を時間順に分け、モデルと閾値を固定');table(s,['区間','行数','役割'],[['学習','52','RSSIモデルの係数を計算'],['校正','26','ずれの大きさの95分位から閾値を決定'],['評価','27','固定したモデルと閾値を適用']], [200,130,540],190,260);section(s,'評価条件',['境界10秒除外、同boot・時間順の分割','閾値τ＝5.64358 dB。評価区間に合わせた再調整なし'],490);


s=slide('変更していない記録での警報','まず、申告位置とRSSIを変えずに確認','実測記録の集計');chart(s,['学習\n23 / 52行','校正\n2 / 26行','評価\n13 / 27行'],[{name:'警報割合',values:[100*23/52,100*2/26,100*13/27]}],{ytitle:'警報割合［%］',max:100,format:'0.00'});note(s,['評価27行のうち13行に警報。変更前から警報が多い','独立真値がなく、物理的な誤警報率は未評価']);


s=slide('申告位置だけを50m遠ざけた結果','実測RSSI・係数・閾値を固定し、申告水平距離だけ変更','実測＋合成変更');chart(s,['未改変','50m遠方へ申告変更'],[{name:'元から警報',values:[13,13],fill:C.blue},{name:'新たに警報',values:[0,14],fill:C.pale},{name:'閾値以下',values:[14,0],fill:'#D8DDE2'}],{ytitle:'同じ評価27行の内訳［行］',max:30,stack:true,legend:true,format:'0'});note(s,['新たな警報は14行。残り13行は変更前から警報','変更後の27行は、すべて学習した距離の範囲外']);


s=slide('RSSIも補償した場合','申告変更に加え、モデルに一致する補償dBを合成加算','実測＋合成変更');chart(s,['未改変','申告変更のみ','申告変更＋補償'],[{name:'元から警報',values:[13,13,13],fill:C.blue},{name:'新たに警報',values:[0,14,0],fill:C.pale},{name:'閾値以下',values:[14,0,14],fill:'#D8DDE2'}],{ytitle:'同じ評価27行の内訳［行］',max:30,stack:true,legend:true,format:'0'});note(s,['理想補償で元と同じ判定へ戻る。13行の警報もそのまま残る','モデル既知・補償上限なし。実RF出力や受信欠落は未評価']);


s=slide('この結果をどう読むか','警報が増えたことだけでは、実機の検出性能は分からない');
section(s,'今回分かったこと',['未改変でも警報が多く、現在のモデルには校正の課題','理想的な電力補償では、申告を変えても元のスコアを維持'],170);
section(s,'検出性能を評価するために',['申告とは別の真位置・正常／攻撃ラベルが必要','別の飛行・日付の記録で、未改変時の警報を再確認'],390);
note(s,['今回の数値は、固定した記録への警報割合と合成変更の比較']);
s=slide('まとめ');
section(s,'実験記録',['Pi BとAndroid 3台で、対象実機IDの855保存行を確認','Androidの自己位置とRSSIを組み合わせて解析'],145);
section(s,'収録の修正',['容量上限による停止と、AndroidのDB復帰失敗を修正','スキャン・消灯試験で、取得頻度が制限される条件を確認'],330);
section(s,'RSSIの評価',['未改変でも13/27行に警報。現モデルの利用は見送り','申告・計算の一致だけでは、機体やセンサの真正性は未確認'],515);
s=slide('今後の実験','次は、記録を比較できる条件を揃える');
table(s,['対象','実施すること'],[['時刻・位置','時計の対応、高度基準、独立した機体位置を記録'],['端末比較','PiとAndroidを同地点で測定し、設定・期間を統一'],['継続収録','自然Doze・電池・長時間・電源断後の復帰を確認'],['RSSI評価','独立した正常記録で校正し、申告変更を再評価']], [235,635],180,350);
note(s,['実ドローンの新規実験は、利用できる時期にIssue #99で実施','ZKPへ接続する前に、入力と判定で保証する範囲を確定']);


s=slide('参考文献・関連資料');
text(s,'GhostBuster',48,140,870,40,27,C.blue,true);
text(s,'M. Keizer, S. Sciancalepore, G. Oligeri\n“GhostBuster: Detecting Misbehaving Remote ID-Enabled Drones”\nIEEE CCNC, 2024\nDOI: 10.1109/CCNC51664.2024.10454860',48,193,870,170,22);
text(s,'Android Developers',48,396,870,40,27,C.blue,true);
text(s,'Wi-Fi scanning overview\ndeveloper.android.com/develop/connectivity/wifi/wifi-scan\nOptimize for Doze and App Standby\ndeveloper.android.com/training/monitoring-device-state/doze-standby',48,446,870,155,22);


s=slide('参考資料・再現手順');table(s,['資料','掲載内容'],[['Week29 総覧','実施内容・報告01〜37への索引'],['報告31〜34','Pi busy、Android背景収録・権限復帰'],['報告35','元DB照合、固定105行と評価可能範囲'],['報告36','モデル診断、合成条件、採用条件の感度'],['報告37','説明図、CSV/JSONと表示検証']], [260,610],155,350);text(s,'GitHub：SMRI2170/zkp-m1-v2\nweek29/ と week29/results/research-review-20261119-f/',48,550,870,80,22,C.blue);
// Supplemental pages A1–A8.


s=slide('補足：機材と確認段階','導入台数と、機能別に試験した端末を区別');table(s,['機材','今回の確認'],[['Pi A','保存停止の調査、保存処理の修正'],['Pi B・E・F','旧記録保持、修正適用、OS再起動・短時間監視'],['Pi C・D','修正適用、4時間待機監視、制御RF試験'],['ASUS_Z017DA 2台','Android 7 / API24、背景収録・権限復帰'],['Pixel 6 Pro／Pixel 8','API31／端末申告API37、v0.15更新・権限復帰']], [280,590],180,370);note(s,['全端末で自然Doze・長時間・GNSS取得を確認した意味ではない']);


s=slide('補足：取得間隔の比較','保存内容が変化する間隔の中央値','実測記録の集計');chart(s,['Pi B','Pixel 6 Pro','ASUS-1','ASUS-2'],[{name:'内容変化の間隔',values:[1.59,8.52,19.69,32.44]}],{ytitle:'内容変化の間隔［秒］',max:40});note(s,['端末の位置・期間・OS・設定が異なる記録','端末間の性能比較には、同地点・同時刻の測定が必要']);


s=slide('補足：4時間監視の詳細','対象RID待ちの状態で、有限時間の監視を実行','待機監視');table(s,['項目','C','D'],[['監視時間','4時間','4時間'],['監視サンプル','437','452'],['health FAULT','0','0'],['ホスト空きRAM最小','527.5 MiB','3364.3 MiB'],['対象RID記録','0','0']], [350,260,260],180,370);note(s,['全サンプルがWAITING。実飛行中の収録成功を示す試験ではない','サービス単体のメモリ使用量は未取得']);


s=slide('補足：待ち時間とbusy','全チャネル／既知周波数のみ、各20秒×2巡','制御RF試験');chart(s,['0.5秒','1秒','2秒','5秒'],[{name:'全チャネル',values:[100*19/26,100*20/30,50,0],fill:C.blue},{name:'既知周波数のみ',values:[0,0,0,0],fill:C.pale}],{ytitle:'busy／要求［%］',max:100,legend:true,format:'0.0'});note(s,['全域の分母26/30/20/8、既知周波数79/40/20/8','適応0.25秒は6/90＝6.7%。busyだけで通常設定を決めない']);


s=slide('補足：SQLite保全と復帰','旧記録を消さず、復帰失敗の原因を修正');section(s,'中断時に起きたこと',['権限取消しで書込みが中断し、hot journalが残存','読み取り専用での再オープンに失敗し、受信開始へ進めず'],160);section(s,'修正と確認',['元ファイルとjournalを保全し、通常のSQLite復旧を実行','integrity確認、旧観測・測位の保持、新セッションの再開'],380);note(s,['端末ごとに隔離fixture試験と実際の権限復帰を区別して記録']);


s=slide('補足：時刻・自己位置・高度','APIの値と、物理的な真値の違い');table(s,['情報','用途と限界'],[['boot・monotonic','同端末内の順序・対応に使用'],['端末間の暦時計','独立した基準との対応が未確定'],['OS精度申告','探索的品質条件。真の誤差上限ではない'],['RID高度','高度基準の独立確認が不足'],['GNSSとnetwork fix','区別して保存。今回の追加試験ではGNSS新規0件']], [270,600],180,385);


s=slide('補足：残差の分布','符号付き残差（保存RSSI−予測RSSI）を区間別に比較');table(s,['区間','残差中央値［dB］','第1〜第3四分位［dB］'],[['学習','−0.235','−5.420 〜 5.256'],['校正','1.267','−0.409 〜 3.238'],['評価','3.349','0.839 〜 13.697']], [180,280,410],185,230);section(s,'読み取れること',['評価13警報のうち、少なくとも9行は学習距離域内','校正区間の代表性が課題。遮蔽・姿勢・電力などの原因は未特定'],465);


s=slide('補足：申告距離に依存する選別','OS精度申告／申告水平距離 ≦ 0.25 の感度','実測＋合成変更');chart(s,['変更なし','20m遠方','50m遠方','100m遠方'],[{name:'条件を通る行',values:[105,248,322,324]}],{ytitle:'探索条件を通る行数［行］',max:350,format:'0'});note(s,['同じ測位記録でも、遠方申告によって条件を通りやすくなる','精度や検出率の改善ではない。モデル評価は元の105行に固定']);


s=slide('補足：電力補償の数値例','別の位置申告でも、同じモデルに整合する例','完全合成の説明例');chart(s,['元の申告10m','40mへ申告変更','申告変更＋補償'],[{name:'スコア',values:[0,12.041199826559248,0],fill:C.blue},{name:'閾値3dB',values:[3,3,3],fill:'#C5CDD4'}],{ytitle:'スコアと閾値［dB］',max:15,format:'0.00',legend:true});note(s,['例：a＝−40、n＝2、保存RSSI＝−60dBm。実測由来の係数とは別','−12.04dBの合成補償でスコア0。位置を正しいと確認した意味ではない']);


s=slide('補足：同じ内容と同じ送信','内容一致だけでは、局間差に使える対応は確定しない','説明用の架空例');table(s,['送信の例','保存された内容','残る可能性'],[['送信①','A','局Xが受信'],['送信②','A','局Yが別の再送を受信'],['キャッシュの再保存','A','新しい電波を受けず保存']], [250,220,400],195,270);section(s,'今回の監査結果',['共通内容の候補は存在。同一物理送信の確定は0件','未知送信電力を局間差で除去できたとは主張しない'],516);


s=slide('補足：GhostBusterとの対応','原著の前提と、今回の代理評価を区別');table(s,['項目','整理'],[['同期・協調','原著は受信局間の同期・協調を前提にしない'],['送信電力','原著も送信電力の操作を議論'],['今回の評価','水平申告距離と保存RSSIを用いた固定モデル'],['厳格な研究条件','別パケット・毎送信任意電力・1送信1RSSI'],['再現の範囲','原著の完全再現や、全配置での検出保証ではない']], [230,640],180,385);


s=slide('補足：連続観測の時間変動','評価27行を、5つの記述ブロックに集約','実測記録の集計');chart(s,['B1\n0/5','B2\n3/6','B3\n3/5','B4\n5/6','B5\n2/5'],[{name:'警報割合',values:[0,50,60,100*5/6,40]}],{ytitle:'警報割合［%］',max:100,format:'0.0'});note(s,['合計13/27。30秒区分を基に、小さい区分を隣接へ統合','独立した5飛行ではなく、独立試行の信頼区間も算出しない']);


s=slide('補足：再現と検証','固定条件・公開集計と、非公開の元記録を分離');section(s,'公開するもの',['解析・試験コード、匿名集計CSV/JSON、説明図','採用105行・分割52/26/27・閾値・合成81条件を固定'],155);section(s,'保全するもの',['元DB・座標・ID・個票は非公開のcapturesへ保持','入力hash、実行ログ、失敗・未実行の理由を記録'],365);text(s,'公開集計の検証\npython3 week29/scripts/validate_field_review.py\n  --results week29/results/research-review-20261119-f',49,566,860,90,20,C.blue);



const out=path.join(BUILD,'candidate-base.pptx');await (await PresentationFile.exportPptx(P)).save(out);
await fs.writeFile(path.join(BUILD,'deck-manifest.json'),JSON.stringify({titles,chartOwners,tableOwners,font:FONT,slideSize:[960,720],sourceReports:'week29/01–37',sourceResults:'week29/results/research-review-20261119-f',referencePlacement:'after future work, before supplement',notes:false},null,2));
console.log(JSON.stringify({output:out,slides:titles.length,nativeCharts:chartOwners.length,nativeTables:tableOwners.length}));
