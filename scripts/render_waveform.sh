#!/usr/bin/env bash
# Render a wavedrom JSON timing-diagram source to SVG.
#
# Usage:
#   scripts/render_waveform.sh <path/to/diagram.json> [output.svg]
#
# If no output path is given, writes next to the source with a .svg
# extension (e.g. foo.json -> foo.svg). Diagram sources live under
# blocks/<name>/docs/waveforms/; both the .json source and its rendered
# .svg are committed (see CLAUDE.md's block layout convention) -- re-run
# this after editing a .json to refresh its .svg before committing.

set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <path/to/diagram.json> [output.svg]" >&2
  exit 2
fi

input=$1
if [[ ! -f "$input" ]]; then
  echo "error: $input not found" >&2
  exit 2
fi

output=${2:-"${input%.json}.svg"}

repo_root=$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)
wavedrompy="$repo_root/.pixi/envs/default/bin/wavedrompy"
if [[ ! -x "$wavedrompy" ]]; then
  echo "error: $wavedrompy not found -- run 'pixi install' first" >&2
  exit 2
fi

"$wavedrompy" --input "$input" --svg "$output"
echo "wrote $output"
