#!/usr/bin/env bash
# Create or verify a signed-release-friendly SHA-256 manifest for Groth16
# artifacts.  The manifest contains no proving key material; it names hashes
# only, so it can safely be committed or attached to a GitHub Release.
set -euo pipefail

usage() {
  cat <<'EOF'
usage:
  scripts/zk_artifact_manifest.sh create <manifest.json> <artifact>...
  scripts/zk_artifact_manifest.sh verify <manifest.json>

The paths recorded by `create` are relative to the repository root. Run this
command from the repository root, or pass paths below it.
EOF
}

[[ $# -ge 2 ]] || { usage >&2; exit 2; }
command="$1"
manifest="$2"
shift 2

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

case "$command" in
  create)
    [[ $# -gt 0 ]] || { echo "at least one artifact is required" >&2; exit 2; }
    node - "$root_dir" "$manifest" "$@" <<'NODE'
const crypto = require("crypto");
const fs = require("fs");
const path = require("path");
const [root, out, ...inputFiles] = process.argv.slice(2);
const files = inputFiles.map((input) => {
  const absolute = path.resolve(input);
  const relative = path.relative(root, absolute);
  if (relative.startsWith("..") || path.isAbsolute(relative)) {
    throw new Error(`artifact is outside repository: ${input}`);
  }
  const data = fs.readFileSync(absolute);
  return {
    path: relative.split(path.sep).join("/"),
    bytes: data.length,
    sha256: crypto.createHash("sha256").update(data).digest("hex"),
  };
});
fs.mkdirSync(path.dirname(out), { recursive: true });
fs.writeFileSync(out, `${JSON.stringify({
  format: "zkp-m1-artifact-manifest-v1",
  generatedAt: new Date().toISOString(),
  files,
}, null, 2)}\n`);
NODE
    ;;
  verify)
    [[ $# -eq 0 ]] || { usage >&2; exit 2; }
    node - "$root_dir" "$manifest" <<'NODE'
const crypto = require("crypto");
const fs = require("fs");
const path = require("path");
const [root, manifestPath] = process.argv.slice(2);
const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
if (manifest.format !== "zkp-m1-artifact-manifest-v1" || !Array.isArray(manifest.files)) {
  throw new Error("unsupported manifest format");
}
for (const entry of manifest.files) {
  const target = path.resolve(root, entry.path);
  const relative = path.relative(root, target);
  if (relative.startsWith("..") || path.isAbsolute(relative)) throw new Error(`unsafe path: ${entry.path}`);
  const data = fs.readFileSync(target);
  const actual = crypto.createHash("sha256").update(data).digest("hex");
  if (actual !== entry.sha256 || data.length !== entry.bytes) {
    throw new Error(`artifact mismatch: ${entry.path}`);
  }
  process.stdout.write(`verified ${entry.path}\n`);
}
NODE
    ;;
  *) usage >&2; exit 2 ;;
esac
