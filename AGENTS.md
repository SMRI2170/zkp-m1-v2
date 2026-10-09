# AI development rules

This repository contains a research PoC for aggregating Remote ID observations.
Do not describe it as a production safety or aircraft-authentication system.

- Keep the boundary explicit: V2 currently groups a claimed RID and verifies
  observer-signed statements; it does not verify a DRIP trust chain, prove
  sensor honesty, or authenticate observer hardware.
- Never add real capture JSONL, truth ledgers, coordinates, session keys, or
  private observer keys to Git. Field data belongs in ignored `captures/` or
  `uav/captures/` directories and must retain owner-only permissions.
- Disposable single-contributor Groth16 setup outputs are test fixtures, never
  release keys. Never publish/deploy their `.ptau`, `.zkey`, VK, or proofs.
- Keep local `pcd3` setup/proof-cache artifacts out of Git. Proof caches include
  linkable public witnesses; the complete private assignment is never cached.
- A `pcd3 --stage=plan` pass is host preflight only. Claim the recursive/final
  path works only after generating the current-version recursive proofs and
  verifying the resulting FinalBNV2 proof in the EVM harness.
- The recursive `--stage=run` setup is resource-intensive. Check available
  memory and swap first; use an approved high-memory runner when the local host
  lacks safe headroom. Preserve private fixtures deliberately for resume.
- `pcd3` reuses setup caches only when source/dependency metadata and all
  artifact hashes verify. Incomplete or mismatched cache directories are
  preserved, not silently reused or deleted; inspect them before cleanup.
- Do not weaken circuits, tests, policy checks, or security controls merely to
  obtain a green result. Report suspected false positives instead of adding
  silent ignores.

For relevant changes, run the existing checks:

```sh
python3 -m unittest discover -s uav -p 'test_*.py'
cd aggregator && go test ./...
cd contracts && npm test
```

The slower Flutter/Pi synthetic proof integration is documented in
`uav/OBSERVER_CAPTURE.md`. It uses test-only keys and fake BLE input; it is not
field evidence. When a task includes publishing changes, follow
implementation → local checks → commit/push → GitHub Actions result/log review
→ root-cause fix, with at most three repair cycles.
