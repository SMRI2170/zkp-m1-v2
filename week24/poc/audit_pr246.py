"""Audit a pinned public source archive; does not generate or read private proofs."""
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
SHA = "9c4e61f8d1a5be87c00f28838a0ef657a3cf479f"
source = ROOT / ".cache/week23/sources/sonobe-hypernova-9c4e61f8"
refs = ROOT / ".cache/week24/references"
pr = json.loads((refs / "pr246.json").read_text())
tree = json.loads((refs / "pr246-tree.json").read_text())
assert pr["head"]["sha"] == SHA, "PR head changed; inspect before updating the pinned audit"
assert tree["sha"] == SHA and not tree["truncated"]
entries = [e for e in tree["tree"] if e["type"] == "blob"
           and (e["path"].startswith("crates/") or e["path"] == "Cargo.toml")]
hashes = {}
rust = {}
for entry in entries:
    path = source / entry["path"]
    data = path.read_bytes()
    git_hash = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
    assert git_hash == entry["sha"], f"Upstream archive mismatch: {entry['path']}"
    hashes[entry["path"]] = hashlib.sha256(data).hexdigest()
    if path.suffix == ".rs":
        rust[entry["path"]] = data.decode()
all_remote_rust = [e["path"] for e in tree["tree"] if e["type"] == "blob" and e["path"].endswith(".rs")]
assert set(all_remote_rust) == set(rust), "Rust code outside scanned crates; extend audit scope"
deciders = [p for p, text in rust.items()
            if re.search(r"\bimpl\b[^{};]*\bDecider\b[^{};]*\bfor\b", text, re.S)]
named_blindfold = [p for p, text in rust.items() if "NovaBlindFold" in text]
assert not deciders and not named_blindfold, "Source findings changed; inspect implementations"
ivc = rust["crates/ivc/src/lib.rs"]
assert "Still WIP" in ivc and "pub trait Decider" in ivc
assert "FS1::decide_incoming(dk1, w, u)?" in rust["crates/ivc/src/compilers/cyclefold/mod.rs"]
patch = ROOT / "week23/poc/sonobe-current/hypernova-ark06.patch"
lock = ROOT / "week23/poc/sonobe-current/hypernova.Cargo.lock"
result = {
    "checked_on": "2026-10-13",
    "pr": {"url": pr["html_url"], "state": pr["state"], "draft": pr["draft"],
           "merged": pr["merged"], "updated_at": pr["updated_at"],
           "base_sha": pr["base"]["sha"], "base_ref": pr["base"]["ref"],
           "head_sha": SHA, "head_ref": pr["head"]["ref"]},
    "archive_verified_files": len(entries), "all_rust_files_scanned": len(rust),
    "ivc_final_decider_impl_text_matches": deciders,
    "nova_blindfold_name_text_matches": named_blindfold,
    "scan_limit": "Text/source inspection, not a proof of absence of every equivalent algorithm or an audit",
    "upstream_source_sha256": hashes,
    "reused_patch_sha256": hashlib.sha256(patch.read_bytes()).hexdigest(),
    "reused_lock_sha256": hashlib.sha256(lock.read_bytes()).hexdigest(),
    "paper": {"metadata_url": "https://eprint.iacr.org/2023/573",
              "metadata_last_revision": "2026-02-20", "metadata_revision_count": 5,
              "pdf_url": "https://eprint.iacr.org/2023/573.pdf", "pdf_http_status": 403,
              "pdf_retrieved": False, "section7_appendixD_fulltext_checked": False},
    "new_proof_execution": False, "new_pi_measurement": False,
    "reused_evidence": ["week23/logs/hypernova-fixed-tests.log",
                        "week23/logs/hypernova-execution.json",
                        "week23/logs/hypernova-ivc-tests.log",
                        "week23/logs/hypernova-handoff-probe.json"],
}
output = ROOT / "week24/manifests/pr246-source-audit.json"
output.write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps({"verified_files": len(entries), "rust_files": len(rust),
                  "ivc_decider_impl_matches": len(deciders), "pdf_fulltext_checked": False}))
