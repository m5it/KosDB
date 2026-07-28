#!/usr/bin/env bash
set -euo pipefail

BASE_REF="${1:-master}"
HEAD_REF="${2:-HEAD}"
EXPECTED_FILE="${3:-FILELISTMADSORTINTEGRATION}"

if [[ ! -f "$EXPECTED_FILE" ]]; then
  echo "ERROR: expected file list not found: $EXPECTED_FILE"
  exit 2
fi

tmp_changed="$(mktemp)"
tmp_expected="$(mktemp)"
trap 'rm -f "$tmp_changed" "$tmp_expected"' EXIT

# Collect changed files between refs
git diff --name-only "${BASE_REF}...${HEAD_REF}" | sed '/^\s*$/d' | sort > "$tmp_changed"

# Normalize expected file list:
# - drop comments and blank lines
sed -e 's/#.*$//' -e '/^\s*$/d' "$EXPECTED_FILE" | sort > "$tmp_expected"

echo "=== madsort integration filelist check ==="
echo "Base ref : $BASE_REF"
echo "Head ref : $HEAD_REF"
echo "Expected : $EXPECTED_FILE"
echo

echo "---- Unexpected files (must be empty) ----"
unexpected="$(comm -23 "$tmp_changed" "$tmp_expected" || true)"
if [[ -n "$unexpected" ]]; then
  echo "$unexpected"
else
  echo "(none)"
fi
echo

echo "---- Missing expected files (review) ----"
missing="$(comm -13 "$tmp_changed" "$tmp_expected" || true)"
if [[ -n "$missing" ]]; then
  echo "$missing"
else
  echo "(none)"
fi
echo

if [[ -n "$unexpected" ]]; then
  echo "RESULT: FAIL (unexpected files detected)"
  exit 1
fi

echo "RESULT: PASS"
exit 0
