"""Build native host and Linux ARM64 binaries with the same pinned source digest."""
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess

root = Path(__file__).resolve().parents[2]
source = Path(__file__).resolve().parent / "gnark"
output = root / ".cache/week24"
output.mkdir(parents=True, exist_ok=True)
h = hashlib.sha256()
source_files = {}
for name in ["main.go", "go.mod", "go.sum"]:
    data = (source / name).read_bytes()
    h.update(name.encode() + b"\0" + data)
    source_files[name] = hashlib.sha256(data).hexdigest()
source_digest = h.hexdigest()
host_os = {"Darwin": "darwin", "Linux": "linux"}[platform.system()]
host_arch = {"arm64": "arm64", "aarch64": "arm64", "x86_64": "amd64"}[platform.machine()]
binaries = {}
for target_os, target_arch in dict.fromkeys([(host_os, host_arch), ("linux", "arm64")]):
    name = f"euclidean-gnark-{target_os}-{target_arch}"
    subprocess.run(["go", "build", "-mod=readonly", "-trimpath", "-ldflags",
                    f"-X main.sourceDigest={source_digest}", "-o", str(output / name), "."],
                   cwd=source, env={**os.environ, "CGO_ENABLED": "0", "GOOS": target_os,
                                    "GOARCH": target_arch}, check=True)
    binaries[name] = hashlib.sha256((output / name).read_bytes()).hexdigest()
result = {"source_digest": source_digest, "source_sha256": source_files,
          "binary_sha256": binaries,
          "go": subprocess.check_output(["go", "version"], text=True).strip(),
          "cgo_enabled": False, "pi_proof_executed": False}
path = root / "week24/manifests/euclidean-gnark-build.json"
path.write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result))
