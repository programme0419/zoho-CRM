#!/usr/bin/env bash
# Local grading matrix for refcalc-clone (no Docker required).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
python3 "$ROOT/scripts/refcalc/verify_local.py"
