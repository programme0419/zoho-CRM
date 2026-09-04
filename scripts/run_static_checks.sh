#!/usr/bin/env bash
# Run the Terminal-Bench 3 static checks that CI executes on every push.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
TASK="${1:-tasks/scan-margin}"
FAILED=0
for check in "$ROOT"/scripts/checks/check-*.sh; do
  echo "===== $(basename "$check") ====="
  if ! bash "$check" "$TASK"; then
    echo "FAILED $(basename "$check")"
    FAILED=1
  fi
done
if [ "$FAILED" -ne 0 ]; then
  echo "Static checks failed"
  exit 1
fi
echo "All static checks passed"
