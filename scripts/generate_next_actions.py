#!/usr/bin/env python3
"""Regenerate memory/next_actions.md from task_queue.json + run_state.json.

The generated file is the *only* next-action list the controller should read.
It is short (≤ MAX_NEXT_ACTION_LINES) and overwritten on every call.

A pre-existing hand-written next_actions.md (no ARW_GENERATED marker) is archived
once to memory/next_actions.journal.md and never deleted. Subsequent regenerations
do not grow the journal. Agents must update task_queue.json, not append this file.

Fail-soft: missing run / missing files → write a stub (or no-op) and exit 0.
Never prints the body to stdout (hook-safe); diagnostics go to stderr.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _arw_common import (  # noqa: E402
    EXIT_OK, MAX_NEXT_ACTION_LINES, NEXT_ACTIONS_JOURNAL_REL, NEXT_ACTIONS_MARKER,
    NEXT_ACTIONS_REL, STATE_REL, TASKQ_REL, atomic_write_text, completed_task_ids,
    find_run_dir, iter_runnable_tasks, literature_mode_of, load_json, log, now_iso,
    require_run_dir,
)

TAG = "generate_next_actions"
MAX_DO_NOW = 3
MAX_BLOCKED = 2
GOAL_CHARS = 160
TITLE_CHARS = 72


def _one_line(text, limit: int) -> str:
    s = " ".join(str(text or "").split())
    if len(s) <= limit:
        return s
    return s[: max(0, limit - 1)].rstrip() + "…"


def _archive_if_handwritten(run_dir: Path, prev: str) -> bool:
    """Archive prev to the journal iff it is a non-empty hand-written file.

    Returns True if an archive write happened.
    """
    if not prev.strip():
        return False
    if prev.lstrip().startswith(NEXT_ACTIONS_MARKER):
        return False
    journal = run_dir / NEXT_ACTIONS_JOURNAL_REL
    journal.parent.mkdir(parents=True, exist_ok=True)
    header = f"\n\n<!-- archived {now_iso()} from next_actions.md (pre-generated) -->\n\n"
    with journal.open("a", encoding="utf-8") as f:
        f.write(header)
        f.write(prev)
        if not prev.endswith("\n"):
            f.write("\n")
    return True


def build_next_actions(run_dir: Path, state, tasks) -> str:
    """Pure builder: no I/O besides reading nothing. Returns the markdown body."""
    state = state if isinstance(state, dict) else {}
    tasks = tasks if isinstance(tasks, list) else []
    mode = literature_mode_of(state)
    done = completed_task_ids(state, tasks)
    runnable = iter_runnable_tasks(tasks, done)

    blocked = []
    for t in tasks:
        if not isinstance(t, dict):
            continue
        st = t.get("state")
        tid = t.get("task_id")
        if st == "blocked":
            blocked.append(t)
        elif st == "pending" and tid and not any(r.get("task_id") == tid for r in runnable):
            blocked.append(t)

    goal = _one_line(state.get("active_goal") or "(none)", GOAL_CHARS)
    run_id = state.get("run_id") or run_dir.name
    cur = state.get("current_state") or "?"
    proposal = state.get("proposal_status") or "?"
    eid = state.get("latest_experiment_id") or "?"
    baseline = state.get("baseline_status") or "?"

    lines = [
        NEXT_ACTIONS_MARKER,
        "# Next Actions (generated)",
        "",
        f"> From task_queue+run_state @ {now_iso()}. Do not hand-edit; "
        f"update the queue, then `python3 scripts/generate_next_actions.py`. "
        f"Narrative → `{NEXT_ACTIONS_JOURNAL_REL}`.",
        "",
        f"- run: `{run_id}` | state: `{cur}` | mode: `{mode}` | proposal: `{proposal}`",
        f"- EID: `{eid}` | baseline: `{baseline}` | goal: {goal}",
        "",
        "## Do now",
    ]
    if not runnable:
        lines.append("- (idle — no runnable task)")
    else:
        extra = len(runnable) - MAX_DO_NOW
        for i, t in enumerate(runnable[:MAX_DO_NOW], 1):
            title = _one_line(t.get("title") or t.get("task_id") or "?", TITLE_CHARS)
            owner = t.get("owner_agent") or "-"
            st = t.get("state") or "?"
            tid = t.get("task_id") or "?"
            lines.append(f"{i}. `{tid}` [{st}] {owner}: {title}")
        if extra > 0:
            lines.append(f"- (+{extra} more runnable; see `{TASKQ_REL}`)")

    lines.append("")
    lines.append("## Blocked / waiting")
    shown = blocked[:MAX_BLOCKED]
    if not shown:
        lines.append("- (none)")
    else:
        extra_b = len(blocked) - MAX_BLOCKED
        for t in shown:
            tid = t.get("task_id") or "?"
            title = _one_line(t.get("title") or "", TITLE_CHARS)
            why = t.get("state") or "pending"
            lines.append(f"- `{tid}` [{why}] {title}")
        if extra_b > 0:
            lines.append(f"- (+{extra_b} more)")

    body = "\n".join(lines)
    clipped = body.splitlines()
    if len(clipped) > MAX_NEXT_ACTION_LINES:
        clipped = clipped[: MAX_NEXT_ACTION_LINES - 1] + ["- (truncated; see task_queue.json)"]
        body = "\n".join(clipped)
    return body


def generate(run_dir: Path, archive: bool = True) -> str:
    """Build, optionally archive a handwritten predecessor, write, return body."""
    state = load_json(run_dir / STATE_REL, TAG, default={}) or {}
    tq = load_json(run_dir / TASKQ_REL, TAG, default={}) or {}
    tasks = tq.get("tasks", []) if isinstance(tq, dict) else []
    body = build_next_actions(run_dir, state, tasks)

    na_path = run_dir / NEXT_ACTIONS_REL
    prev = ""
    if na_path.is_file():
        try:
            prev = na_path.read_text(encoding="utf-8")
        except OSError as e:
            log(TAG, "WARN", f"could not read {na_path}: {e}")
    if archive:
        try:
            if _archive_if_handwritten(run_dir, prev):
                log(TAG, "INFO", f"archived handwritten next_actions → {NEXT_ACTIONS_JOURNAL_REL}")
        except OSError as e:
            log(TAG, "WARN", f"journal archive failed (continuing with overwrite): {e}")

    atomic_write_text(na_path, body)
    nlines = body.count("\n") + 1
    log(TAG, "INFO", f"wrote {na_path} ({nlines} lines)")
    return body


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Regenerate memory/next_actions.md from queue+state.")
    ap.add_argument("--run-dir", default=None,
                    help="Override run dir (defaults to $ARW_RUN_DIR / .active_run / newest).")
    ap.add_argument("--no-archive", action="store_true",
                    help="Do not copy a handwritten predecessor into the journal.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print body to stdout and do not write files.")
    args = ap.parse_args(argv)

    run_dir = find_run_dir(args.run_dir) if args.run_dir else require_run_dir(TAG)
    if run_dir is None:
        return EXIT_OK

    if args.dry_run:
        state = load_json(run_dir / STATE_REL, TAG, default={}) or {}
        tq = load_json(run_dir / TASKQ_REL, TAG, default={}) or {}
        tasks = tq.get("tasks", []) if isinstance(tq, dict) else []
        body = build_next_actions(run_dir, state, tasks)
        print(body)
        return EXIT_OK

    generate(run_dir, archive=not args.no_archive)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
