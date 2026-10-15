# 全方式の既存結果をグラフへまとめる

18構成・38件のrun/集計記録を、PiのCPU条件・Mac・署名workloadで分けて描画する。
追加のproof生成・Pi負荷・新しい性能測定は行わない。
読取対象は既存の公開JSON/JSONLとPlonky2の公開`time -l`出力だけ。captureやprivate cacheは読まない。

```sh
python3 experiments/all-framework-plots/plot.py
python3 -m unittest discover -s experiments/all-framework-plots -p 'test_*.py'
python3 experiments/all-framework-plots/check_results.py
```

描画時はmatplotlibと日本語fontが必要。今回はmatplotlib3.9.4・Hiragino Sansで生成し、SVGはfontをpathへ埋め込む。
別環境ではNoto Sans CJK JPも利用できる。`render-metadata.json`に描画環境を保存。

- 00：全18構成の実行状況。未集計／未実施／IVC／途中成功／保護停止を区別。
- 01：Pi・CPU quotaなし、1CPU affinityの12構成。
- 02：Pi・CPUQuota25%の5記録。Plonky2は2件成功後の中断で、memoryはsampling最大のみ。
- 03：Pi・CPUQuota25%、Kimchi/Binius64/Joltの同一入力3反復。
- 04：Macの追加距離記録。SP1の2停止試行も含める。
- 05：Pi・gnarkの署名付き1/2/4観測と旧partial。
- 06：Mac・gnarkの署名付き観測。停止runの検証済み部分を斜線で表示。

出力：`week24/plots/all-frameworks/*.png`／`.svg`、`week24/data/all-frameworks/`のCSV/JSON/JSONL。
入力のSHA256は`provenance.json`に保存。再生成は今回の専用出力だけを更新し、元の結果・図・manifestを変更しない。
過去のNoir/cold、setup/署名の測定範囲、curve/security、proof形式は揃っていない。順位や1Hz適合性の確定には使わない。
欠測はnull／CSV空欄。IVCの最終proofやSP1の未完了proofを0 byte扱いしない。
Mac RSS、Mac footprint、Pi kernel peak、Pi partial sampling最大は異なる指標として保存・描画する。

`n`は図内で平均へ用いた記録数（case/反復/IVC step）。signed図の「観測数」とは別。
Mac距離の「集計対象外」は、この図で参照した記録がないという意味で、失敗や非対応を意味しない。
SVG/PNGは科学図のartifact。暗号学的保証やsensor truthの評価は元報告の範囲を継承する。

```sh
python3 experiments/all-framework-plots/package.py
python3 experiments/all-framework-plots/manifest.py
```

ZIPにはPNG/SVG・公開集計データ・report12を含める。閲覧／資料利用用の一括配布で、再生成には元の入力記録を含むrepositoryが必要。
CIは標準libraryだけで欠測・途中停止・host境界と数値・画像hashを検査し、異なるfont環境で図を上書きしない。
