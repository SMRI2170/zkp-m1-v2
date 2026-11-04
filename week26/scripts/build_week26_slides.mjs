import fs from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
const ROOT=process.cwd();
const CACHE=path.join(ROOT,'.cache/week26-slides');
const RUNTIME='/Users/shivio/.cache/codex-runtimes/codex-primary-runtime/dependencies';
const SKILL='/Users/shivio/.codex/plugins/cache/openai-primary-runtime/presentations/26.1022.11436/skills/presentations';
const req=createRequire(path.join(RUNTIME,'node/node_modules/__runtime__.cjs'));
const {PresentationFile,FileBlob}=await import(pathToFileURL(req.resolve('@oai/artifact-tool')).href);
const {makeNativeBulletParagraphs,applyPresentationChartFont}=await import(pathToFileURL(path.join(SKILL,'container_tools/artifact_tool_utils.mjs')).href);
const D=JSON.parse(await fs.readFile(path.join(CACHE,'slide-data.json'),'utf8'));
const REF=path.join(ROOT,'week24/slides/references/第24回進捗_HyperNovaとNova_環境構築_実装.pptx');
const F='Hiragino Kaku Gothic ProN W3', H='Hiragino Kaku Gothic ProN W6';
const C={black:'#282629',blue:'#2F64A1',head:'#2B5581',light:'#EDF3F7',red:'#E02B2B',gray:'#7B8591',pale:'#BDC5CF',green:'#00867C'};
const E='mac-event-scenarios-20261101';
const L='mac-public-lora-20261101';
const S='mac-sensitivity-20261101-v2';
const R='mac-robustness-20261101';
const src=(folder,file,scope='合成10 seed')=>`出典：${folder} / ${file}（${scope}）`;
let P, template, coverTemplate, log=[];
function shape(sl,g,x,y,w,h,fill='none',stroke='none',sw=0){return sl.shapes.add({geometry:g,position:{left:x,top:y,width:w,height:h},fill,line:{fill:stroke,width:sw,style:'solid'}});}
function txt(sl,t,x,y,w,h,size=24,color=C.black,bold=false,align='left'){
 const o=shape(sl,'textbox',x,y,w,h);o.text=t;o.text.style={typeface:bold?H:F,fontSize:size,bold,color,alignment:align,verticalAlignment:'top',autoFit:'none',wrap:'square',insets:0};return o;
}
function ln(sl,x1,y1,x2,y2,color=C.blue,width=2){const o=shape(sl,'line',Math.min(x1,x2),Math.min(y1,y2),Math.abs(x2-x1)||.1,Math.abs(y2-y1)||.1,'none',color,width);if((x2-x1)*(y2-y1)<0)o.position={...o.position,left:Math.min(x1,x2),top:Math.min(y1,y2),width:Math.abs(x2-x1)||.1,height:Math.abs(y2-y1)||.1,verticalFlip:true};return o;}
function para(sl,items,x=44,y=175,w=870,size=24,marker='•',color=C.black){
 const units=t=>[...t].reduce((a,c)=>a+(c.charCodeAt(0)<128?.55:1),0);
 const rows=items.reduce((a,t)=>a+Math.max(1,Math.ceil(units(t)/((w-42)/size))),0);
 const height=rows*(size*1.38)+items.length*10+12;
 const o=shape(sl,'textbox',x,y,w,height);o.text=makeNativeBulletParagraphs(items,{marginLeftPoints:22.5,hangingPoints:15,spaceAfterPoints:6,bulletCharacter:marker});
 o.text.style={typeface:F,fontSize:size,color,autoFit:'none',insets:0};return height;
}
function section(sl,title,items,y=175,size=24){
 const a=shape(sl,'textbox',44,y,870,34);a.text=makeNativeBulletParagraphs([title],{marginLeftPoints:20,hangingPoints:20,spaceAfterPoints:0,bulletCharacter:'■'});
 a.text.style={typeface:H,fontSize:25,bold:true,color:C.blue,autoFit:'none',insets:0};
 return y+40+para(sl,items,47,y+40,862,size);
}
function note(sl,items,y=543){return para(sl,items,45,y,867,22);}
function footer(sl,t){if(t)txt(sl,t,44,674,840,34,11.8,C.gray);}
function base(title,lead='',source=''){
 const sl=template.duplicate();
 for(const o of sl.shapes.items){
  if(o.name==='TextBox 2'){o.text=title;o.position={left:42,top:10,width:876,height:52};o.text.style={typeface:H,fontSize:34,bold:true,color:C.black,autoFit:'none',insets:0};}
  else if(o.name==='TextBox 4'){o.text=lead;o.position={left:60,top:83,width:850,height:60};o.text.style={typeface:H,fontSize:24,bold:true,color:C.blue,autoFit:'none',insets:0};}
  else if(o.name==='正方形/長方形 6')o.text='';
 }
 sl.speakerNotes.text='';footer(sl,source);log.push({slide:sl,key:null,title,source});return sl;
}
function page(title,lead,groups,source=''){
 const sl=base(title,lead,source);let y=165;
 for(const [head,items] of groups)y=section(sl,head,items,y,24)+18;
 return sl;
}
function table(sl,values,{x=42,y=160,w=876,h,columns}={}){
 h??=Math.min(380,values.length*53);
 const t=sl.tables.add({rows:values.length,columns:values[0].length,left:x,top:y,width:w,height:h,values,columnWidths:columns??Array(values[0].length).fill(w/values[0].length)});
 t.borders.assign({style:'solid',fill:'#B7BEC7',width:.6});
 for(let r=0;r<values.length;r++)for(let c=0;c<values[0].length;c++){
  const cell=t.getCell(r,c);cell.fill=r===0?C.head:(r%2===1?'#FFFFFF':C.light);
  cell.text.style={typeface:r===0?H:F,fontSize:r===0?23:21,color:r===0?'#FFFFFF':C.black,bold:r===0,verticalAlignment:'middle',alignment:'left',insets:{left:10,right:8,top:7,bottom:5},autoFit:'none'};
 }
 return t;
}
function chart(sl,{title,categories,series,type='bar',max=100,min=0,ytitle='警報率（%）',x=60,y=153,w=840,h=370,stack=false,labels=true}){
 const lines=type==='line'||type==='scatter';const o=sl.charts.add(type,{
  position:{left:x,top:y,width:w,height:h},title,titleTextStyle:{fontSize:20,fill:C.black},categories,
  series:series.map((s,i)=>({...s,values:s.values.map(v=>Number(v.toFixed(6))),smooth:false,fill:s.fill??[C.blue,'#8CA7C3',C.red,C.green][i%4],line:lines?{fill:s.fill??[C.blue,'#8CA7C3',C.red,C.green][i%4],width:2}:undefined,marker:lines?{symbol:'circle',size:6}:undefined,dataLabels:stack?{showValue:true,position:'center',numberFormatCode:'0.00',textStyle:{fontSize:17,fill:i===2?C.black:'#FFFFFF'}}:undefined,dataLabelOverrides:stack?s.values.flatMap((v,j)=>v===0?[{idx:j,showValue:false}]:[]):undefined})),
  chartFill:'#FFFFFF',plotAreaFill:'#FFFFFF',hasLegend:series.length>1,
  legend:{position:'bottom',textStyle:{fontSize:17,fill:C.black}},
  barOptions:{direction:'column',grouping:stack?'stacked':'clustered',gapWidth:100,overlap:stack?100:0},
  lineOptions:{smooth:false},
  scatterOptions:type==='scatter'?{style:'lineWithMarkers'}:undefined,
  xAxis:{...(type==='scatter'?{min:0,max:100,majorUnit:20,title:{text:'水平位置の改変量（m）',textStyle:{fontSize:18,fill:C.black}}}:{}),tickLabelPosition:'low',textStyle:{fontSize:18,fill:C.gray},line:{fill:'#C9D0D8',width:1},majorGridlines:null},
  yAxis:{min,max,majorUnit:min<0?1:max<=20?5:max<=50?10:max<=150?20:undefined,crossesAt:min,title:{text:ytitle,textStyle:{fontSize:18,fill:C.black}},numberFormatCode:'0',textStyle:{fontSize:17,fill:C.gray},majorGridlines:{fill:'#E8ECF0',width:.7},line:{fill:'none',width:0}},
  dataLabels:{showValue:labels&&!lines,position:stack?'center':'outEnd',numberFormatCode:'0.0',textStyle:{fontSize:17,fill:C.black}}
 });applyPresentationChartFont(o,{fontFamily:F});for(const se of o.series.items)if(se.dataLabels?.textStyle)se.dataLabels.textStyle.typeface=F;return o;
}
const pc=x=>100*x,fmt=(x,n=1)=>Number(x).toFixed(n);
const ev=(mode,name,sd=2)=>D.events.cases.find(r=>r.mode===mode&&r.case===name&&r.noise_sd_db===sd);
function select(rows,criteria){const r=rows.find(r=>Object.entries(criteria).every(([k,v])=>String(r[k])===String(v)));if(!r)throw Error('Missing source row '+JSON.stringify(criteria));return r;}
function dot(sl,x,y,label,color=C.blue){shape(sl,'ellipse',x-10,y-10,20,20,color);txt(sl,label,x-68,y+17,140,50,22,color,false,'center');}
function scene(sl,kind='scenario'){
 txt(sl,'地上の観測ノード',70,445,800,35,22,C.blue);
 for(const [i,x] of [160,455,760].entries()){shape(sl,'rect',x-17,405,34,28,C.blue);txt(sl,['A','B','C'][i],x-15,408,30,30,22,'#FFFFFF',true,'center');}
 shape(sl,'ellipse',370,205,20,20,C.blue);shape(sl,'ellipse',670,205,20,20,C.red);
 txt(sl,'実際の位置',275,167,210,35,22,C.blue,false,'center');txt(sl,'RIDの申告位置',565,167,230,35,22,C.red,false,'center');
 ln(sl,395,215,660,215,C.red,2);txt(sl,'位置のずれ',475,240,160,35,22,C.red);
 for(const x of [160,455,760])ln(sl,380,235,x,390,'#8CA7C3',1.7);
 if(kind==='terms'){txt(sl,'機体から届く情報\n「ここにいる」という位置の申告',480,500,420,85,23);txt(sl,'ノードが測るRSSI\n受信した電波の強さ',50,500,400,85,25,C.blue);}
 else note(sl,['機体の位置申告と送信電力を信用しない想定','ノードの位置・RSSI報告が適切であることは別の前提'],515);
}
function ambiguity(sl){
 for(const [j,x] of [65,515].entries()){
  txt(sl,j?'近い場所から弱く送信':'遠い場所から強く送信',x,175,380,40,25,C.blue,true);
  dot(sl,x+65,j?330:235,'機体',C.blue);shape(sl,'rect',x+260,400,40,30,C.blue);txt(sl,'受信機',x+220,445,135,38,23);
  ln(sl,x+80,j?340:250,x+275,390,'#8CA7C3',2);
  txt(sl,'同じ受信強度になる場合',x,505,380,45,24,C.red,true);
 }
 note(sl,['RSSIが同じでも、距離と送信電力の組合せは一つに決まらない'],585);
}
function overlap(sl,mode='all'){
 const plans=mode==='all'?Array.from({length:5},()=>[0,1,2,3,4]):mode==='partial'?[[0,1],[1],[1,2,3],[3],[2,4]]:[[0],[1],[2],[3],[4]];
 for(let i=0;i<5;i++)txt(sl,String.fromCharCode(65+i),80,177+i*57,70,35,23,C.blue,true);
 for(let e=0;e<5;e++){
  const x=250+e*135,ns=plans[e],color=ns.length>1?C.blue:C.gray;
  if(ns.length>1)ln(sl,x,190+ns[0]*57,x,190+ns.at(-1)*57,'#91AFC9',3);
  for(const n of ns)shape(sl,'ellipse',x-9,181+n*57,18,18,color);
  txt(sl,'e'+e,x-25,493,70,30,20,C.black);
  txt(sl,ns.length>1?'検査':'保留',x-40,535,90,30,22,color,true,'center');
 }
 txt(sl,'同じ列＝同じ物理送信　／　別の列＝別送信',170,595,700,35,23,C.blue);
}
function timing(sl){
 txt(sl,'同じ送信・提出だけ遅い',44,170,850,34,25,C.blue,true);
 for(let i=0;i<2;i++){
  txt(sl,['A','B'][i],70,230+i*65,40,35,24);ln(sl,140,245+i*65,850,245+i*65,'#CBD2DA',1);
  dot(sl,230,245+i*65,'受信e0');dot(sl,i?740:360,245+i*65,'提出',i?C.red:C.blue);
 }
 txt(sl,'別の送信を受信',44,425,850,35,25,C.blue,true);
 for(let i=0;i<2;i++){
  txt(sl,['A','B'][i],70,485+i*65,40,35,24);ln(sl,140,500+i*65,850,500+i*65,'#CBD2DA',1);
  dot(sl,i?650:230,500+i*65,i?'受信e1':'受信e0',i?C.red:C.blue);
 }
}
function geometry(sl,result=false){
 const cx=result?240:290,cy=340,r=result?125:150;
 shape(sl,'ellipse',cx-r,cy-r,2*r,2*r,'none','#BEC9D6',2);
 [[1,0],[0,-1],[-1,0],[0,1]].forEach(([a,b],i)=>{shape(sl,'rect',cx+a*r-11,cy+b*r-11,22,22,C.blue);txt(sl,'ABCD'[i],cx+a*r+16,cy+b*r-13,40,28,22);});
 txt(sl,'中心上空の2つの候補',70,530,355,32,23,C.blue);txt(sl,'半径100m・地上4台',70,570,355,32,22);
 if(result){
  const c=D.events.counterexamples.circle;
  chart(sl,{title:'全4台のRSSIが一致',categories:['A','B','C','D'],series:[{name:'正常：高度80m',values:c.truthful_rssi_dbm,fill:C.blue},{name:'偽装：高度20m',values:c.attack_rssi_dbm,fill:C.red}],type:'line',x:470,y:170,w:430,h:350,min:-91,max:-86,ytitle:'RSSI（dBm）',labels:false});
  txt(sl,'偽装側の基準電力：−2.18dB\n位置が違っても同じ観測',485,550,410,85,24,C.red,true);
 }else{
  txt(sl,'両方のRID申告：高度80m',535,180,380,40,24,C.blue,true);
  dot(sl,605,270,'正常：実高度80m',C.blue);dot(sl,605,450,'偽装：実高度20m',C.red);
  ln(sl,605,290,605,425,'#CBD2DA',2);txt(sl,'電力も変えると\n見分けられるか？',660,340,245,85,25,C.red,true);
 }
}
function dataSetup(sl){
 const cfg=D.events.config,xyz=D.synthetic_example_xyz;
 const chartObj=sl.charts.add('scatter',{position:{left:45,top:170,width:505,height:350},title:'共通の架空軌跡と5台配置',titleTextStyle:{fontSize:19,fill:C.black},series:[{name:'観測ノード',xValues:cfg.observer_xyz_m.map(p=>p[0]),values:cfg.observer_xyz_m.map(p=>p[1]),marker:{symbol:'square',size:9,fill:C.blue},line:{fill:'none',width:0}},{name:'機体の軌跡例',xValues:xyz.map(p=>p[0]),values:xyz.map(p=>p[1]),marker:{symbol:'none'},line:{fill:'#8CA7C3',width:2}}],hasLegend:true,legend:{position:'bottom',textStyle:{fontSize:16}},xAxis:{min:-200,max:200,title:{text:'東西（m）',textStyle:{fontSize:16}},textStyle:{fontSize:15}},yAxis:{min:-200,max:200,title:{text:'南北（m）',textStyle:{fontSize:16}},textStyle:{fontSize:15},majorGridlines:{fill:'#E8ECF0',width:.7}},scatterOptions:{style:'lineWithMarkers'}});
 applyPresentationChartFont(chartObj,{fontFamily:F});
 table(sl,[['項目','設定'],['機体','共通の3D軌跡'],['観測','0.5秒間隔・5台'],['電力','未知・送信ごとに変動'],['雑音','SD2／6dB'],['反復','10 seed']],{x:575,y:175,w:335,h:330,columns:[95,240]});
 note(sl,['受信範囲は幾何とスキャン欠測の簡略モデル','正常位置誤差・NLOS・実際の時計誤差は未導入'],550);
}
const BANK={};
const define=(key,fn)=>BANK[key]=fn;
const cap=(title,subtitle)=>{
 const sl=coverTemplate.duplicate();for(const o of sl.shapes.items)if(o.text)o.text='';sl.speakerNotes.text='';
 txt(sl,title,90,215,780,150,36,C.black,false,'center');txt(sl,'進捗報告　第26回',160,390,640,45,27,C.gray,false,'center');txt(sl,subtitle,100,455,760,100,23,C.gray,false,'center');
 log.push({slide:sl,title,source:''});return sl;
};
define('coverA',()=>cap('RSSIによる位置偽装検知の調査・評価','公開実測の再解析と複数ノードの合成評価'));
define('coverB',()=>cap('RSSIから位置偽装を検知できるか？','送信電力が分からない・変わる状況での検証'));
define('agendaA',()=>page('目次','研究の前提、公開実測、複数ノード評価、到達点',[['研究の問いと成立条件',['位置と送信電力の曖昧さ、関連研究の前提']],['公開実測と合成評価',['BLE・LoRa再解析、複数ノードの検知率と限界']],['まとめと今後',['検査できる条件と、実RIDで追加確認する事項']]]));
define('agendaB',()=>page('目次','「RSSIから位置偽装を検知できるか」に答える流れ',[['なぜ難しいか',['位置の変化と、送信電力の変更の曖昧さ']],['どんな条件なら検査できるか',['同じ送信を複数地点で受ける意味']],['実験でどこまで分かったか',['検知できる例、保留する例、区別できない例']]]));
define('work',()=>{const sl=base('第26回の作業内容','位置偽装検知の前提から、再現可能な評価まで');table(sl,[['区分','作業内容'],['調査','RSSI・未知電力・異時刻観測の成立条件'],['実測解析','公開BLE・UAV受信LoRaの取得と再解析'],['実装','共通軌跡・複数ノード・保留を含む判定'],['評価','位置改変、電力変更、雑音、時刻差、配置'],['資料','CSV・JSON・日本語図と結果の整理']],{columns:[155,721]});note(sl,['新しい実RID計測・ZKP回路の実装は今回の対象外'],560);return sl;});
define('answer',()=>page('今回の答え','RSSIから位置偽装を検知できる場面はある',[['検査に使える条件',['同じ送信を複数地点で受信し、観測とモデルが適切']],['検知率を下げる要因',['電波の揺らぎ、受信の不足、配置や時刻の誤対応']],['現在の限界',['別送信を単独受信し、電力が毎回自由なら一般に判定不可']]],'今回の複数ノードの検知率は合成評価。実RIDでの実証ではない。'));
define('scenario',()=>{const sl=base('想定する位置偽装','施設周辺を通過する機体の「ここにいる」という申告を調べる');scene(sl);return sl;});
define('terms',()=>{const sl=base('Remote IDの位置とRSSI','位置は機体の申告、RSSIは受信側で測る電波の強さ');scene(sl,'terms');return sl;});
define('factors',()=>page('電波の強さを変える要因','RSSIは、距離だけで決まる値ではない',[['距離と送信電力',['遠いほど弱くなる傾向と、強く送れば強く届く効果']],['電波の通り方',['遮蔽物、反射、アンテナの向きによる変化']],['受信する側の違い',['端末の感度や校正差による変化']]],'簡略モデルの要因整理。各要因を今回のシミュレーションが全て再現しているわけではない。'));
define('ambiguous',()=>{const sl=base('位置と送信電力の曖昧さ','同じRSSIから、位置と電力の組合せを一つに決められない');ambiguity(sl);return sl;});
define('disjointIntro',()=>{const sl=base('異時刻・単独受信での限界','各送信の電力が自由なら、ノードや件数を増やすだけでは不足');overlap(sl,'single');return sl;});
define('timing',()=>{const sl=base('受信した送信の違いと提出時刻','「後から提出」と「別の送信を受信」を区別');timing(sl);return sl;});
define('common',()=>{const sl=base('同一送信の共通電力の除去','ノード間の受信強度の違いと、申告位置からの予測を比較');
 txt(sl,'AのRSSI − BのRSSI',90,175,800,50,34,C.blue,true,'center');
 txt(sl,'同じ送信なら、共通の送信電力成分を除去',80,250,800,50,27,C.red,true,'center');
 txt(sl,'Δr = −10n log₁₀(dA / dB) ＋ 誤差',65,345,835,55,32,C.black,false,'center');
 txt(sl,'dA・dB：申告位置から各ノードまでの距離\nn：距離による減衰を表す係数',105,425,750,75,23);
 note(sl,['送信ごとに電力が変わっても、同じ送信内では共通','向き・遮蔽・受信機差まで消えるわけではない'],545);
 footer(sl,'関連：Hu & Leus, IEEE TSP 2017, DOI:10.1109/TSP.2017.2684741');return sl;});
define('observationConditions',()=>{const sl=base('検査に使う観測の条件','同じRID文字列だけでは、同じ物理送信とは限らない');table(sl,[['条件','必要な確認'],['送信の対応','同じ物理送信を受けた記録か'],['受信の重なり','1送信について複数地点のRSSIがあるか'],['ノードの観測','位置・RSSI・時計の扱いは適切か'],['伝搬と配置','誤差の校正と、区別しにくい配置の確認']],{columns:[200,676]});note(sl,['受信が1台以下、または校正不足の組は判定保留'],550);return sl;});
define('scenarios',()=>{const sl=base('評価する3つの観測シナリオ','受信の重なりで、検査できる範囲が変わる');table(sl,[['シナリオ','1送信の受信','今回の扱い'],['全重複','常に5台','全イベントを検査'],['一部重複','0〜5台','複数受信と校正がある組を検査'],['完全非重複','最大1台','自由電力の位置判定は保留']],{columns:[180,210,486]});note(sl,['全ノードが同じ一本の機体軌跡を参照','提出時刻と、電波を受信したイベントは別に管理'],520);return sl;});
define('related',()=>{const sl=base('関連研究と今回の前提','未知電力を扱う研究でも、観測を共有する条件が重要');table(sl,[['関連研究','扱う内容','今回との境界'],['GhostBuster','RSSによるRID位置偽装の検知','複数観測者は実測チャネルから拡張'],['DRSS','受信強度差による未知電力の扱い','共通電力と受信ごとの電力差を区別'],['今回の問い','別時刻・変動電力・受信の重なり','何が不足すると判定できないか']],{columns:[170,310,396],h:310});note(sl,['完全非重複・毎送信の自由電力を無条件に解決した結果とは扱わない'],535);footer(sl,'Keizer et al., CCNC 2024, DOI:10.1109/CCNC51664.2024.10454860\nHu & Leus, IEEE TSP 2017, DOI:10.1109/TSP.2017.2684741');return sl;});
define('evidence',()=>{const sl=base('今回使用したデータの区分','実測で確認する注意点と、合成で検証する成立条件');table(sl,[['データ','実際に測った内容','今回確認すること'],['屋内BLE実測','固定ビーコン→スマホのRSSI','揺らぎ・出力設定差'],['LoRa実測','固定送信機→移動するUAV','時刻対応・観測集約'],['複数ノード合成','架空の機体軌跡とRSSI','位置改変の検知・保留・反例']],{columns:[200,325,351],h:315});note(sl,['実UAVのBLE／Wi-Fi RIDを複数台で同時取得した実測ではない'],540);return sl;});
define('ble',()=>{const sl=base('公開BLE実測におけるRSSI変動','出力設定差とRSSI差が、そのまま一致するとは限らない', '出典：manwestc/ble-rssi-indoor-localization-dataset、固定版 b38a9a4（屋内BLE実測）');
 const a=D.ble.paired_setting_shifts;chart(sl,{title:'出力設定差と、RSSI中央値差',categories:['−8 → −4dBm','−4 → 0dBm','−8 → 0dBm'],series:[{name:'出力設定差',values:a.map(r=>r.nominal_shift_db),fill:C.blue},{name:'RSSI中央値差',values:a.map(r=>r.median_rssi_shift_db),fill:'#8CA7C3'}],max:10,ytitle:'差（dB）'});
 note(sl,['同じ地点・ビーコンの組を比較。測定セッションの違いも含む','位置・環境を固定した電力だけの因果効果とは断定しない'],550);return sl;});
define('loraSetup',()=>{const sl=base('公開UAV・LoRaデータの構成','実飛行中のRSSIと位置参照を使った再解析','出典：Mavilia et al., Data in Brief 2025, DOI:10.1016/j.dib.2025.112243\nデータ：Zenodo v2, DOI:10.5281/zenodo.17339095');table(sl,[['項目','内容'],['送信・受信','雪中の固定LoRa送信機 → UAV上の受信機'],['件数','19条件・142,039件（公開論文の件数と一致）'],['分割','3 runがある16条件、学習／校正／評価を分離'],['距離','位置参照・高度から平坦地の斜距離を近似'],['対象の違い','868MHz LoRa。BLE Remote IDではない']],{columns:[170,706],h:360});note(sl,['複数地上ノードで同じRID送信を受けた実測ではない'],560);return sl;});
define('loraWindow',()=>{const sl=base('LoRa実測の観測集約と距離誤差','観測をまとめても、距離誤差の改善は小さめ',src(L,'window-summary.csv','公開LoRa実測の再解析'));
 const a=D.lora.window.filter(r=>r.radial_range_shift_m===0);chart(sl,{title:'中央値集約と距離誤差',categories:['1件','5件','20件'],series:[{name:'RSSI距離モデル',values:a.map(r=>r.mae_m)},{name:'RSSIなし・学習距離中央値',values:a.map(r=>r.prior_mae_m),fill:'#8CA7C3'}],max:50,ytitle:'距離近似値に対するMAE（m）'});
 note(sl,['16条件・48分割を等重み平均。距離は地形を簡略化した近似','連続する観測を、独立した反復試験とは扱わない'],550);return sl;});
define('loraDelay',()=>{const sl=base('LoRa実測の時刻対応と誤警報','古いRSSIを現在位置と比較すると、正常でも警報が増える',src(L,'delay-summary.csv','実測系列への人工時刻ずれ'));
 chart(sl,{title:'RSSIの古さと正常誤警報率',categories:D.lora.delay.map(r=>r.requested_delay_s+'秒'),series:[{name:'正常誤警報率',values:D.lora.delay.map(r=>pc(r.normal_fpr))}],type:'line',max:30,ytitle:'正常誤警報率（%）'});
 note(sl,['15秒ずれでは約23.2%。全遅延で同じ評価時刻を使用','実RIDの複数ノード融合を測定した結果ではない'],550);return sl;});
define('setup',()=>{const sl=base('複数ノード合成評価の条件','未知・変動電力を持つ一本の飛行を、複数地点で観測',src(E,'config.json'));dataSetup(sl);return sl;});
define('metrics',()=>{const sl=base('検知・誤警報・判定保留','警報が出た割合だけでなく、判定できた割合も評価');table(sl,[['入力と出力','意味'],['位置を改変した入力 → 警報','合成実験での位置偽装の検知'],['正常な入力 → 警報','正常時の誤警報'],['観測・校正が不足 → 保留','位置が正しいとも、偽装とも判断しない'],['判定可能部分の検知率','判定できたイベントだけを分母にする'],['全送信中の検知割合','保留を含む全送信を分母にする']],{columns:[390,486],h:350});note(sl,['正常校正の95%点を閾値に設定。評価飛行とは分離'],550);return sl;});
define('power',()=>{const sl=base('共通電力の変更と警報率','電力変更だけで位置偽装と誤認しないか',src(E,'cases-summary.csv'));
 const names=['normal','power_plus16','power_random16'];chart(sl,{title:'同一送信を5台受信・雑音SD2dB',categories:['正常','電力 +16dB','送信ごとに追加変動'],series:[{name:'正常への警報',values:names.map(n=>pc(ev('full',n).conditional_alarm_fraction))}],max:20,ytitle:'正常時の誤警報率（%）'});
 note(sl,['3条件とも約5%。共通電力の変更はスコアから除去','電力変更そのものや、申告電力の虚偽を検知した結果ではない'],550);return sl;});
function curveSlide(sd){const sl=base(sd===2?'位置改変量と受信ノード数':'雑音増加による検知率の低下',sd===2?'位置をどれだけ変えると検知できるか':'同じ配置・同じ改変でも、電波の揺らぎで見逃しが増加',src(E,'curves-summary.csv'));
 const shifts=D.events.config.claim_displacements_m;chart(sl,{title:'独立リンク雑音 SD'+sd+'dB',categories:shifts.map(x=>x+'m'),series:[2,3,5].map((n,i)=>({name:n+'台',xValues:shifts,values:shifts.map(v=>pc(select(D.events.curves,{noise_sd_db:sd,receivers:n,shift_m:v}).conditional_alarm_fraction)),fill:[C.blue,'#8CA7C3',C.red][i]})),type:'scatter',max:100,ytitle:'警報率（%）'});
 note(sl,[sd===2?'100m改変でも、5台の検知率は約73.7%':'雑音SD6dBでは、100m改変・5台でも約18.7%', '0mは正常誤警報。台数の変更とともに使う配置も変化',...(sd===2?['位置100m＋共通電力補償でも、同じ73.7%（5台）']:[])],540);return sl;}
define('curve2',()=>curveSlide(2));define('curve6',()=>curveSlide(6));
function coverageSlide(onlySingle=false){const sl=base(onlySingle?'毎回1台しか受信しない場合':'一部重複での検知と判定保留',onlySingle?'全件保留は、位置が正しいという判定ではない':'同じ100m改変でも、判定できる時間帯は限られる',src(E,'cases-summary.csv'));
 const modes=onlySingle?['full','partial','single']:['full','partial'];const a=modes.map(m=>ev(m,'position100'));chart(sl,{title:'雑音SD2dB・全送信を分母にした割合',categories:onlySingle?['常に5台','一部重複','毎回1台']:['常に5台','一部重複'],series:[{name:'不整合の警報',values:a.map(r=>pc(r.all_event_alarm_fraction)),fill:C.red},{name:'警報なし',values:a.map(r=>pc(r.decision_fraction-r.all_event_alarm_fraction)),fill:C.blue},{name:'判定保留',values:a.map(r=>pc(r.abstain_fraction)),fill:C.pale}],stack:true,labels:false,max:100,ytitle:'全送信に対する割合（%）'});
 note(sl,onlySingle?['各イベントを1台だけ受信する条件では100%保留','自由電力なら、位置が違っても同じRSSIを作れる']:['一部重複：判定可能77.1%、その部分の検知率64.0%','全送信中の警報は49.35%、保留22.89%'],550);return sl;}
define('coverage',()=>coverageSlide(false));define('singleCoverage',()=>coverageSlide(true));
define('mispair',()=>{const sl=base('異なる送信の誤対応と誤警報','時刻が近いだけでは、電力が共通とは限らない',src(E,'pairing-summary.csv'));
 const gaps=D.events.config.pairing_spread_s;chart(sl,{title:'雑音SD2dB・正常データへの警報',categories:gaps.map(x=>x+'秒'),series:[['stable','飛行中の電力一定',C.blue],['per_event_variable','送信ごとに変動 SD8dB',C.red]].map(([mode,name,fill])=>({name,fill,values:gaps.map(t=>pc(select(D.events.pairing,{noise_sd_db:2,power_mode:mode,maximum_pairing_age_s:t}).conditional_alarm_fraction))})),type:'line',max:100,ytitle:'正常誤警報率（%）'});
 note(sl,['0.5秒でも、電力が別々なら誤警報が増えるモデル例','電力変動SD8dBは仮定。実機の時間上限や測定値ではない'],550);return sl;});
define('upload',()=>{const sl=base('同一送信の提出遅延','受信したイベントを正しく結べれば、提出が遅くても同じ判定',src(E,'uploads-summary.csv','理想的な同一イベント結合'));
 const a=D.events.uploads.filter(r=>r.noise_sd_db===2);table(sl,[['最後の提出まで','正常誤警報率','追加の判定待ち'],...a.map(r=>[r.upload_spread_s+'秒',fmt(pc(r.alarms/r.decidable_events),2)+'%',r.decision_wait_s+'秒'])],{columns:[290,290,296],h:255});
 section(sl,'成立の前提',['同じ物理送信であることを理想的に知っている条件','通信スタック・時計誤差・実際の対応付けは未評価'],465,24);return sl;});
define('geo1',()=>{const sl=base('複数受信機でも残る配置の曖昧さ','4台受信でも、違う位置を区別できない配置がある','数理反例：雑音なし、単一送信源、既知の伝搬指数2.2。実RFの攻撃実証ではない。');geometry(sl);return sl;});
define('geo2',()=>{const sl=base('配置と電力補償による同一観測','高度も電力も違うのに、全ノードで同じRSSI',src(E,'summary.json / counterexamples','雑音なしの数理反例'));geometry(sl,true);return sl;});
define('personal',()=>{const sl=base('RID別学習の効果と限界','学習による誤差改善は、位置や機体の真正性の証明ではない',src(S,'personalization-summary.csv'));
 const cases=['normal','cloned_rid'];chart(sl,{title:'30ラベル／RID・ID差SD6dB・飛行差SD1dB',categories:['通常の送信機','同じRIDを名乗る別送信機'],series:[['global','共通モデル',C.blue],['rid_shrinkage','RID別補正','#8CA7C3']].map(([model,name,fill])=>({name,fill,values:cases.map(scenario=>+select(D.personal,{profile:'stable_id6',labeled_per_rid:30,scenario,model}).mae_m)})),max:70,ytitle:'距離MAE（m）'});
 note(sl,['学習ラベルは独立した合成真距離。RID申告値ではない','同じRID文字列でも同じ物理機体とは限らず、補正が悪化'],550);return sl;});
define('attribution',()=>page('警報から判断できること','示せるのは、位置申告と観測の不整合',[['警報が出た場合',['位置偽装の疑い。ただし遮蔽・向き・受信誤差も候補']],['警報が出なかった場合',['位置が正しい証明ではない。見逃しや識別不能配置が残る']],['電力について',['実際のEIRPや、電力申告の真偽を測った方式ではない']]]));
define('conditions',()=>{const sl=base('位置偽装を検査できる条件','台数だけでなく、同一送信・観測品質・配置が必要');table(sl,[['状況','今回の到達点','残る条件・限界'],['同じ送信を複数受信','位置改変の不整合を検知','観測・モデル・配置に依存'],['一部だけ重複','重複部を検査、その他は保留','全送信の検知割合は低下'],['別送信を単独受信','自由電力の位置判定は保留','RSSI単独では一般に識別不可'],['等距離比となる配置','同じRSSIを作れる反例','複数台でも全検知は不可'],['警報の原因','不整合まで','位置偽装と原因を確定しない']],{columns:[250,310,316],h:390});note(sl,['実測で確認した注意点と、合成で得た検知率を区別'],580);return sl;});
define('summaryA',()=>page('まとめ','未知・変動電力の下で、位置申告を検査できる条件を整理',[['同一送信の複数受信',['共通電力を除いた位置申告の検査を合成評価']],['実測から得た注意点',['RSSIの揺らぎと、時刻を誤って対応させた場合の誤警報']],['未解決の条件',['完全非重複・自由電力と識別不能な配置、実RIDでの検証']]]));
define('summaryB',()=>page('RSSIから位置偽装を検知できるか','条件付きで一部は検知可能。無条件の位置認証ではない',[['検査できる場面',['同じ送信を複数地点で受け、観測・配置・モデルが適切']],['判定できない場面',['別送信を単独受信し電力が自由、または識別不能な配置']],['今回示した範囲',['合成で成立条件と検知率を確認。実RIDでの実証は今後']]]));
define('future',()=>page('今後','実際のRIDで、成立条件を満たせるかを確認',[['同じ送信の対応付け',['受信時刻・PHY等の取得可能情報と、誤対応率の評価']],['現実の受信条件',['電力による受信可否、時計誤差、NLOSや雑音相関の導入']],['独立真値付きの複数ノード実測',['位置真値・同一送信の重複・実効電力の条件を記録']]]));
// Shared appendix pages.
define('singleModels',()=>{const sl=base('補足：単一RSSIの推定モデル','距離精度が改善しても、自由電力の識別不能性は解消しない','出典：mac-independent3d-20261101 / summary.json（独立した合成10 seed）');
 const a=D.single.filter(r=>r.channel==='mixed'&&r.scenario==='normal'&&['PathLoss','Bayesian','GP','MLP'].includes(r.model));chart(sl,{title:'通常条件での距離推定',categories:a.map(r=>r.model),series:[{name:'距離MAE',values:a.map(r=>r.mae_m)}],max:70,ytitle:'距離MAE（m）'});
 note(sl,['事前分布・学習済み条件の下での性能','同じ機体を複数ノードが通過観測する評価とは別の実験'],550);return sl;});
define('empirical',()=>{const sl=base('補足：実測残差による雑音ストレス','小さい独立ガウス雑音の仮定は、楽観的になる場合がある',src(R,'empirical_sync-summary.csv','屋内BLE残差を仮想リンクへ注入'));
 const kinds=['gaussian2','gaussian_matched_rms','empirical'];const rows=kinds.map(noise_model=>D.empirical.find(r=>r.noise_model===noise_model&&r.receivers==='10'&&r.environment==='matched'&&r.delta_m==='100'));
 if(rows.some(r=>!r))throw Error('empirical source category mismatch '+JSON.stringify([...new Set(D.empirical.map(r=>r.noise_model))]));
 chart(sl,{title:'10受信機・100m改変の警報率',categories:['ガウス SD2dB','RMSを合わせたガウス','屋内BLEの実測残差'],series:[{name:'改変時の警報',values:rows.map(r=>pc(+r.alarm_rate))}],max:100,ytitle:'警報率（%）'});
 note(sl,['実測残差を各仮想リンクに独立に抽出した評価','屋外UAV・複数受信機の同時実測の性能ではない'],550);return sl;});
define('poison',()=>{const sl=base('補足：個別モデルの学習汚染','誤った距離ラベルへの頑健化にも限界がある',src(R,'poisoning-summary.csv'));
 const fractions=[0,.1,.3,.5,.7];chart(sl,{title:'距離ラベルを4倍に改変した場合',categories:fractions.map(v=>pc(v)+'%'),series:[['mean','平均補正',C.blue],['median','中央値補正',C.red]].map(([model,name,fill])=>({name,fill,values:fractions.map(corrupt_fraction=>+select(D.poisoning,{flight_sd_db:1,pattern:'random_rows',corrupt_fraction,distance_multiplier:4,scenario:'normal',model}).mae_m)})),type:'line',max:150,ytitle:'距離MAE（m）'});
 note(sl,['外部の共通学習データは保護されている仮定','誤ラベルが過半数になる場合まで防御できるわけではない'],550);return sl;});
define('expiry',()=>{const sl=base('補足：過去情報とモデル失効','電力や環境が長く安定すると誤ると、区間を過信する',src(R,'time_mismatch-summary.csv'));
 const rows=['none','600','86400'].map(assumed_tau_s=>select(D.time,{true_tau_s:600,assumed_tau_s,gap_s:3600,scenario:'normal'}));
 chart(sl,{title:'真の相関時間10分・1時間後の予測',categories:['履歴なし','相関時間10分の仮定','相関時間1日の仮定'],series:[{name:'公称90%区間の実包含率',values:rows.map(r=>pc(+r.interval_coverage))}],max:100,ytitle:'区間包含率（%）'});
 note(sl,['1日安定と誤ると、包含率は約60.8%まで低下','この相関時間は仮定であり、実UAVで推定した値ではない'],550);return sl;});
define('dropout',()=>{const sl=base('補足：追加欠測と観測窓','受信済みの観測を失うと、固定件数の窓は古くなる',src(L,'dropout-summary.csv','実測系列からの人工削除'));
 const a=D.lora.dropout.filter(r=>r.window_packets===20);chart(sl,{title:'20件集める時間幅の変化',categories:a.map(r=>pc(r.drop_fraction)+'%削除'),series:[{name:'ブロック時間幅の中央値平均',values:a.map(r=>r.span_median_s)}],max:20,ytitle:'時間幅（秒）'});
 note(sl,['元々のRF損失率は不明。受信済み記録を追加で削除','完全ブロックが作れない例を、誤差ゼロにしていない'],550);return sl;});
define('sourceMap',()=>{const sl=base('補足：データ・実装・出典の対応','入力の版と集計CSVを残し、実測と合成を分離');table(sl,[['対象','入力・集計の所在'],['公開BLE','固定版 b38a9a4 / mac-recheck-20261101'],['公開LoRa','Zenodo 17339095 v2 / mac-public-lora-20261101'],['共通軌跡の合成','event_scenarios_config.json / mac-event-scenarios-20261101'],['学習等の合成','mac-sensitivity-20261101-v2 / mac-robustness-20261101'],['確認できないもの','認証が必要なICMCIS本体、別チャットの元ZIP']],{columns:[200,676],h:370});note(sl,['取得できないデータを、再現済みの実験として使用しない'],565);return sl;});
const APP=['singleModels','empirical','poison','expiry','dropout','sourceMap'];
const ORDER_A=['coverA','agendaA','work','scenario','terms','ambiguous','disjointIntro','timing','related','common','scenarios','evidence','ble','loraSetup','loraWindow','loraDelay','setup','metrics','power','curve2','curve6','coverage','mispair','upload','geo1','geo2','personal','conditions','summaryA','future',...APP];
const ORDER_B=['coverB','agendaB','work','answer','scenario','terms','factors','ambiguous','disjointIntro','common','observationConditions','related','evidence','ble','loraDelay','setup','metrics','power','curve2','curve6','coverage','singleCoverage','mispair','upload','geo1','geo2','attribution','conditions','summaryB','future',...APP];
async function build(tag,order){
 P=await PresentationFile.importPptx(await FileBlob.load(REF));template=P.slides.items[4];coverTemplate=P.slides.items[0];log=[];
 const slides=[];
 for(const key of order){const sl=BANK[key]();slides.push(sl);log.at(-1).key=key;}
 P.slides.keep(slides.map(sl=>P.slides.items.findIndex(s=>s.id===sl.id)));
 slides.forEach((sl,i)=>sl.moveTo(i));
 const dir=path.join(CACHE,tag);await fs.mkdir(dir,{recursive:true});
 const records=log.map((r,i)=>({slide:i+1,key:r.key,title:r.title,source:r.source,charts:r.slide.charts.items.length,tables:r.slide.tables.items.length}));
 await fs.writeFile(path.join(dir,'slide-map.json'),JSON.stringify(records,null,2));
 // Native chart workbooks use 6 decimal places; original aggregates retain full precision.
 for(const slide of slides)for(const ch of slide.charts.items)for(const se of ch.series.items){
  se.values=se.values.map(v=>v===null?v:Number(v.toFixed(6)));
  if(se.xValues?.length)se.xValues=se.xValues.map(v=>Number(v.toFixed(6)));
 }
 await (await PresentationFile.exportPptx(P)).save(path.join(dir,'draft.pptx'));
 console.log(`${tag}: exported ${slides.length} slides`);
 for(let i=0;i<slides.length;i++){
  const png=await P.export({slide:slides[i],format:'png',scale:1});await fs.writeFile(path.join(dir,`slide-${i+1}.png`),new Uint8Array(await png.arrayBuffer()));
  if((i+1)%6===0)console.log(`${tag}: rendered ${i+1}/${slides.length}`);
 }
 await fs.writeFile(path.join(dir,'layout-inspection.ndjson'),(await P.inspect({kind:'textbox,chart,table',maxChars:2000000})).ndjson);
}
const arg=process.argv[2]??'both';
if(arg==='A'||arg==='both')await build('A',ORDER_A);
if(arg==='B'||arg==='both')await build('B',ORDER_B);
