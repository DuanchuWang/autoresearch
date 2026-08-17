#!/usr/bin/env python3
"""Stop hook — keep the controller working while there is runnable work, else allow idle.

Rule (fail-soft):
  runnable = first task with state=='in_progress', or state=='pending' with empty blocked_by.
  terminal = current_state in {S18_PUBLICATION_CANDIDATE_PACKAGE, S_BLOCKED_EXTERNAL,
             S_FAIL_CLOSED_REPORT}.
  BLOCK stop (re-inject the next action) iff:
    active_goal is non-empty AND not terminal AND a runnable task exists AND
    stop_continue_count < cap (default 40, env ARW_STOP_CONTINUE_CAP).
  Otherwise ALLOW stop.

On each block, best-effort increment run_state.stop_continue_count so a stuck loop cannot
run forever. The orchestrator resets it on real state transitions.
"""
from __future__ import annotations
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _arw_common import (  # noqa: E402
    STATE_REL, TASKQ_REL, completed_task_ids, find_run_dir, first_runnable_task,
    load_json, log,
)

TAG = "on_stop"
TERMINAL = {"S18_PUBLICATION_CANDIDATE_PACKAGE", "S_BLOCKED_EXTERNAL", "S_FAIL_CLOSED_REPORT"}


def _first_runnable(tasks, completed_ids=None):
    """First runnable task: in_progress, OR pending with all blockers already done.

    Resolves ``blocked_by`` against the union of run_state.completed_task_ids and
    task_queue rows with state=done (see completed_task_ids). Previously a non-empty
    blocked_by list masked ready work as 'still blocked' (T0016/T0017).
    """
    return first_runnable_task(tasks, completed_ids)


def _live_training_process() -> bool:
    """Is a training entrypoint (tools/train.py | dist_train.sh) alive?

    Used to recognize a long-running background TRAINING gate: if the runnable
    task is an in_progress training job with a live process, the controller is
    correctly WAITING (the operator-endorsed background-trigger model), not
    idle. The training-completion poller re-triggers the controller on exit, so
    re-nagging on every stop only burns tokens.
    """
    try:
        r = subprocess.run(
            ['pgrep', '-f', r'tools/train\.py'],
            capture_output=True, text=True, timeout=5)
        if r.stdout.strip():
            return True
    except Exception:
        pass
    try:
        r = subprocess.run(
            ['pgrep', '-f', r'dist_train\.sh'],
            capture_output=True, text=True, timeout=5)
        if r.stdout.strip():
            return True
    except Exception:
        pass
    return False


def _cooldown_active(rd: Path, cooldown_s: int) -> bool:
    """Did the hook block within the last ``cooldown_s`` seconds? (rate-limit)."""
    f = rd / '.stop_hook_last_block'
    try:
        last = float(f.read_text().strip())
        return (time.time() - last) < cooldown_s
    except Exception:
        return False


def _record_block(rd: Path) -> None:
    """Sidecar timestamp of the last block (for the cooldown rate-limit)."""
    try:
        (rd / '.stop_hook_last_block').write_text(str(time.time()))
    except Exception:
        pass


def main() -> int:
    rd = find_run_dir()
    if rd is None:
        return 0  # nothing to enforce
    rs = load_json(rd / STATE_REL, TAG)
    if not isinstance(rs, dict):
        return 0
    state = rs.get("current_state", "")
    goal = (rs.get("active_goal") or "").strip()
    cap = int(os.environ.get("ARW_STOP_CONTINUE_CAP", "40"))
    count = int(rs.get("stop_continue_count", 0))

    if not goal or state in TERMINAL or count >= cap:
        if count >= cap:
            log(TAG, "WARN", f"stop_continue_count={count} reached cap {cap}; allowing stop. "
                             f"Reset run_state.stop_continue_count to continue autonomously.")
        return 0

    tq = load_json(rd / TASKQ_REL, TAG) or {}
    tasks = tq.get("tasks", []) if isinstance(tq, dict) else []
    task = _first_runnable(tasks, completed_task_ids(rs, tasks))
    if task is None:
        return 0  # genuinely idle (e.g., waiting on external input) -> allow stop

    # (1) Live training gate: an in_progress training job with a live process is
    # a legitimate WAIT, not idleness. Allow stop; the training-completion poller
    # re-triggers the controller on exit (operator-endorsed background-trigger
    # model). Re-nagging every stop only burns tokens.
    if task.get("state") == "in_progress" and _live_training_process():
        log(TAG, "INFO",
            f"runnable task {task.get('task_id','?')} is an in_progress training "
            f"job with a live process; allowing stop (background-trigger model).")
        return 0

    # (2) Cooldown backstop: never re-block within cooldown_s of the last block,
    # so no rapid-fire repeat can burn tokens regardless of cause.
    cooldown_s = int(os.environ.get("ARW_STOP_COOLDOWN_S", "120"))
    if _cooldown_active(rd, cooldown_s):
        log(TAG, "INFO",
            f"blocked within the last {cooldown_s}s; allowing stop (rate-limit).")
        return 0

    # Best-effort increment the loop counter
    try:
        rs["stop_continue_count"] = count + 1
        (rd / STATE_REL).write_text(json.dumps(rs, ensure_ascii=False, indent=2))
    except Exception as e:
        log(TAG, "WARN", f"could not persist stop_continue_count: {e}")
    _record_block(rd)

    title = task.get("title", "next action")
    tid = task.get("task_id", "?")
    reason = (f"[on_stop] ACTIVE GOAL still pending (state={state}, runnable={tid}). "
              f"Continue with: {title}. Do not go idle; advance the state machine / gate, "
              f"persist results to files, then re-evaluate. (autonomous continue #{count + 1})")
    print(json.dumps({"decision": "block", "reason": reason}))
    log(TAG, "BLOCK", f"preventing idle; runnable task {tid}: {title}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
