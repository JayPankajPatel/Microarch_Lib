#!/usr/bin/env bash
# Run every cocotb testbench in the repo (blocks/*/verif/tb/*/Makefile) once
# each at its default (Makefile-declared) parameters, and report a pass/fail
# summary across all of them.
#
# Usage:
#   scripts/run_regression.sh
#
# Exits non-zero if any testbench fails to build or has a failing test, so
# this is safe to wire into CI later.

set -euo pipefail

repo_root=$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)
cd "$repo_root"

mapfile -t tb_dirs < <(find blocks -path '*/verif/tb/*/Makefile' -exec dirname {} \; | sort)

if [[ ${#tb_dirs[@]} -eq 0 ]]; then
  echo "no testbenches found under blocks/*/verif/tb/*/Makefile" >&2
  exit 2
fi

declare -a results=()
overall_status=0

for tb_dir in "${tb_dirs[@]}"; do
  echo "=== $tb_dir ==="
  rm -rf "$tb_dir/sim_build" "$tb_dir/__pycache__" "$tb_dir/results.xml" "$tb_dir/dump.vcd"

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
  results+=("$tb_dir: $summary")

  rm -rf "$tb_dir/sim_build" "$tb_dir/__pycache__" "$tb_dir/results.xml" "$tb_dir/dump.vcd"
  echo
done

echo "=== regression summary ==="
for line in "${results[@]}"; do
  echo "$line"
done

exit "$overall_status"
