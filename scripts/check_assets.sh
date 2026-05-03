#!/usr/bin/env bash
# Run full pipeline (C2PA + Titan + Google) on every file in assets/.
# Set AWS credentials, GOOGLE_CLOUD_PROJECT, and: pip install -e ".[google]"
set -euo pipefail
export PYTHONUNBUFFERED=1
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="$ROOT/.venv/bin:$PATH"
for img in "$ROOT/assets"/*.*; do
  [[ -f "$img" ]] || continue
  echo "======== $(basename "$img") ========" >&2
  mendacity-check "$img" --json --titan --google
  echo >&2
done
