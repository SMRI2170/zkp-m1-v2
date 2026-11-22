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
// 1–5: purpose and terms.
s=slide('実機Remote IDの収録・品質監査');
text(s,'RSSIによる位置申告の検査',65,200,835,75,40,C.navy,true);
text(s,'Android・Raspberry Piの収録改善と\n実測記録への合成位置変更による評価',65,310,830,100,27);
text(s,'第29回  研究進捗',65,528,800,45,24,C.blue,true);
s=slide('目次');table(s,['項目','内容'],[['実験記録','取得データと収録上の課題'],['収録改善','Piの保存・スキャン、Androidの継続収録'],['品質監査','解析に使える記録と不足情報'],['RSSI評価','未改変・申告変更・電力補償の比較'],['まとめ・今後','今回の判断と追加評価']], [230,640],155,410);
s=slide('今回の作業内容','回収した記録の解析と、収録を続けるための修正');table(s,['区分','実施内容'],[['データ回収','Pi・Androidの記録保全、実機IDの再解析'],['Pi','保存上限への対応、再起動確認、スキャン比較'],['Android','SQLite保全、背景収録、権限復帰の修正'],['品質監査','元DBとの照合、時刻・自己位置・用途の確認'],['RSSI評価','モデルの失敗診断、合成変更、説明図の作成']], [190,680],180,390);note(s,['実験記録の解析と、後日の動作試験を分けて整理']);
s=slide('研究の目的と今回の範囲','未知の送信電力の下で、位置申告の矛盾を調べる');seq(s,['収録','品質監査','位置申告の検査'],['RSSI・時刻・生情報\n端末自身の位置','保存内容と元DBの照合\n利用できる条件の確認','モデルと観測の比較\n警報と限界の評価']);note(s,['今回は実験記録の整理と、水平距離を用いた探索的な評価','独立した真位置に対する位置偽装検出率は未評価']);
s=slide('受信記録・申告位置・真位置','位置の意味を分けて扱う');columns(s,['受信記録','申告位置','独立した真位置'],['端末に保存した\nRSSI・時刻・生情報','Remote IDに\n含まれている座標','申告とは別の方法で\n計測した機体位置']);note(s,['今回の軌跡はRemote IDの申告軌跡','受信した座標だけでは、実際の位置を検証できない']);
// 6–16: collection and repairs.
s=slide('実験機材と取得経路','実機の記録と、後日の動作試験を分ける');table(s,['機材','役割・今回の対象'],[['Pi A','搭載側の受信・予備送信・センサ記録'],['Pi B〜F','地上側の受信・保存、起動時収録'],['Pixel 6 Pro／Pixel 8','Android受信・自己位置・SQLite保存'],['ASUS 2台','Android受信・保存、背景収録・復帰試験'],['後日の制御RF試験','Pi Dが研究用IDを送信、CまたはAndroidが受信']], [265,605],180,390);note(s,['距離・向き・時刻を統制した端末間性能比較とは別']);
s=slide('実機実験と追加試験の進め方','実機の観測記録を回収し、取得・保存の問題を別試験で検証');table(s,['段階','方法'],[['実機の観測','11月16日14〜18時頃との申告。Pi・Androidで収録'],['データ回収','JSONL・SQLiteを保全し、実機IDを指定して再解析'],['Piの追加試験','Dから研究用Beaconを送信し、Cで20秒ずつ比較'],['Androidの追加試験','Pi Beacon受信下で表示・消灯・強制Dozeを比較']], [245,625],180,350);note(s,['実験時のノード間距離・高さ・移動経路は、現記録では未確定','端末間時計も未確定。申告された時間帯だけで記録を切り出さない']);
s=slide('保存したデータ','後から解析できるよう、生情報と付随情報を保持');table(s,['取得項目','内容・解析での使い道'],[['生の受信情報','Vendor IE・Message Pack。未分類行の再解析'],['RSSI・周波数','保存時の受信強度とチャネル情報'],['時刻','観測・保存時刻、boot・単調時刻による順序確認'],['機体の申告情報','RIDのID・座標・高度等。解釈できた項目を利用'],['Androidの自己位置','位置・測位時刻・provider・OS精度申告']], [255,615],180,375);note(s,['Androidの対象324行には、対応する自己位置の記録あり','Pi Bは自己位置の記録がなく、今回の水平距離解析から除外']);
s=slide('取得データから調べること','収録状態を確認してから、位置申告の検査へ進む');table(s,['調べたいこと','使うデータ・分析'],[['どの間隔で新しい内容が取れたか','保存時刻・観測キー・内容反復を分離'],['申告距離とRSSIに関係があるか','Android自己位置とRID申告位置の水平距離'],['申告位置の変更に反応するか','実測RSSIを固定し、申告だけを合成変更'],['電力操作で判定が変わるか','同じ記録へ補償dBを合成加算して対比較']], [390,480],180,350);note(s,['まず未改変記録の警報を確認し、変更後の警報と区別','独立した真位置がないため、実環境の検出率は次の実験で評価']);
s=slide('回収した実機IDの記録','固定した参照デコーダでオフライン解析','実測記録の集計');table(s,['端末','対象IDの保存行','今回の用途'],[['Pi B','531','受信間隔・内容反復の解析'],['Pixel 6 Pro','132','自己位置対応・RSSI解析'],['ASUS-1','146','自己位置・採用条件の確認'],['ASUS-2','46','自己位置・採用条件の確認'],['Pixel 8','0','指定した実機IDの解析対象なし']], [270,210,390],180,375);note(s,['Pixel 8の0行は、全電波未受信や受信率0%を意味しない']);
s=slide('保存行数と新しい観測内容','同じ内容を保存した回数と、新しい内容の数を分ける','説明用の架空例');table(s,['保存時刻','内容','読み方'],[['0秒','A','最初の内容'],['1秒','A','同じ内容をもう一度保存'],['2秒','B','内容が変化']], [180,170,520],190,255);section(s,'この例で数えられること',['保存3行、内容2種類','再送・キャッシュ・別の物理送信の区別は未確定'],490);
s=slide('取得間隔の記述統計','保存内容が変化する間隔の中央値','実測記録の集計');chart(s,['Pi B','Pixel 6 Pro','ASUS-1','ASUS-2'],[{name:'内容変化の間隔',values:[1.59,8.52,19.69,32.44]}],{ytitle:'内容変化の間隔［秒］',max:40});note(s,['端末の位置・期間・OS・設定が異なる記録','端末間の性能比較には、同地点・同時刻の測定が必要']);
s=slide('Aノードの記録停止','保存履歴と、上限到達後の明示停止を照合','実測記録の監査');table(s,['記録','設定上限','上限到達から停止まで'],[['センサ記録','192 MiB','約1.65秒'],['予備送信記録','128 MiB','約5.01秒']], [270,220,380],192,200);section(s,'停止原因として確認したこと',['累積保存量と容量上限による停止の対応','低電圧警告も併存。全ての無記録区間を容量停止では説明しない'],448);
s=slide('保存処理の修正','旧記録を保持し、停止理由を残す');seq(s,['セッション分離','容量・RAM監視','理由付き停止'],['役割別・起動別に保存\n旧記録と新記録を分離','保存予算と空き容量\nメモリ余力を確認','上限や失敗を明示\n診断情報を保存']);note(s,['B〜Fへ適用し、旧記録の保持とOS再起動後の復帰を確認','物理電源断や実飛行中の高負荷は別の評価']);
s=slide('C・Dの4時間監視','対象RID待ちの状態で、有限時間の監視を実行','待機監視');table(s,['項目','C','D'],[['監視時間','4時間','4時間'],['監視サンプル','437','452'],['health FAULT','0','0'],['ホスト空きRAM最小','527.5 MiB','3364.3 MiB'],['対象RID記録','0','0']], [350,260,260],180,370);note(s,['全サンプルがWAITING。実飛行中の収録成功を示す試験ではない','サービス単体のメモリ使用量は未取得']);
s=slide('Piのスキャン比較条件','同じC/D構成で、周波数指定と待ち時間を変更','制御RF試験');table(s,['条件','設定'],[['送受信','D：研究用Beacon送信、C：受信'],['内容更新','送信内容のカウンタ（Vendor IE）を約1秒更新'],['比較方法','全チャネル／既知周波数のみ／適応'],['要求後の待ち時間','0.5・1・2・5秒、適応0.25秒'],['試験区間','各20秒、順序反転2巡、受動対照を含む20区間']], [255,615],180,370);note(s,['実ドローンの試験ではなく、Locationなしの研究用送信']);
s=slide('周波数指定とbusyの発生','要求後の待ち時間0.5秒の条件を比較','制御RF試験');chart(s,['全チャネル\n19 / 26要求','既知周波数のみ\n0 / 79要求'],[{name:'busy割合',values:[100*19/26,0]}],{ytitle:'busy／スキャン要求［%］',max:100,format:'0.0'});note(s,['全域スキャン中の次要求で、busy（受付失敗）が発生','未知周波数の探索性能は、今回の比較対象外']);
s=slide('Androidの消灯・強制Doze試験','ASUS 2台、各20秒。Doze：OSの省電力状態','制御RF試験');chart(s,['画面表示','ホーム','消灯','強制Doze'],[{name:'ASUS-1',values:[4,4,4,1],fill:C.blue},{name:'ASUS-2',values:[8,7,6,2],fill:C.pale}],{ytitle:'対象Vendor内容の種類数',max:10,format:'0',legend:true});note(s,['研究用Pi Beaconを受信。消灯中もID・RSSIを保存','強制Dozeでは最初の5秒以降、新しい対象観測が0件']);
s=slide('権限取消し後の保存復旧','SQLite中断時のjournalを保全して復旧');seq(s,['取消し・中断','保全・復旧','収録再開'],['位置権限取消しで\n書込み中の処理が中断','元ファイルを退避\nSQLite整合性を検査','再許可で記録再開\n旧観測・測位を保持']);section(s,'確認した範囲',['ASUS 2台・Pixel 2台で更新と権限復帰を確認','新規GNSS（衛星測位）は0件。受信再開と位置取得を別評価'],496);
s=slide('発生した問題と対応','修正した不具合と、原因を切り分けた制限');table(s,['症状','対応','確認結果'],[['容量上限で停止','役割・起動別に保存先を分離','B〜Fへ適用\n旧記録・再起動復帰を確認'],['対象IDが未分類','生情報を参照デコーダで再解析','対象855行を抽出\n本番受理成功とは別'],['SQLiteの復帰失敗','中断DB・journalを保全し復旧','4台で旧記録保持と再開'],['スキャンbusy','全域・既知周波数を比較','既知周波数0/79要求\n通常設定は維持']], [205,325,340],180,375,21);note(s,['強制Dozeの取得停止、GNSS未取得、低電圧の影響は未解決','動作することと、必要な頻度・精度で取得できることを分けて評価']);
// 17–21: input audit.
s=slide('RSSI解析前の品質監査','モデルを適用する前に、元の保存内容を照合');seq(s,['元データ','照合','用途の判定'],['元DB 4件\n参照デコード\n自己位置の保存記録','RSSI・申告位置\nboot・単調時刻\n端末自己位置','水平解析に使用\n情報不足なら保留\n評価範囲を限定']);note(s,['元ファイルを保持し、Androidの対象324行を再照合']);
s=slide('解析に使った105行と保留219行','時刻差2秒以内、OS精度申告20m以下などで選別','実測記録の集計');chart(s,['Pixel 6 Pro','ASUS-1','ASUS-2'],[{name:'解析に使用',values:[105,0,0],fill:C.blue},{name:'保留',values:[27,146,46],fill:'#C5CDD4'}],{ytitle:'保存行数［行］',max:180,stack:true,legend:true,format:'0'});note(s,['OS精度申告／申告水平距離 ≦ 0.25。全324行から105行を使用','保留は探索条件の不一致。位置偽装や未受信の判定ではない']);
s=slide('今回のデータで評価できる範囲','不足する情報がある用途は、結果を出さず保留');table(s,['用途','今回の扱い・不足情報'],[['申告水平距離とRSSI','同端末・固定105行の探索的評価'],['物理的な検出率・誤警報率','独立した真位置と正常／攻撃ラベルが不足'],['三次元の実位置','独立した高度・位置の基準が不足'],['局間RSSI差','同一物理送信の確定対応が不足'],['受信率・独立runの信頼区間','送信総数・独立runのラベルが不足']], [310,560],180,385);
s=slide('同じ内容と同じ物理送信','内容一致だけでは、局間差に使える対応は確定しない','説明用の架空例');table(s,['送信の例','保存された内容','残る可能性'],[['送信①','A','局Xが受信'],['送信②','A','局Yが別の再送を受信'],['キャッシュの再保存','A','新しい電波を受けず保存']], [250,220,400],195,270);section(s,'今回の監査結果',['共通内容の候補は存在。同一物理送信の確定は0件','未知送信電力を局間差で除去できたとは主張しない'],516);
s=slide('申告軌跡の可視化','Remote IDの座標を時系列で表示');section(s,'表示できたこと',['機体の申告軌跡、Android自身の移動','RSSIによる色分け、上面・側面、記録の空白'],185);section(s,'実位置として扱えない点',['RSSIから機体の三次元位置を推定した結果ではない','独立真位置・高度基準・端末間時計の確認が必要'],412);text(s,'公開資料には実座標を含めず、匿名集計を使用',51,624,860,35,21,C.muted);
// 22–30: model and synthetic cases.
s=slide('RSSIモデルと警報の意味','申告位置から予測したRSSIと、保存RSSIの差を比較');text(s,'予測RSSI  =  a − 10 nₕ log₁₀(d)',68,190,830,65,32,C.navy,true);table(s,['記号','意味'],[['d','端末位置とRID申告位置の水平距離［m］'],['a・nₕ','今回の記録から求めた代理モデルの係数'],['R','端末に保存したRSSI［dBm］']], [170,700],285,200);text(s,'スコア S = | R − 予測RSSI |',68,527,830,52,31,C.navy,true);note(s,['Sが閾値τを超えた場合に警報。小さいSは位置の正しさを保証しない'],608);
s=slide('学習・校正・評価の分割','同じ105行を時間順に分け、モデルと閾値を固定');table(s,['区間','行数','役割'],[['学習','52','代理モデルの係数を計算'],['校正','26','絶対残差95分位から閾値を決定'],['評価','27','固定したモデルと閾値を適用']], [200,130,540],190,260);section(s,'評価条件',['境界10秒除外、同boot・時間順の分割','閾値τ＝5.64358 dB。評価を見て調整しない'],490);
s=slide('未改変記録の警報割合','位置申告やRSSIを変えていない記録で評価','実測記録の集計');chart(s,['学習\n23 / 52行','校正\n2 / 26行','評価\n13 / 27行'],[{name:'警報割合',values:[100*23/52,100*2/26,100*13/27]}],{ytitle:'警報割合［%］',max:100,format:'0.00'});note(s,['未改変でも13/27行に警報。位置偽装判定への利用は見送り','独立真値がなく、物理的な誤警報率は未評価']);
s=slide('警報増加の診断','符号付き残差（保存RSSI−予測RSSI）を区間別に比較');table(s,['区間','残差中央値［dB］','第1〜第3四分位［dB］'],[['学習','−0.235','−5.420 〜 5.256'],['校正','1.267','−0.409 〜 3.238'],['評価','3.349','0.839 〜 13.697']], [180,280,410],185,230);section(s,'読み取れること',['評価13警報のうち、少なくとも9行は学習距離域内','校正区間の代表性が課題。遮蔽・姿勢・電力などの原因は未特定'],465);
s=slide('位置申告だけを変える条件','保存RSSIを維持し、申告水平距離を50m遠方へ変更','実測＋合成変更');columns(s,['維持する値','合成的に変える値'],['同じ27行の保存RSSI\n同じモデル係数\n同じ閾値','端末からの申告水平距離\nd を d＋50m へ変更']);note(s,['機体を実際に移動させた試験ではない','受信電力・欠測・アンテナ姿勢の変化は再現していない']);
s=slide('27行すべて警報となった内訳','元からの警報と、合成変更で増えた警報を分ける','実測＋合成変更');chart(s,['未改変','50m遠方へ申告変更'],[{name:'元から警報',values:[13,13],fill:C.blue},{name:'新たに警報',values:[0,14],fill:C.pale},{name:'閾値以下',values:[14,0],fill:'#D8DDE2'}],{ytitle:'同じ評価27行の内訳［行］',max:30,stack:true,legend:true,format:'0'});note(s,['27/27を実機の検出率100%とは評価しない','変更後の27行は、すべて学習した距離の範囲外']);
s=slide('電力補償を加えた条件','モデルと一致する補償値を、保存RSSIへ合成加算','実測＋合成変更');chart(s,['未改変','申告変更のみ','申告変更＋補償'],[{name:'元から警報',values:[13,13,13],fill:C.blue},{name:'新たに警報',values:[0,14,0],fill:C.pale},{name:'閾値以下',values:[14,0,14],fill:'#D8DDE2'}],{ytitle:'同じ評価27行の内訳［行］',max:30,stack:true,legend:true,format:'0'});note(s,['理想補償では元のスコアに一致。元の13警報も残る','モデル既知・補償上限なし。実RF出力や受信欠落は未評価']);
s=slide('小さいスコアと位置の正しさ','別の位置申告でも、同じモデルに整合する例','完全合成の説明例');chart(s,['元の申告10m','40mへ申告変更','申告変更＋補償'],[{name:'スコア',values:[0,12.041199826559248,0],fill:C.blue},{name:'閾値3dB',values:[3,3,3],fill:'#C5CDD4'}],{ytitle:'スコアと閾値［dB］',max:15,format:'0.00',legend:true});note(s,['例：a＝−40、n＝2、保存RSSI＝−60dBm。実測由来の係数とは別','−12.04dBの合成補償でスコア0。位置を正しいと確認した意味ではない']);
s=slide('申告距離に依存する採用条件','OS精度申告／申告水平距離 ≦ 0.25 の感度','実測＋合成変更');chart(s,['変更なし','20m遠方','50m遠方','100m遠方'],[{name:'条件を通る行',values:[105,248,322,324]}],{ytitle:'探索条件を通る行数［行］',max:350,format:'0'});note(s,['同じ測位記録でも、遠方申告によって条件を通りやすくなる','精度や検出率の改善ではない。モデル評価は元の105行に固定']);
s=slide('まとめ');section(s,'収録基盤',['停止原因を記録から確認し、保存・権限復帰を修正','Pi・Androidの動作試験と、実飛行の性能評価を分離'],135);section(s,'実測記録の評価',['品質監査後の105行を固定し、評価27行中13行に警報','未改変記録にも警報が多く、位置偽装判定への利用は見送り'],330);section(s,'今回の限界',['真位置・同一物理送信・高度基準が不足','申告値や観測者署名だけでは、機体やセンサの真正性は保証しない'],535);
s=slide('今後の評価','必要な情報を揃えてから、検出性能を再評価');table(s,['対象','次に必要なこと'],[['データ品質','独立時計・高度基準、申告値に依存しない採用条件'],['単局RSSIモデル','独立した正常真値・runで警報を評価'],['追加観測','同一物理送信の対応、局間偏差と配置の確認'],['収録の継続性','自然Doze・電池・長時間・物理電源断の評価'],['実ドローン','独立真値と配置を記録した新規実験。後日#99で実施']], [245,625],180,380);note(s,['ZKPへの接続は、証明する判定と入力条件を確定した後に検討']);
// References follow future work, never slide-bottom citations.
s=slide('参考文献・関連資料');
text(s,'GhostBuster',48,140,870,40,27,C.blue,true);
text(s,'M. Keizer, S. Sciancalepore, G. Oligeri\n“GhostBuster: Detecting Misbehaving Remote ID-Enabled Drones”\nIEEE CCNC, 2024\nDOI: 10.1109/CCNC51664.2024.10454860',48,193,870,170,22);
text(s,'Android Developers',48,396,870,40,27,C.blue,true);
text(s,'Wi-Fi scanning overview\ndeveloper.android.com/develop/connectivity/wifi/wifi-scan\nOptimize for Doze and App Standby\ndeveloper.android.com/training/monitoring-device-state/doze-standby',48,446,870,155,22);
s=slide('参考資料・再現手順');table(s,['資料','掲載内容'],[['Week29 総覧','実施内容・報告01〜37への索引'],['報告31〜34','Pi busy、Android背景収録・権限復帰'],['報告35','元DB照合、固定105行と評価可能範囲'],['報告36','モデル診断、合成条件、採用条件の感度'],['報告37','説明図、CSV/JSONと表示検証']], [260,610],155,350);text(s,'GitHub：SMRI2170/zkp-m1-v2\nweek29/ と week29/results/research-review-20261119-f/',48,550,870,80,22,C.blue);
// Supplemental pages A1–A8.
s=slide('補足：機材と確認段階','導入台数と、機能別に試験した端末を区別');table(s,['機材','今回の確認'],[['Pi A','保存停止の調査、保存処理の修正'],['Pi B・E・F','旧記録保持、修正適用、OS再起動・短時間監視'],['Pi C・D','修正適用、4時間待機監視、制御RF試験'],['ASUS_Z017DA 2台','Android 7 / API24、背景収録・権限復帰'],['Pixel 6 Pro／Pixel 8','API31／端末申告API37、v0.15更新・権限復帰']], [280,590],180,370);note(s,['全端末で自然Doze・長時間・GNSS取得を確認した意味ではない']);
s=slide('補足：保存上限の扱い','上限と停止理由を、実際の保存履歴と対応付ける');table(s,['対象','記録・設定'],[['センサ','上限192 MiB、到達後約1.65秒で停止'],['予備送信','上限128 MiB、到達後約5.01秒で停止'],['受信側の既往設定','256 MiBからreserve 64 MiBを除く予算'],['修正','役割・起動別の保存、旧記録保持、容量監視']], [280,590],180,300);note(s,['低電圧警告や無記録区間の原因は、容量だけで断定しない']);
s=slide('補足：待ち時間とbusy','全チャネル／既知周波数のみ、各20秒×2巡','制御RF試験');chart(s,['0.5秒','1秒','2秒','5秒'],[{name:'全チャネル',values:[100*19/26,100*20/30,50,0],fill:C.blue},{name:'既知周波数のみ',values:[0,0,0,0],fill:C.pale}],{ytitle:'busy／要求［%］',max:100,legend:true,format:'0.0'});note(s,['全域の分母26/30/20/8、既知周波数79/40/20/8','適応0.25秒は6/90＝6.7%。busyだけで通常設定を決めない']);
s=slide('補足：SQLite保全と復帰','旧記録を消さず、復帰失敗の原因を修正');section(s,'中断時に起きたこと',['権限取消しで書込みが中断し、hot journalが残存','読み取り専用での再オープンに失敗し、受信開始へ進めず'],160);section(s,'修正と確認',['元ファイルとjournalを保全し、通常のSQLite復旧を実行','integrity確認、旧観測・測位の保持、新セッションの再開'],380);note(s,['端末ごとに隔離fixture試験と実際の権限復帰を区別して記録']);
s=slide('補足：時刻・自己位置・高度','APIの値と、物理的な真値の違い');table(s,['情報','用途と限界'],[['boot・monotonic','同端末内の順序・対応に使用'],['端末間の暦時計','独立した基準との対応が未確定'],['OS精度申告','探索的品質条件。真の誤差上限ではない'],['RID高度','高度基準の独立確認が不足'],['GNSSとnetwork fix','区別して保存。今回の追加試験ではGNSS新規0件']], [270,600],180,385);
s=slide('補足：連続観測の時間変動','評価27行を、5つの記述ブロックに集約','実測記録の集計');chart(s,['B1\n0/5','B2\n3/6','B3\n3/5','B4\n5/6','B5\n2/5'],[{name:'警報割合',values:[0,50,60,100*5/6,40]}],{ytitle:'警報割合［%］',max:100,format:'0.0'});note(s,['合計13/27。30秒区分を基に、小さい区分を隣接へ統合','独立した5飛行ではなく、独立試行の信頼区間も算出しない']);
s=slide('補足：GhostBusterとの対応','原著の前提と、今回の代理評価を区別');table(s,['項目','整理'],[['同期・協調','原著は受信局間の同期・協調を前提にしない'],['送信電力','原著も送信電力の操作を議論'],['今回の評価','水平申告距離と保存RSSIを用いた固定モデル'],['厳格な研究条件','別パケット・毎送信任意電力・1送信1RSSI'],['再現の範囲','原著の完全再現や、全配置での検出保証ではない']], [230,640],180,385);
s=slide('補足：再現と検証','固定条件・公開集計と、非公開の元記録を分離');section(s,'公開するもの',['解析・試験コード、匿名集計CSV/JSON、説明図','採用105行・分割52/26/27・閾値・合成81条件を固定'],155);section(s,'保全するもの',['元DB・座標・ID・個票は非公開のcapturesへ保持','入力hash、実行ログ、失敗・未実行の理由を記録'],365);text(s,'公開集計の検証\npython3 week29/scripts/validate_field_review.py\n  --results week29/results/research-review-20261119-f',49,566,860,90,20,C.blue);

const out=path.join(BUILD,'candidate-base.pptx');await (await PresentationFile.exportPptx(P)).save(out);
await fs.writeFile(path.join(BUILD,'deck-manifest.json'),JSON.stringify({titles,chartOwners,tableOwners,font:FONT,slideSize:[960,720],sourceReports:'week29/01–37',sourceResults:'week29/results/research-review-20261119-f',referencePlacement:'after future work, before supplement',notes:false},null,2));
console.log(JSON.stringify({output:out,slides:titles.length,nativeCharts:chartOwners.length,nativeTables:tableOwners.length}));
