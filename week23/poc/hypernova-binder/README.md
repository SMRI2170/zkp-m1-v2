# HyperNova NIMFS fold binder（中間部品）

これは **元IVC履歴のbinder／秘密非共有引継ぎの完成実装ではない**。
2個のsynthetic LCCCSを1個へfoldするNIMFS関係を、Groth16用Fr回路へ移した実験。
入力LCCCSの有効なopening、元IVCの成立、CycleFold、最新incoming assignment、
次のaugmented circuitでのbinder検証は、この回路のstatementに含めていない。

前提は[10の固定sourceと互換patch](../../10_HyperNova実行と最新Sonobe安全性と秘密引継ぎ.md)、
`week23/poc/sonobe-current/hypernova-ark06.patch`、Rust stable、macOS（resource guardのsysctl）。
patched sourceの配置はCargo.tomlのpath dependencyと一致させる。
CCSは上流CircuitForTest、public x=1項目、r_x=2、v=3、SumCheck 2round×4係数、sigma=6。
異なるshapeには別回路・鍵が必要であり、現回路は拒否する。

```sh
CARGO_TARGET_DIR=.cache/week23/target-hypernova-binder cargo +stable build --locked --release -j 2 --manifest-path week23/poc/hypernova-binder/Cargo.toml
CARGO_TARGET_DIR=.cache/week23/target-hypernova-binder cargo +stable test --locked --release -j 2 --manifest-path week23/poc/hypernova-binder/Cargo.toml -- --test-threads=1
python3 week23/poc/hypernova-binder/run.py plan
python3 week23/poc/hypernova-binder/run.py prove
```

実行前にmemory/swapを確認する。guardはRSS 4.5 GiB／swap used 7,500 MiBを上限とし、
中断したlogとfixtureも保存する。`plan`はR1CS充足性のみ、証明生成成功ではない。
`check`はplanと否定テストまで、`prove`は加えてsetup/prove/native verifyを行う。
fixtureが既に存在する場合、上書き・自動削除・未確認reuseはせず失敗する。
再実行は既存fixtureを別のprivate名へ意図的に保存した上で行う。

公開入力はversion/session/policy/epoch/stepの5タグと、全入力・出力instanceを拘束するGriffin digest。
タグと元IVCのsession等との対応は未拘束で、タグのprovenanceを証明しない。
Groth16鍵に固定したGriffin設定とtoy relationを使用する。
上流のpartial verifierに加え、`cm_out = cm_0 + rho * cm_1`を
BN254 Fqの非ネイティブ群演算で拘束する（rhoは上流transcriptの128bit challenge）。
群演算はark-r1cs-std 0.6.0のRCB Algorithm 1を移植した実験コードで、監査済みではない。
infinity・逆元・doubling・off-curve・誤った和を単体テストし、実NIMFSの出力と照合する。

否定テストはtarget/input commitment、target scalar、SumCheck、sigma、session digest。
最初の5件はdigestも再計算するため、digestの不一致だけで拒否した結果ではない。
今回のサンプル入力はnative decide_runningで事前検証するが、そのhost検査をbinder回路内の保証とは扱わない。

pk/vk/proof/publicはignored `.cache/week23/private/hypernova-fold-binder-v1` のみに保存し、
directory 0700／files 0600。private assignmentはキャッシュしない。
使い捨て単独setupのテストfixtureで、公開・deploy・release keyへの転用はしない。
Gitにはコード、phase-only log、resource測定、hash manifestだけを記録する。
