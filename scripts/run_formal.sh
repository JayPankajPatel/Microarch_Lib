#!/usr/bin/env bash
# Run every SymbiYosys proof in the repo (blocks/*/verif/formal/*/*.sby) via
# the `pixi run formal` task, and report a pass/fail summary across all of them.
#
# Usage:
#   scripts/run_formal.sh
#
# Exits non-zero if any proof fails or errors, so it can gate CI.

set -euo pipefail

repo_root=$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)
cd "$repo_root"

mapfile -t sby_files < <(find blocks -path '*/verif/formal/*/*.sby' | sort)

if [[ ${#sby_files[@]} -eq 0 ]]; then
  echo "no proofs found under blocks/*/verif/formal/*/*.sby" >&2
  exit 1
fi

overall_status=0
results=()

for sby in "${sby_files[@]}"; do
  echo "=== $sby ==="
  set +e
  out=$(pixi run formal "$sby" 2>&1)
  status=$?
  set -e
  echo "$out" | grep -E "DONE|ERROR|FAIL" || true

  if [[ "$status" -ne 0 ]]; then
    overall_status=1
    results+=("$sby: FAIL (exit $status)")
  else
    results+=("$sby: PASS")
  fi
  echo
done

echo "=== formal summary ==="
for line in "${results[@]}"; do
  echo "$line"
done

exit "$overall_status"
