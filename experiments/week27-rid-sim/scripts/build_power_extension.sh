#!/usr/bin/env bash
set -e
package="$(cd "$(dirname "$0")/.." && pwd)"
workspace="$(cd "$1" && pwd)"
extension="$package/native"
repository="$(cd "$package/../.." && pwd)"
case "$workspace/" in
    "$repository/.cache/"*) ;;
    *) echo 'Keep dependencies and binaries inside ignored .cache/' >&2; exit 2 ;;
esac
test -d "$extension"
expected_sha="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["uli_net_sim"]["sha"])' "$package/upstream.lock.json")"
test "$(git -C "$workspace/uli-net-sim" rev-parse HEAD)" = "$expected_sha"
test -z "$(git -C "$workspace/uli-net-sim" status --porcelain)"
if [[ ! -e "$workspace/project-build/power_extension" ]]; then
    ln -s "$extension" "$workspace/project-build/power_extension"
fi
test -L "$workspace/project-build/power_extension"
test "$(readlink "$workspace/project-build/power_extension")" = "$extension"
bash "$package/scripts/build_headless.sh" "$workspace" 2 project
