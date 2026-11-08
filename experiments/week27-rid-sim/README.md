# Issue #70 — uli-net-sim integration (PR1)

Research PoC for **OMNeT++/INET simulation of Remote ID-like custom Wi-Fi
Beacons**. Not real UAV Remote ID measurements, ASTM/Japanese byte-level
conformance, aircraft authentication or a production safety system.

Read [#70](https://github.com/SMRI2170/zkp-m1-v2/issues/70),
[#66](https://github.com/SMRI2170/zkp-m1-v2/issues/66),
[#67](https://github.com/SMRI2170/zkp-m1-v2/issues/67), and
[#68](https://github.com/SMRI2170/zkp-m1-v2/issues/68).
All four issue bodies and comments were checked before implementation.
The main question remains **asynchronous, different packets, one RSSI each,
unknown and potentially arbitrary per-packet power**. This PR1 smoke uses
same-packet multiple receivers only to check communication/event plumbing.

## Isolation and versions

- No changes to existing Week25/26 numerical models, ZKP circuits, Flutter,
  observer capture, or real-data analysis. Visualization remains #69's scope.
- `upstream.lock.json` pins upstream SHA, OMNeT++ 6.2.0, INET 4.5.4 and
  Eigen 5.0.0 archive hashes. The compiler/OS must also be recorded per run.
- Python **3.12** is embedded into the simulator; `requirements-smoke.txt`
  pins the minimal no-detector environment. This is not upstream's full uv/ML
  environment. Torch, MLP, training and graphical notebooks are **NOT_RUN**.
- No repository-wide LICENSE exists at the pinned upstream SHA. Some source
  files have LGPL SPDX headers. We only reference a local, unmodified clone;
  **no upstream source, binary, source patch or built image is redistributed**.
- `scitech26` is a different snapshot, pinned separately in the lock. The
  inspected diff has 194 files, 23,655 insertions and 85,765 deletions. Running
  current main does not reproduce the paper's reported detection accuracy.

## Host setup

On macOS Apple Silicon, install command-line Xcode tools, Homebrew GNU Make
4+, pkg-config, bison, flex, OpenSceneGraph and Python 3.12. The build is bounded to 1–2 jobs.
The following package command is a separate explicit setup step; the Python
runner never silently invokes a global package manager:

```sh
HOMEBREW_NO_AUTO_UPDATE=1 HOMEBREW_NO_INSTALL_CLEANUP=1 \
  brew install make pkgconf bison flex open-scene-graph python@3.12
```

For Linux, provide Clang/GNU Make 4+, pkg-config, bison, flex, Python 3.12,
Python development headers, a shared libpython and normal C/C++ development
libraries and OpenSceneGraph development headers/libraries. **Linux simulator compilation is not established by the offline
GitHub Actions adapter tests.** No Docker daemon is needed for the native build.

Check available memory/swap and disk before building. Reserve at least 8 GiB
disk for setup. The observed host has 16 GiB RAM; do not raise parallelism to
all CPU cores. Do not clean another experiment's caches to make space.

From repository root:

```sh
python3 experiments/week27-rid-sim/scripts/setup.py \
  --stage preflight --out .cache/issue70/preflight-NEW

python3 experiments/week27-rid-sim/scripts/setup.py \
  --stage build --jobs 2 --out .cache/issue70/build-NEW
```

Default local dependencies: `.cache/issue70/` (ignored). Downloads are hash
verified; failed partial downloads and mismatched/existing upstream checkouts
are preserved for inspection. Use a fresh workspace directory for a clean
reproduction rather than assuming an old extracted directory is pristine.
The CLI build sets Qtenv off but keeps OSG libraries enabled. Building all
upstream modules with OSG disabled failed in MultirotorMobility's drawing code;
no module or security check was removed to obtain success. Radio/Beacon source
remains unchanged. This is a CLI adaptation of the README's GUI setup, not a 3D demo.

## Run PR1 (after build success)

```sh
.cache/issue70/python/bin/python experiments/week27-rid-sim/scripts/run_smoke.py \
  --raw-dir captures/issue70-smoke-NEW \
  --summary-dir week27/results/uli-net-sim-smoke-NEW
```

Both configs use seed **2170**, 4 simulator seconds, fixed 13 dBm, one moving
transmitter and two receive-only stationary ground nodes. The attack invokes
the **existing StaticLocationSpoofer**, not a new detection/power algorithm.
The runner asserts equal true trajectories/enqueue schedules/powers, honest
claims in Normal, changed claims and spoof labels in StaticSpoof, exact RX→TX
packet matches, RX/GCS counts, and presence of actual RSSI vectors.

Outputs:

- Private `captures/.../{Normal,StaticSpoof}/`: actual `.vec/.sca`, simulation
  and conversion logs, exact argv/exits, upstream Parquet, audited observation
  CSV/Parquet, TX ledger and GCS CSV. Directories 0700, files 0600.
- Public summary directory: counts, nullable FPR/TPR, limits, log/vector hashes.
  Only aggregate outputs may be committed. Never add raw ledgers/coordinates.
- A failed run keeps logs, returns nonzero, and records unattempted cases as
  `NOT_RUN`. Do not manufacture fallback CSV/figures when the environment fails.

The full field mapping and missing-value semantics are in
[schema/field-map.md](schema/field-map.md) and
[schema/observation.schema.json](schema/observation.schema.json).

## Checks and stage gates

```sh
python3 -m unittest discover -s experiments/week27-rid-sim/tests -v
python3 -m unittest discover -s uav -p 'test_*.py'
```

Also run `go test ./...` in `aggregator/` and `npm test` in `contracts/`.
Adapter tests use explicit synthetic unit fixtures and do not demonstrate a
simulator execution. GitHub Actions runs the adapter tests only.

PR1 success means **communication/spoofer plumbing**, not spoof detection.
All decisions are `UNDETERMINED`, scores/FPR/TPR are null. Packet-level physical
power changes (PR2), asynchronous regimes and non-identifiability (PR3), and
calibrated detection/figures (PR4) remain separate stages. Do not continue when
PR1 fails. Do not copy upstream-reported accuracy into our result tables.

Research report: [Week27 report 11](../../week27/11_uli_net_sim導入とRemoteID_RSSI位置偽装実験.md).

## PR2: per-packet physical power (after PR1 success)

The original `native/` extension uses upstream/INET public interfaces without
patching the local upstream checkout. No runtime mutability flag is relaxed:
`SignalPowerReq` accompanies each packet into the actual dimensional transmitter.
The PHY hook records packet IDs, tag presence, start time and computed power.
The old upstream parameter sample is not mistaken for dynamic actual power.

```sh
bash experiments/week27-rid-sim/scripts/build_power_extension.sh .cache/issue70
.cache/issue70/python/bin/python experiments/week27-rid-sim/scripts/run_power.py \
  --raw-dir captures/issue70-power-NEW \
  --out week27/results/uli-net-sim-power-NEW
```

`config/power.json` defines fixed, IID uniform, bounded slew and adaptive power,
plus physical controls. Position-only comparisons now preserve serial/time via
the base RID fill method. Adaptive knows the synthetic reference receiver,
true/claimed position and n=2; its +/-10dB compensation is additionally clamped
to [-80,23]dBm. It is **not** unbounded mathematical transmit power.

The 6dB control predicts total RSS including the configured background noise;
it does not require total RSS to increase by exactly 6dB. Receiver roles exclude
the extra transmitter from the observer set, while full raw vectors are kept.
Queues with no PHY hook by the horizon are distinct from a logged physical
transmission with no successful RX. All detection scores remain null and
decisions UNDETERMINED. These short controls do not establish FPR/TPR.

Report: [Week27 report 12](../../week27/12_パケット単位送信電力のPHY反映と通信対照実験.md).
