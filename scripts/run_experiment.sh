#!/usr/bin/env bash
# run_experiment.sh — run (or stub) experiment E000X for the active run.
# Fail-soft: missing command.sh / config / data -> stub run.log + exit 0.
set -uo pipefail

TAG="run_experiment"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNS_DIR="$REPO_ROOT/research_runs"

# --- Arg parsing -------------------------------------------------------------
eid=""
exp_dir=""
cmd=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --eid)     eid="$2";     shift 2 ;;
        --exp-dir) exp_dir="$2"; shift 2 ;;
        --cmd)     cmd="$2";     shift 2 ;;
        *)  echo "[$TAG] WARN: ignoring unknown arg: $1"; shift ;;
    esac
done

if [[ -z "$eid" ]]; then
    echo "[$TAG] WARN: --eid E000X is required"
    exit 0
fi
echo "[$TAG] eid=$eid"

# --- Resolve RUN_DIR ---------------------------------------------------------
run_dir=""
if [[ -n "${ARW_RUN_DIR:-}" ]]; then
    run_dir="$ARW_RUN_DIR"
elif [[ -f "$RUNS_DIR/.active_run" ]]; then
    rid="$(head -1 "$RUNS_DIR/.active_run" | tr -d '[:space:]')"
    [[ -n "$rid" && -d "$RUNS_DIR/$rid" ]] && run_dir="$RUNS_DIR/$rid"
fi
if [[ -z "$run_dir" ]]; then
    run_dir="$(ls -dt "$RUNS_DIR"/*/ 2>/dev/null | head -1)"
    run_dir="${run_dir%/}"
fi
if [[ -z "$run_dir" || ! -d "$run_dir" ]]; then
    echo "[$TAG] WARN: no run dir resolved; cannot place experiment"
    exit 0
fi
echo "[$TAG] run_dir=$run_dir"

# --- Resolve exp-dir (existing E000X_* match, else create E000X_run) ---------
if [[ -z "$exp_dir" ]]; then
    # First matching dir under 60_experiments starting with EID.
    exp_dir="$(find "$run_dir/60_experiments" -maxdepth 1 -type d -name "${eid}_*" 2>/dev/null | head -1)"
    if [[ -z "$exp_dir" ]]; then
        exp_dir="$run_dir/60_experiments/${eid}_run"
    fi
fi
mkdir -p "$exp_dir"
echo "[$TAG] exp_dir=$exp_dir"

# --- Record environment.txt --------------------------------------------------
env_file="$exp_dir/environment.txt"
{
    echo "# environment captured by run_experiment.sh"
    echo "eid: $eid"
    echo "date: $(date -u '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null || date)"
    echo "python: $(python --version 2>&1)"
    echo "--- pip freeze (head -200) ---"
    pip freeze 2>/dev/null | head -200
    echo "--- gpus ---"
    nvidia-smi -L 2>/dev/null || echo "no-gpu"
} > "$env_file" 2>&1
echo "[$TAG] wrote $env_file"

# --- Header for run.log ------------------------------------------------------
run_log="$exp_dir/run.log"
{
    echo "# experiment $eid"
    echo "# host: $(hostname 2>/dev/null || echo unknown)"
    echo "# pid:  $$"
    echo "# start: $(date -u '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null || date)"
} > "$run_log"

# --- Decide what to run ------------------------------------------------------
command_sh="$exp_dir/command.sh"
run_rc=0
ran=0
if [[ -f "$command_sh" && -x "$command_sh" ]]; then
    echo "[$TAG] running executable command.sh"
    echo "[cmd] bash command.sh" >> "$run_log"
    (cd "$exp_dir" && bash command.sh) >> "$run_log" 2>&1 || run_rc=$?
    ran=1
elif [[ -n "$cmd" ]]; then
    echo "[$TAG] running --cmd"
    echo "[cmd] $cmd" >> "$run_log"
    bash -c "$cmd" >> "$run_log" 2>&1 || run_rc=$?
    ran=1
else
    echo "[$TAG] STUB: no command.sh / --cmd"
    cat >> "$run_log" <<EOF
experiment command not configured
To run this experiment, either:
  - create an executable $command_sh , or
  - re-invoke with --cmd '<shell command>'
EOF
fi

# --- Capture OOM/traceback tail ---------------------------------------------
if [[ $ran -eq 1 && $run_rc -ne 0 ]]; then
    echo "--- exit code: $run_rc ---" >> "$run_log"
    echo "[$TAG] run exited non-zero ($run_rc); tail of run.log:"
    tail -n 40 "$run_log" 2>/dev/null || true
    if grep -qiE 'out of memory|CUDA out of memory|RuntimeError|FileNotFoundError|No such file' "$run_log" 2>/dev/null; then
        echo "[$TAG] crash/missing-config signature detected; recorded in run.log"
    fi
fi

# --- Ensure metrics.json exists (stub) --------------------------------------
metrics_file="$exp_dir/metrics.json"
[[ -f "$metrics_file" ]] || echo '{}' > "$metrics_file"

echo "# end: $(date -u '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null || date)" >> "$run_log"
echo "[$TAG] done (exit 0)"
exit 0
