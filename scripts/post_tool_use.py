#!/usr/bin/env python3
"""PostToolUse dispatcher (advisory, fail-soft — never blocks).

Fires after Write/Edit/NotebookEdit/MultiEdit. Runs the cheapest relevant checks:
  - ALWAYS: validate_run_state.py, validate_claim_ledger.py, validate_experiment_report.py
  - if argument_chain.md or claim_ledger.jsonl: validate_argument_chain.py
  - if the edited file is *.py: run_lint.sh on that file; if it is code under
    ARW_SMOKE_SCOPE (default 50_code/target_repo/,methods/), also run_smoke_tests.sh.

All child scripts are fail-soft; this dispatcher always exits 0. Output is a concise
stderr summary so the controller sees drift without log spam. Set ARW_POST_TOOL_QUIET=1
to suppress the summary line.
"""
from __future__ import annotations
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _arw_common import log  # noqa: E402

TAG = "post_tool_use"
HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
QUIET = os.environ.get("ARW_POST_TOOL_QUIET") == "1"
SMOKE_SCOPE = tuple(
    p.strip() for p in os.environ.get(
        "ARW_SMOKE_SCOPE", "50_code/target_repo/,methods/"
    ).split(",") if p.strip()
)
NEXT_ACTIONS_TRIGGERS = (
    "state/run_state.json",
    "state/task_queue.json",
)
ARGUMENT_CHAIN_TRIGGERS = (
    "00_seed/argument_chain.md",
    "40_proposal/claim_ledger.jsonl",
)


def _run(cmd: list[str]) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, timeout=120)
        return p.returncode, (p.stdout + p.stderr)[-800:]
    except FileNotFoundError:
        return 0, "tool missing (skipped)"
    except subprocess.TimeoutExpired:
        return 0, "timeout (skipped)"
    except Exception as e:  # never raise from a hook
        return 0, f"error: {e}"


def main() -> int:
    try:
        raw = sys.stdin.read()
        evt = json.loads(raw) if raw.strip() else {}
    except Exception:
        evt = {}
    tin = evt.get("tool_input", {}) or {}
    fp = tin.get("file_path") or tin.get("path") or ""
    rel = ""
    if fp:
        try:
            rel = str(Path(fp).resolve().relative_to(REPO_ROOT))
        except Exception:
            rel = str(fp)

    notes = []
    # Always-on validators (cheap, fail-soft)
    for script in ("validate_run_state.py", "validate_claim_ledger.py",
                   "validate_experiment_report.py"):
        rc, _ = _run(["python3", str(HERE / script)])
        notes.append(f"{script}:{'ok' if rc == 0 else 'warn'}")

    is_py = rel.endswith(".py")
    if is_py:
        rc, _ = _run(["bash", str(HERE / "run_lint.sh"), str(Path(REPO_ROOT) / rel) if rel else ""])
        notes.append(f"lint:{'ok' if rc == 0 else 'issues'}")
        if any(rel.startswith(p) for p in SMOKE_SCOPE):
            rc, _ = _run(["bash", str(HERE / "run_smoke_tests.sh")])
            notes.append(f"smoke:{'ok' if rc == 0 else 'skipped/issues'}")

    rel_posix = rel.replace("\\", "/")
    if any(rel_posix.endswith(t) for t in NEXT_ACTIONS_TRIGGERS):
        rc, _ = _run(["python3", str(HERE / "generate_next_actions.py")])
        notes.append(f"next_actions:{'ok' if rc == 0 else 'warn'}")
    if any(rel_posix.endswith(t) for t in ARGUMENT_CHAIN_TRIGGERS):
        rc, _ = _run(["python3", str(HERE / "validate_argument_chain.py")])
        notes.append(f"argument_chain:{'ok' if rc == 0 else 'warn'}")

    if not QUIET:
        log(TAG, "INFO", f"post-edit {rel or '(?)'} -> " + ", ".join(notes))
    return 0


if __name__ == "__main__":
    sys.exit(main())
