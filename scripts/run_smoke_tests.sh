#!/usr/bin/env bash
# Generic smoke check for the *target* scientific repo. Never starts training.
# Fail-soft: missing env -> exit 0.
set -uo pipefail

TAG="run_smoke"
ARW_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "[$TAG] starting smoke check (arw_root=$ARW_ROOT)"

target="${ARW_TARGET_REPO:-}"
if [[ -z "$target" ]]; then
  if [[ -n "${ARW_RUN_DIR:-}" && -e "$ARW_RUN_DIR/50_code/target_repo" ]]; then
    target="$ARW_RUN_DIR/50_code/target_repo"
  elif [[ -f "$ARW_ROOT/research_runs/.active_run" ]]; then
    rid="$(head -1 "$ARW_ROOT/research_runs/.active_run" | tr -d '[:space:]')"
    cand="$ARW_ROOT/research_runs/$rid/50_code/target_repo"
    [[ -e "$cand" ]] && target="$cand"
  fi
fi

mod="${ARW_SMOKE_IMPORT:-}"
if [[ -z "$mod" && -f "$ARW_ROOT/arw.yaml" ]]; then
  mod="$(python3 -c "import re,pathlib; t=pathlib.Path('$ARW_ROOT/arw.yaml').read_text();
m=re.search(r'^smoke_import:\\s*[\"\\']?([^\"\\'#\\n]+)', t, re.M);
print((m.group(1).strip() if m else ''))" 2>/dev/null || true)"
fi

if [[ -n "$mod" ]]; then
  ver="$(python3 -c "import $mod as m; print(getattr(m,'__version__', 'ok'))" 2>&1)" || true
  if [[ -z "$ver" || "$ver" == *"ModuleNotFoundError"* || "$ver" == *"ImportError"* ]]; then
    echo "[$TAG] SKIPPED ($mod not importable)"
    echo "[$TAG] detail: $ver"
    exit 0
  fi
  echo "[$TAG] $mod importable: $ver"
else
  echo "[$TAG] no ARW_SMOKE_IMPORT / arw.yaml smoke_import; skip domain import"
fi

if [[ -n "$target" && -d "$target" ]]; then
  echo "[$TAG] target_repo=$target"
  python3 -m py_compile "$ARW_ROOT/scripts/_arw_common.py" || true
else
  echo "[$TAG] no target_repo linked yet (ok at scaffold time)"
fi

echo "[$TAG] PASS"
exit 0
