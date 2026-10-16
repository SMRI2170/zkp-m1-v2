# Week24：順次実行プログラムとCSV／JSON出力

チャットで処理完了を待つ運用をやめ、[順次実行プログラム](../experiments/sequential-evaluation/README.md)を追加した。
起動コマンドは別processを開始して直ちに戻り、ジョブが工程ごとの状態と結果をファイルへ更新する。

## 処理順

1. runnerの回帰検査、Piへの接続と現在の準備状態の確認。
2. 実装済み8構成のビルド、gnarkの新private fixture生成、Circom／Noirの新driver生成。
3. Piがreadyの場合だけ配置し、8構成を1方式ずつ既存の保護付きlauncherで測定。
4. 回収できた実測からCSV／JSONL・統計JSON・PNG／SVGを生成。
5. 残る8構成の未対応理由と、対象commitのGitHub Actions結果・ログを保存。

1工程が失敗した場合、依存する測定は開始せず、独立したローカル工程や回収は進める。
Piのguard設定やOS設定をこのプログラムが自動的に変更することはない。
接続断の後に同じproof試験を自動再送しない。Pi側で実行が続いている可能性を記録し、残存unitの確認を必要とする。

## 起動と結果

```sh
python3 experiments/sequential-evaluation/run.py start \
 --tag seq-1016a --out .cache/week24/sequential-jobs/seq-1016a
```

同名の出力・build/runは上書きしない。起動済みの場合は新しい小文字tagを使う。
SSH認証情報は環境から渡し、plan・CSV・JSON・Gitへpasswordを書き込まない。

- `status.json`：全体と各工程の状態、開始／終了時刻、終了コード、理由。
- `results.csv`：工程別の状態と実行時間。
- `events.jsonl`：状態遷移の履歴。
- `data/samples.csv`／`samples.jsonl`、`data/summary.json`：回収できた実際の測定値と統計。
- `pi-readiness.json`、`measurement-status.json`：準備状態・実測の有無・partialログの所在。
- `ci-results.csv`／`ci-results.json`：CI状態とリンク。
- `private/`：owner-onlyの詳細ログ。公開前に内容を確認する。

`completed`はその工程の完了。build成功はproof成功ではなく、CLI driver生成は実CLI測定ではない。
`blocked`、`failed`、`timed_out`、`interrupted`、`unsupported`を分ける。実測がなければ空CSV／空JSONで示し、0秒・0byteの成功や仮の性能図を作らない。
現在のplanには未対応8方式も含むため、それらは理由付きの`unsupported`、全体は`partial`となり得る。
このprogramが未知の研究実装まで自動生成するわけではない。各ライブラリの実装・検証自体は #61 の残件。

## 検証範囲

回帰7件で、失敗時の依存停止、回収の継続、timeout時の子process停止、実行途中の再送禁止、欠測欄、未対応状態を検査した。
ローカルのplan検査やテスト成功を、Piでの21件測定成功と混同しない。
起動後はチャットで完了を待たず、実行開始の報告と結果ファイルの場所を伝える。

研究PoCの合成入力のみ。既存の回路・否定テスト・メモリ／SSH保護を維持し、実capture・実座標・鍵・使い捨てsetup/VK/proof実体を公開・deployしない。
DRIP trust chain、sensor honesty、observer hardware／航空機認証を保証しない。
