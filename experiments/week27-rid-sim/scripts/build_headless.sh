#!/usr/bin/env bash
# Build local, unmodified dependencies. No downloaded source is redistributed.
set -e
workspace="$(cd "$1" && pwd)"
jobs="${2:-2}"
if [[ "$jobs" != 1 && "$jobs" != 2 ]]; then
    echo 'Use 1 or 2 build jobs on this research runner.' >&2
    exit 2
fi
upstream="$workspace/uli-net-sim"
source "$workspace/omnetpp-6.2.0/setenv" -q
source "$workspace/inet4.5/setenv" -q
export VIRTUAL_ENV="$workspace/python"
export PATH="$VIRTUAL_ENV/bin:$PATH"
make_cmd=make
if command -v gmake >/dev/null; then make_cmd=gmake; fi

if [[ "${3:-all}" != project ]]; then
    cd "$workspace/omnetpp-6.2.0"
    cat > configure.user <<'EOF'
WITH_QTENV=no
WITH_OSG=yes
WITH_OSGEARTH=no
WITH_NETBUILDER=yes
WITH_SCAVE_PYTHON_BINDINGS=no
WITH_LIBXML=no
EOF
    ./configure
    "$make_cmd" MODE=release -j"$jobs"

    cd "$workspace/inet4.5"
    opp_featuretool disable VisualizationOsg
    "$make_cmd" makefiles
    "$make_cmd" MODE=release -j"$jobs"
fi

mkdir -p "$workspace/project-build"
cd "$workspace/project-build"
if [[ ! -e src ]]; then ln -s "$upstream/src" src; fi
opp_makemake -f --deep -o rid_smoke -O out -DINET_IMPORT \
    -DPROJ_DIR="$upstream" -Isrc -I"$workspace/inet4.5/src" \
    -I"$workspace/eigen-5.0.0" -L"$workspace/inet4.5/src" -lINET
# All original modules are compiled. OSG libraries are required by upstream
# even for CLI use; no display server or Qtenv is needed at runtime.
cat >> Makefile <<'EOF'

include src/makefrag
EOF
"$make_cmd" MODE=release -j"$jobs"
