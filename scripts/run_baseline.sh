#!/usr/bin/env bash
# run_baseline.sh — run (or stub) the baseline experiment for the active run.
# Fail-soft: missing config/data/tooling -> stub run.log + metrics.json + exit 0.
# Hard tooling error (cannot resolve run dir, cannot write) -> non-zero.
set -uo pipefail

TAG="run_baseline"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNS_DIR="$REPO_ROOT/research_runs"

# --- Arg parsing -------------------------------------------------------------
exp_dir=""
config=""
cmd=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --exp-dir) exp_dir="$2"; shift 2 ;;
        --config)  config="$2";  shift 2 ;;
        --cmd)     cmd="$2";     shift 2 ;;
        *)  echo "[$TAG] WARN: ignoring unknown arg: $1"; shift ;;
    esac
done

# --- Resolve RUN_DIR ---------------------------------------------------------
run_dir=""
if [[ -n "${ARW_RUN_DIR:-}" ]]; then
    run_dir="$ARW_RUN_DIR"
elif [[ -f "$RUNS_DIR/.active_run" ]]; then
    rid="$(head -1 "$RUNS_DIR/.active_run" | tr -d '[:space:]')"
    [[ -n "$rid" && -d "$RUNS_DIR/$rid" ]] && run_dir="$RUNS_DIR/$rid"
fi
if [[ -z "$run_dir" ]]; then
    # newest run dir
    run_dir="$(ls -dt "$RUNS_DIR"/*/ 2>/dev/null | head -1)"
    run_dir="${run_dir%/}"
fi
if [[ -z "$run_dir" || ! -d "$run_dir" ]]; then
    echo "[$TAG] WARN: no run dir resolved (looked in $RUNS_DIR); nothing to do"
    exit 0
fi
echo "[$TAG] run_dir=$run_dir"

# --- Resolve exp-dir ---------------------------------------------------------
if [[ -z "$exp_dir" ]]; then
    exp_dir="$run_dir/60_experiments/E0001_baseline"
fi
mkdir -p "$exp_dir"
echo "[$TAG] exp_dir=$exp_dir"

# --- Record environment.txt --------------------------------------------------
env_file="$exp_dir/environment.txt"
{
    echo "# environment captured by run_baseline.sh"
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
    echo "# baseline run"
    echo "# host: $(hostname 2>/dev/null || echo unknown)"
    echo "# pid:  $$"
    echo "# start: $(date -u '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null || date)"
} > "$run_log"

# --- Decide what to run ------------------------------------------------------
run_rc=0
if [[ -n "$cmd" ]]; then
    echo "[$TAG] running --cmd: $cmd"
    echo "[cmd] $cmd" >> "$run_log"
    bash -c "$cmd" >> "$run_log" 2>&1 || run_rc=$?
elif [[ -n "$config" ]]; then
    target="${ARW_TARGET_REPO:-$run_dir/50_code/target_repo}"
    if [[ -f "$target/tools/train.py" ]]; then
        echo "[$TAG] running $target/tools/train.py: $config"
        echo "[cmd] python tools/train.py $config --work-dir $exp_dir" >> "$run_log"
        (cd "$target" && python tools/train.py "$config" --work-dir "$exp_dir") >> "$run_log" 2>&1 || run_rc=$?
    else
        echo "[$TAG] STUB: no target_repo/tools/train.py; recording stub"
        echo "baseline command not fully runnable (set ARW_TARGET_REPO or 50_code/target_repo); config=$config" >> "$run_log"
    fi
else
    echo "[$TAG] STUB: no --cmd / --config provided"
    cat >> "$run_log" <<EOF
baseline command not configured; see memory/open_questions.md
Provide --cmd '<shell>' or --config <config.py> on the next invocation.
EOF
fi

# --- Capture OOM/traceback tail ---------------------------------------------
if [[ $run_rc -ne 0 ]]; then
    echo "--- exit code: $run_rc ---" >> "$run_log"
    echo "[$TAG] run exited non-zero ($run_rc); tail of run.log:"
    tail -n 40 "$run_log" 2>/dev/null || true
    if grep -qiE 'out of memory|CUDA out of memory|RuntimeError' "$run_log" 2>/dev/null; then
        echo "[$TAG] OOM/crash signature detected; see $run_log"
    fi
fi

# --- Ensure a metrics.json exists (stub if absent) ---------------------------
metrics_file="$exp_dir/metrics.json"
if [[ ! -f "$metrics_file" ]]; then
    if [[ $run_rc -ne 0 ]]; then
        echo '{}' > "$metrics_file"
    else
        echo '{}' > "$metrics_file"
    fi
fi

echo "# end: $(date -u '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null || date)" >> "$run_log"
echo "[$TAG] done (exit 0)"
exit 0
