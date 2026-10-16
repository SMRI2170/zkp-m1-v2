# Issue #60：無負荷での事前状態観測

`observe.py`はhash固定の既存preflightを読み、30秒間隔で3 snapshotを保存する。
sudo・OS設定変更・service再起動・prover起動を行わない。ready=falseでも観測は続け、最後に終了コード1。
ready=trueも次のpreflightへ進む根拠の一部で、実proof成功や長期安定性の保証ではない。

```sh
python3 observe.py --preflight /home/pi/.cache/week24/preflight-v1.py --out /home/pi/.cache/week24/observe-NEW
python3 -m unittest discover -s experiments/pi-balanced-readiness -p 'test_*.py'
python3 experiments/pi-balanced-readiness/check_results.py
```

出力先は未使用名、owner-only。秘密・IP・serial・boot ID・journal本文は収集せず、稼働時間・メモリ・温度・保護状態・journalの一致件数だけ保存する。
公開する前にmetadataの内容を確認する。今回の保存済み3観測は、同じ固定preflight.snapshotをSSH stdin scriptから呼び出して取得した。
新observe.py自体のPi E2E成功とは扱わない。

SSH失敗からOOMや電源障害を断定しない。低電圧の過去履歴と現在のbitを分ける。
再起動後は保護状態を確認し、既存のruntime復旧手順と3 snapshotのready preflightを通してから負荷試験へ進む。
この実装はproofの準備観測のみであり、研究PoCの観測の真実性やhardware／航空機認証を保証しない。
