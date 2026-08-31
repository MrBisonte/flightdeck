#!/usr/bin/env bash
# Generic credential scan over tracked files. Runs in CI.
#
# Deliberately generic: credential shapes only, no project names and no
# personal data. A scanner that hardcodes the strings it suppresses would
# publish exactly what it is meant to keep out.
set -uo pipefail

cd "$(git rev-parse --show-toplevel)" || exit 2

SECRETS='AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|password[[:space:]]*=[[:space:]]*["'"'"'][^"'"'"'$]{6,}'

hits=$(git ls-files -z | xargs -0 grep -InIE "$SECRETS" 2>/dev/null || true)
if [ -n "$hits" ]; then
  echo "FAIL  credential shapes found in tracked files:"
  echo "$hits" | sed 's/^/      /'
  exit 1
fi
echo "ok    no credential shapes in $(git ls-files | wc -l) tracked files"
