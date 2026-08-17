#!/usr/bin/env bash
# package_artifacts.sh — gather per-experiment artifacts into 90_package/ and write
# artifact_manifest.json. Fail-soft: no experiments -> empty manifest + exit 0.
set -uo pipefail

TAG="package"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNS_DIR="$REPO_ROOT/research_runs"

# --- Arg parsing -------------------------------------------------------------
run_dir=""
eid=""
out_rel="90_package"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --run-dir) run_dir="$2"; shift 2 ;;
        --eid)     eid="$2";     shift 2 ;;
        --out)     out_rel="$2"; shift 2 ;;
        *)  echo "[$TAG] WARN: ignoring unknown arg: $1"; shift ;;
    esac
done

# --- Resolve RUN_DIR ---------------------------------------------------------
if [[ -z "$run_dir" ]]; then
    if [[ -n "${ARW_RUN_DIR:-}" ]]; then
        run_dir="$ARW_RUN_DIR"
    elif [[ -f "$RUNS_DIR/.active_run" ]]; then
        rid="$(head -1 "$RUNS_DIR/.active_run" | tr -d '[:space:]')"
        [[ -n "$rid" && -d "$RUNS_DIR/$rid" ]] && run_dir="$RUNS_DIR/$rid"
    fi
fi
if [[ -z "$run_dir" ]]; then
    run_dir="$(ls -dt "$RUNS_DIR"/*/ 2>/dev/null | head -1)"
    run_dir="${run_dir%/}"
fi
if [[ -z "$run_dir" || ! -d "$run_dir" ]]; then
    echo "[$TAG] WARN: no run dir resolved; writing nothing"
    exit 0
fi
echo "[$TAG] run_dir=$run_dir"

run_id="$(basename "$run_dir")"
experiments_root="$run_dir/60_experiments"
out_dir="$run_dir/$out_rel"
mkdir -p "$out_dir"

# --- Build list of experiment dirs to gather --------------------------------
exp_dirs=()
if [[ ! -d "$experiments_root" ]]; then
    echo "[$TAG] no 60_experiments dir yet; manifest will be empty"
else
    if [[ -n "$eid" ]]; then
        # Match either an exact dir name or any "${eid}_*" dir.
        matched="$(find "$experiments_root" -maxdepth 1 -type d -name "$eid" -o -type d -name "${eid}_*" 2>/dev/null | head -20)"
        if [[ -z "$matched" ]]; then
            echo "[$TAG] WARN: eid '$eid' not found under 60_experiments; manifest will be empty"
        else
            while IFS= read -r d; do
                [[ -n "$d" ]] && exp_dirs+=("$d")
            done <<< "$matched"
        fi
    else
        while IFS= read -r d; do
            [[ -n "$d" ]] && exp_dirs+=("$d")
        done < <(find "$experiments_root" -maxdepth 1 -mindepth 1 -type d 2>/dev/null | sort)
    fi
fi

# --- Assemble manifest via python (stdlib only) ------------------------------
manifest_path="$out_dir/artifact_manifest.json"
ARW_PYTHON="${ARW_PYTHON:-python}"
"$ARW_PYTHON" - "$run_id" "$manifest_path" "${exp_dirs[@]}" <<'PYEOF'
import json, os, sys, datetime
run_id, manifest_path = sys.argv[1], sys.argv[2]
exp_dirs = sys.argv[3:]
artifacts_names = [
    "config.yaml", "command.sh", "run.log", "metrics.json",
    "report.md", "code_diff.patch", "environment.txt",
]
experiments = []
for d in sorted(exp_dirs):
    if not d or not os.path.isdir(d):
        continue
    eid = os.path.basename(d)
    files = {}
    for name in artifacts_names:
        p = os.path.join(d, name)
        if os.path.isfile(p):
            # store absolute path for portability
            files[name] = os.path.abspath(p)
    experiments.append({"eid": eid, "dir": os.path.abspath(d), "files": files})
manifest = {
    "run_id": run_id,
    "generated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "experiments": experiments,
}
with open(manifest_path, "w") as f:
    json.dump(manifest, f, indent=2, sort_keys=True)
print("manifest_experiments=%d" % len(experiments))
PYEOF

echo "[$TAG] manifest written: $manifest_path"

# --- Optional tar ------------------------------------------------------------
tarball="$out_dir/${run_id}.tar.gz"
if command -v tar >/dev/null 2>&1; then
    if [[ ${#exp_dirs[@]} -gt 0 ]]; then
        tar -czf "$tarball" -C "$run_dir" \
            "$(python -c "import os,sys; print(os.path.relpath(sys.argv[1], sys.argv[2]))" "$manifest_path" "$run_dir")" \
            "${exp_dirs[@]/#$run_dir\//}" 2>/dev/null \
            && echo "[$TAG] tarball written: $tarball" \
            || echo "[$TAG] WARN: tar assembly had errors (continuing)"
    else
        echo "[$TAG] skipping tarball (no experiments to package)"
    fi
else
    echo "[$TAG] tar not available; skipping tarball"
fi

echo "[$TAG] done (exit 0)"
exit 0
