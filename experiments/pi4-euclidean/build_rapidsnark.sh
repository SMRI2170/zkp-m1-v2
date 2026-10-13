#!/bin/sh
# Run through run_guarded.py inside week24.slice on Linux ARM64.
set -eu
cd "$1"
cmake -S . -B build_week24 -DTARGET_PLATFORM=aarch64 -DCMAKE_BUILD_TYPE=Release -DUSE_OPENMP=OFF
cmake --build build_week24 --target prover verifier --parallel 1
