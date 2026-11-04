#!/bin/sh
set -eu
TASK_ROOT=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
TASK_BUILD="$TASK_ROOT/build/host-tests"
mkdir -p "$TASK_BUILD"
javac -d "$TASK_BUILD" "$TASK_ROOT/app/src/main/java/org/smri/ridprobe/RadioMath.java" "$TASK_ROOT/tests/RadioMathTest.java"
java -cp "$TASK_BUILD" org.smri.ridprobe.RadioMathTest
