# 4レプリカ・3票のBCなし最小署名ログ

```sh
python3 week23/poc/quorum-log/run.py
python3 week23/poc/quorum-log/security_check.py
```

Pythonのcryptography依存、前段の `../../logs/integrated-history.json` を使用する。
4レプリカは別プロセス。transportはテストharnessのstdio配送。
prepare/commit QCは署名と3個の異なる署名者を検査し、投票をfsyncしてから応答する。
`.cache/week23/private/quorum-log-v1` が既存なら停止し、保存する。再実行はBASEを新しい名前へ変更する。

固定1slot/leaderの安全性・失敗系baseline。view changeのないことによる停止は実験結果として残す。
PBFT完成版や本番BFT実装とは扱わない。公開結果 `../../logs/quorum-log.json`。
[Besuとの比較と限界](../../09_BCなし4レプリカとBesu障害比較.md)。
