#!/usr/bin/env bash
# Resolve this repo's root from the hook script location (cwd-independent) and
# exec a scripts/*.py or *.sh. Usage: bash scripts/arw_hook.sh hook_guard.py
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export ARW_ROOT="$ROOT"
if [[ $# -lt 1 ]]; then
  echo "[arw_hook] usage: arw_hook.sh <script.py|script.sh> [args...]" >&2
  exit 2
fi
target="$1"
shift
case "$target" in
  *.py) exec python3 "$ROOT/scripts/$target" "$@" ;;
  *.sh) exec bash "$ROOT/scripts/$target" "$@" ;;
  *)    exec python3 "$ROOT/scripts/$target" "$@" ;;
esac
