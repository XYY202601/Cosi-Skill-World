#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

targets=(apps packages services domains)
patterns=(
  'references/(hermes-agent|deeptutor)'
  '\bfrom[[:space:]]+references(\.[[:alnum:]_]+)*\b'
  '\bimport[[:space:]]+references(\.[[:alnum:]_]+)*\b'
)
globs=(
  -g '*.py'
  -g '*.ts'
  -g '*.tsx'
  -g '*.js'
  -g '*.jsx'
  -g '*.sh'
  -g '*.json'
  -g '*.yaml'
  -g '*.yml'
)

if command -v rg >/dev/null 2>&1; then
  if rg -n --color=never "${globs[@]}" "${patterns[0]}" "${targets[@]}" \
    || rg -n --color=never "${globs[@]}" "${patterns[1]}" "${targets[@]}" \
    || rg -n --color=never "${globs[@]}" "${patterns[2]}" "${targets[@]}"; then
    echo "[check-no-reference-imports] forbidden reference coupling found"
    exit 1
  fi
else
  mapfile -t candidate_files < <(
    find "${targets[@]}" -type f \( \
      -name '*.py' -o \
      -name '*.ts' -o \
      -name '*.tsx' -o \
      -name '*.js' -o \
      -name '*.jsx' -o \
      -name '*.sh' -o \
      -name '*.json' -o \
      -name '*.yaml' -o \
      -name '*.yml' \
    \)
  )
  if ((${#candidate_files[@]} > 0)) && grep -nE "${patterns[0]}|${patterns[1]}|${patterns[2]}" "${candidate_files[@]}"; then
    echo "[check-no-reference-imports] forbidden reference coupling found"
    exit 1
  fi
fi

echo "[check-no-reference-imports] ok"
