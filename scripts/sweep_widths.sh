#!/usr/bin/env bash
# Run a single cocotb testbench across several WIDTH values.
#
# Usage:
#   scripts/sweep_widths.sh <testbench-dir> <width> [<width> ...]
#
# Example:
#   scripts/sweep_widths.sh blocks/stocastic/verif/tb/test_binary_to_stochastic 2 3 4 8
#
# <testbench-dir> must contain a Makefile with a line matching
# `COMPILE_ARGS += -GWIDTH=<n>` (the convention every block's tb/*/Makefile
# in this repo already uses) -- that line is what gets rewritten per width.
#
# The Makefile is restored to its original contents on exit, including on
# failure or Ctrl-C.

set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "usage: $0 <testbench-dir> <width> [<width> ...]" >&2
  exit 2
fi

tb_dir=$1
shift
widths=("$@")

makefile="$tb_dir/Makefile"
if [[ ! -f "$makefile" ]]; then
  echo "error: $makefile not found" >&2
  exit 2
fi
if ! grep -qE '^COMPILE_ARGS \+= -GWIDTH=[0-9]+' "$makefile"; then
  echo "error: $makefile has no 'COMPILE_ARGS += -GWIDTH=<n>' line to sweep" >&2
  exit 2
fi

makefile_backup=$(mktemp)
cp "$makefile" "$makefile_backup"
restore_makefile() {
  cp "$makefile_backup" "$makefile"
  rm -f "$makefile_backup"
}
trap restore_makefile EXIT

declare -a results=()
overall_status=0

for width in "${widths[@]}"; do
  sed -i "s/-GWIDTH=[0-9]*/-GWIDTH=${width}/" "$makefile"
  rm -rf "$tb_dir/sim_build" "$tb_dir/__pycache__" "$tb_dir/results.xml" "$tb_dir/dump.vcd"

  echo "=== WIDTH=${width} ==="
  set +e
  out=$(cd "$tb_dir" && pixi run make 2>&1)
  status=$?
  set -e
  echo "$out" | grep -E "TESTS=|running .*\(|passed|failed|%Error" || true

  summary=$(echo "$out" | grep -oE "TESTS=[0-9]+ PASS=[0-9]+ FAIL=[0-9]+ SKIP=[0-9]+" | tail -1)
  if [[ -z "$summary" ]]; then
    summary="build/run error (exit $status)"
    overall_status=1
  elif [[ "$status" -ne 0 ]]; then
    overall_status=1
  fi
  results+=("WIDTH=${width}: ${summary}")

  rm -rf "$tb_dir/sim_build" "$tb_dir/__pycache__" "$tb_dir/results.xml" "$tb_dir/dump.vcd"
done

echo
echo "=== sweep summary: $tb_dir ==="
for line in "${results[@]}"; do
  echo "$line"
done

exit "$overall_status"
