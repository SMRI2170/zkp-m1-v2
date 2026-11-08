#!/usr/bin/env bash
set -euo pipefail
# Third-party dependency stays ignored. Do not execute MATLAB or publish raw.
workspace="${1:-.cache/dataset21-geometry}"
case "$workspace" in .cache/*) ;; *) echo 'Use a .cache/ workspace' >&2; exit 2;; esac
mkdir -p "$workspace"
revision=dd49527c70d2aef0e0947ee4b8e9ed2b347a5ba0
checkout="$workspace/data-explorer-core"
if [ ! -d "$checkout/.git" ]; then
  git init "$checkout"
  git -C "$checkout" remote add origin https://github.com/mathworks/data-explorer-core.git
  git -C "$checkout" fetch --depth 1 origin "$revision"
  git -C "$checkout" checkout --detach FETCH_HEAD
fi
test "$(git -C "$checkout" rev-parse HEAD)" = "$revision"
npm install --prefix "$checkout" --ignore-scripts --omit=dev --no-audit --no-fund
cat > "$workspace/bridge.ts" <<'EOF'
export {parseMat} from './data-explorer-core/src/datamodel/parser/MatParser.js';
export {decodeMcosVariables} from './data-explorer-core/src/datamodel/parser/McosParser.js';
EOF
npm exec --yes --package=esbuild@0.25.10 -- esbuild "$workspace/bridge.ts" --bundle --platform=node --format=esm --outfile="$workspace/bridge.mjs"
