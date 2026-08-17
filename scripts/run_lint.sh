#!/usr/bin/env bash
# run_lint.sh — advisory lint over changed (or given) python files.
# Fail-soft: missing tools / no changes -> exit 0. Non-zero only on a hard tooling error.
set -uo pipefail

TAG="run_lint"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[$TAG] resolving target files..."

# --- Resolve target files -----------------------------------------------------
targets=()
if [[ $# -gt 0 ]]; then
    for f in "$@"; do
        # Accept both absolute and repo-relative paths.
        if [[ -f "$f" ]]; then
            targets+=("$f")
        elif [[ -f "$REPO_ROOT/$f" ]]; then
            targets+=("$REPO_ROOT/$f")
        else
            echo "[$TAG] WARN: target not found, skipping: $f"
        fi
    done
else
    # Default: changed python files (added/modified) vs HEAD.
    while IFS= read -r line; do
        if [[ -n "$line" ]]; then
            targets+=("$REPO_ROOT/$line")
        fi
    done < <(cd "$REPO_ROOT" && git diff --name-only --diff-filter=AM 2>/dev/null | grep '\.py$' || true)
fi

if [[ ${#targets[@]} -eq 0 ]]; then
    echo "[$TAG] no python changes; ok"
    exit 0
fi

echo "[$TAG] linting ${#targets[@]} file(s)"

# --- Pick the first available linter -----------------------------------------
linter=""
if command -v ruff >/dev/null 2>&1; then
    linter="ruff"
elif command -v flake8 >/dev/null 2>&1; then
    linter="flake8"
elif command -v pyflakes >/dev/null 2>&1; then
    linter="pyflakes"
else
    linter="py_compile"
fi

echo "[$TAG] using linter: $linter"

# --- Run -----------------------------------------------------------------------
output=""
rc=0
case "$linter" in
    ruff)
        output="$(ruff check "${targets[@]}" 2>&1)" || rc=$?
        ;;
    flake8)
        output="$(flake8 "${targets[@]}" 2>&1)" || rc=$?
        ;;
    pyflakes)
        output="$(pyflakes "${targets[@]}" 2>&1)" || rc=$?
        ;;
    py_compile)
        # py_compile has no aggregate CLI; compile each file.
        for f in "${targets[@]}"; do
            err="$(python -m py_compile "$f" 2>&1)" || { rc=1; output+="$err"$'\n'; }
        done
        ;;
esac

# Lint is advisory — never fail the workflow on lint findings.
if [[ $rc -ne 0 ]]; then
    echo "[$TAG] ISSUES FOUND"
    printf '%s\n' "$output"
    echo "[$TAG] (advisory; exiting 0)"
    exit 0
fi

echo "[$TAG] clean"
exit 0
