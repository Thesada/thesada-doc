#!/usr/bin/env bash

# allow-long-comment
# check-style.sh - two rules AGENTS.md already states but nothing enforced,
# so both drifted in by hand.
#
#   1. No em dashes or en dashes. Hyphens only. Strictest rule in the repo.
#   2. Never write "engineer" in published content (APEGA restriction).
#      consultant / developer / specialist instead.
#
# Usage: scripts/check-style.sh [path ...]   (default: tracked *.md)
# Exit 1 on any hit.

set -euo pipefail
cd "$(cd "$(dirname "$0")/.." && pwd)"

if [ $# -gt 0 ]; then
  files=("$@")
else
  # -f skips dangling symlinks: some pages point into a private repo and are
  # absent on a fresh checkout. grep would silently match nothing instead.
  files=()
  while IFS= read -r f; do
    if [ -f "$f" ]; then files+=("$f"); fi
  done < <(git ls-files '*.md')
fi

if [ ${#files[@]} -eq 0 ]; then
  echo "check-style: no readable markdown to check" >&2
  exit 1
fi

status=0

emdash=$(grep -nE $'—|–' "${files[@]}" 2>/dev/null || true)
if [ -n "$emdash" ]; then
  echo "check-style: em dash or en dash found. Hyphens only." >&2
  printf '%s\n' "$emdash" | sed 's/^/  /' >&2
  status=1
fi

# Word-boundary, so a quoted upstream title trips it too. Deliberate: the
# reviewer decides, the gate does not guess.
engineer=$(grep -nEi '\bengineer' "${files[@]}" 2>/dev/null || true)
if [ -n "$engineer" ]; then
  echo "check-style: 'engineer' in published content. Use consultant / developer / specialist." >&2
  printf '%s\n' "$engineer" | sed 's/^/  /' >&2
  status=1
fi

[ "$status" -eq 0 ] && echo "check-style: ok (${#files[@]} file(s))"
exit "$status"
