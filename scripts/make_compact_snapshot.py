#!/usr/bin/env python3
"""make_compact_snapshot.py — build memory/compact_snapshot.md for the active run.

Gathers: run_state.json, claim_ledger.jsonl (status counts), experiment_ledger.md
(last E000X block), git status + last 5 commits. Overwrites compact_snapshot.md
with the canonical section headers, saves git status to a sidecar file, and bumps
run_state.json (compact_count, last_compact_at).

Fail-soft: missing run_state / ledgers / git -> WARN + exit 0 (snapshot still written).
Hard-fail: present-but-malformed run_state.json -> exit 1.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile

# --- stdlib-only helper bootstrap -------------------------------------------------
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _arw_common import (  # noqa: E402
    REPO_ROOT, RUNS_DIR, now_iso, log,
    find_run_dir, require_run_dir,
    load_json, load_jsonl,
    STATE_REL, CLAIM_LEDGER_REL, LEDGER_REL, SNAPSHOT_REL, NEXT_ACTIONS_REL,
    MAX_NEXT_ACTION_LINES,
    EXIT_OK, EXIT_HARD_FAIL,
)

TAG = "compact_snapshot"


def _git(args: list[str]) -> str:
    """Run a git command in REPO_ROOT, returning stdout. Fail-soft -> '' on error."""
    try:
        cp = subprocess.run(
            ["git", "-C", str(REPO_ROOT), *args],
            capture_output=True, text=True, timeout=30,
        )
        if cp.returncode != 0:
            log(TAG, "WARN", f"git {' '.join(args)} rc={cp.returncode}: {cp.stderr.strip()[:200]}")
            return ""
        return cp.stdout
    except FileNotFoundError:
        log(TAG, "WARN", "git binary not found on PATH; skipping git summary")
        return ""
    except subprocess.TimeoutExpired:
        log(TAG, "WARN", f"git {' '.join(args)} timed out")
        return ""
    except Exception as e:  # pragma: no cover — defensive
        log(TAG, "WARN", f"git {' '.join(args)} raised {type(e).__name__}: {e}")
        return ""


def _claims_by_status(claim_path):
    """Return {status: count} over claim_ledger.jsonl (fail-soft -> {})."""
    claims = load_jsonl(claim_path, TAG)
    counts: dict[str, int] = {}
    for c in claims:
        st = str(c.get("status", "unknown"))
        counts[st] = counts.get(st, 0) + 1
    return counts


_EBLOCK_RE = re.compile(r"^##\s+(E\d{4})\b", re.MULTILINE)


def _last_experiment_block(ledger_path):
    """Return (eid, text) for the last '## E000X' block, truncated to ~40 lines."""
    try:
        text = ledger_path.read_text()
    except FileNotFoundError:
        log(TAG, "WARN", f"missing file: {ledger_path}")
        return None, "n/a"
    except Exception as e:
        log(TAG, "WARN", f"could not read {ledger_path}: {e}")
        return None, "n/a"
    matches = list(_EBLOCK_RE.finditer(text))
    if not matches:
        return None, "n/a"
    last = matches[-1]
    eid = last.group(1)
    start = last.start()
    nxt = None
    for m in matches:
        if m.start() > start:
            nxt = m.start()
            break
    block = text[start:nxt].rstrip() if nxt else text[start:].rstrip()
    lines = block.splitlines()
    if len(lines) > 40:
        block = "\n".join(lines[:40]) + "\n... (truncated)"
    return eid, block


def _fmt_list(items, limit=8):
    if not items:
        return "n/a"
    out = items[:limit]
    suffix = f" (+{len(items) - limit} more)" if len(items) > limit else ""
    return ", ".join(str(x) for x in out) + suffix


def _atomic_write_json(path, obj):
    """Write JSON atomically via a temp file in the same dir."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp.", suffix=".json", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(obj, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _bump_state(state_path, state):
    """Increment compact_count, set last_compact_at, write back atomically."""
    state["compact_count"] = int(state.get("compact_count", 0) or 0) + 1
    state["last_compact_at"] = now_iso()
    try:
        _atomic_write_json(state_path, state)
    except Exception as e:
        log(TAG, "ERROR", f"failed to write back run_state.json: {e}")


def build_snapshot(run_dir, state):
    """Assemble the compact_snapshot.md body from gathered data."""
    claim_path = run_dir / CLAIM_LEDGER_REL
    ledger_path = run_dir / LEDGER_REL

    claim_counts = _claims_by_status(claim_path)
    last_eid, last_block = _last_experiment_block(ledger_path)

    cur_state = state.get("current_state", "n/a")
    active_goal = state.get("active_goal", "n/a") or "n/a"
    current_branch = state.get("current_branch", "n/a") or "n/a"
    best_branch = state.get("best_branch", "n/a") or "n/a"
    latest_eid = state.get("latest_experiment_id", "E0000") or "E0000"
    proposal_status = state.get("proposal_status", "unlocked")
    completed = state.get("completed_task_ids", []) or []
    active_tids = state.get("active_task_ids", []) or []
    blocked_tids = state.get("blocked_task_ids", []) or []
    baseline_status = state.get("baseline_status", "not_started")
    pub_status = state.get("publication_candidate_status", "not_ready")
    last_commit = state.get("last_commit", "") or ""

    # Git status + recent log
    git_status = _git(["status", "--short"])
    git_log = _git(["log", "--oneline", "-5"])

    accepted = claim_counts.get("supported", 0)
    unsupported = (claim_counts.get("unsupported", 0)
                   + claim_counts.get("overstated", 0)
                   + claim_counts.get("removed", 0))

    parts = []
    parts.append("# Compact Snapshot")
    parts.append("")
    parts.append(f"> Auto-generated by `scripts/make_compact_snapshot.py` at {now_iso()}.")
    parts.append(f"> Run: `{state.get('run_id', 'n/a')}`  ·  Topic: `{state.get('topic', 'n/a')}`")
    parts.append("")

    parts.append("## Current State")
    parts.append("")
    parts.append(f"- State machine: `{cur_state}`")
    parts.append(f"- Proposal status: `{proposal_status}`")
    parts.append(f"- Baseline status: `{baseline_status}`")
    parts.append(f"- Publication candidate: `{pub_status}`")
    gates = state.get("gates", {}) or {}
    if gates:
        gate_lines = [f"  - `{g}`: `{st}`" for g, st in gates.items()]
        parts.append("- Gates:")
        parts.extend(gate_lines)
    parts.append("")

    parts.append("## Current Goal")
    parts.append("")
    parts.append(active_goal)
    parts.append("")

    parts.append("## Completed Work")
    parts.append("")
    parts.append(f"- Completed task IDs: {_fmt_list(completed) if completed else 'none yet'}")
    parts.append(f"- Latest experiment ID: `{latest_eid}`")
    parts.append(f"- Claims by status: {dict(claim_counts) if claim_counts else 'no claim ledger yet'}")
    parts.append("")

    parts.append("## Active Proposal")
    parts.append("")
    parts.append(f"- Proposal lock: `{proposal_status}`")
    parts.append(f"- Active task IDs: {_fmt_list(active_tids) if active_tids else 'none'}")
    parts.append(f"- Blocked task IDs: {_fmt_list(blocked_tids) if blocked_tids else 'none'}")
    parts.append("")

    parts.append("## Active Branch")
    parts.append("")
    parts.append(f"- current_branch: `{current_branch}`")
    parts.append(f"- best_branch:    `{best_branch}`")
    parts.append(f"- last_commit:    `{last_commit if last_commit else 'n/a'}`")
    parts.append("")

    parts.append("## Latest Experiment")
    parts.append("")
    parts.append(f"Last block eid: `{last_eid if last_eid else latest_eid}`")
    parts.append("")
    parts.append("```markdown")
    parts.append(last_block if last_block and last_block != "n/a" else "(no experiment blocks yet)")
    parts.append("```")
    parts.append("")

    parts.append("## Accepted Claims")
    parts.append("")
    parts.append(f"- supported: **{accepted}**")
    parts.append(f"- planned:   {claim_counts.get('planned', 0)}")
    parts.append(f"- weakened:  {claim_counts.get('weakened', 0)}")
    parts.append("")

    parts.append("## Unsupported Claims")
    parts.append("")
    parts.append(f"- unsupported/overstated/removed: **{unsupported}**")
    parts.append("")

    parts.append("## Current Risks")
    parts.append("")
    risks = []
    if blocked_tids:
        risks.append(f"{len(blocked_tids)} blocked task(s): {_fmt_list(blocked_tids)}")
    if baseline_status == "gap_recorded":
        risks.append("Baseline gap recorded — reproduction not clean")
    if pub_status == "blocked":
        risks.append("Publication candidate blocked")
    if not git_status.strip():
        risks.append("Git status empty (clean tree or git unavailable)")
    if not risks:
        risks.append("none observed")
    for r in risks:
        parts.append(f"- {r}")
    parts.append("")

    parts.append("## Next Actions")
    parts.append("")
    na_path = run_dir / NEXT_ACTIONS_REL
    try:
        na_text = na_path.read_text(encoding="utf-8").strip()
        na_lines = na_text.splitlines() if na_text else []
        if len(na_lines) > MAX_NEXT_ACTION_LINES:
            na_text = "\n".join(na_lines[:MAX_NEXT_ACTION_LINES]) + "\n... (truncated)"
        parts.append("```markdown")
        parts.append(na_text if na_text else "(next_actions.md is empty)")
        parts.append("```")
    except FileNotFoundError:
        parts.append(f"(no `memory/next_actions.md` yet — see `{na_path}`)")
    parts.append("")

    parts.append("## Files to Read After Resume")
    parts.append("")
    must_read = [
        f"`{run_dir / STATE_REL}`",
        f"`{run_dir / LEDGER_REL}`",
        f"`{run_dir / CLAIM_LEDGER_REL}`",
        f"`{run_dir / SNAPSHOT_REL}`",
        f"`{run_dir / 'memory' / 'next_actions.md'}`",
        f"`{run_dir / 'memory' / 'open_questions.md'}`",
    ]
    for m in must_read:
        parts.append(f"- {m}")
    parts.append("")

    parts.append("## Do Not Forget")
    parts.append("")
    notes = []
    notes.append("EID is never overwritten — only append new `## E000X` blocks.")
    notes.append("Claim ledger rows are append-only; mutate `status` in place, never delete.")
    notes.append("Never delete protected artifacts (run_state, ledgers, manifest, experiments).")
    notes.append("Fail-soft: missing data -> WARN + exit 0; only malformed contracts exit 1.")
    if proposal_status == "locked":
        notes.append("Proposal is LOCKED — do not change scope without an explicit unlock decision.")
    for n in notes:
        parts.append(f"- {n}")
    parts.append("")

    parts.append("---")
    parts.append("")
    parts.append("### Git status (`git status --short`)")
    parts.append("")
    parts.append("```")
    parts.append(git_status.strip() if git_status.strip() else "(clean)")
    parts.append("```")
    parts.append("")
    parts.append("### Recent commits (`git log --oneline -5`)")
    parts.append("")
    parts.append("```")
    parts.append(git_log.strip() if git_log.strip() else "(none)")
    parts.append("```")
    parts.append("")

    return "\n".join(parts)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build memory/compact_snapshot.md for the active run.")
    ap.add_argument("--run-dir", default=None,
                    help="Override run dir (defaults to $ARW_RUN_DIR / .active_run / newest).")
    args = ap.parse_args(argv)

    run_dir = find_run_dir(args.run_dir) if args.run_dir else require_run_dir(TAG)
    if run_dir is None:
        # Nothing to do — already warned.
        return EXIT_OK

    state_path = run_dir / STATE_REL
    snapshot_path = run_dir / SNAPSHOT_REL
    git_status_path = run_dir / "memory" / "git_status_before_compact.txt"

    # run_state.json: hard-fail if present-but-malformed, fail-soft if missing.
    try:
        raw = state_path.read_text()
    except FileNotFoundError:
        log(TAG, "WARN", f"missing run_state.json at {state_path}; writing snapshot with empty state.")
        state = {}
        malformed = False
    except Exception as e:
        log(TAG, "WARN", f"could not read {state_path}: {e}")
        state = {}
        malformed = False
    else:
        try:
            state = json.loads(raw)
            malformed = False
        except json.JSONDecodeError as e:
            log(TAG, "ERROR", f"malformed run_state.json ({state_path}): {e}")
            state = {}
            malformed = True

    if malformed:
        # Still write the snapshot so the operator has something, but signal hard fail.
        try:
            body = build_snapshot(run_dir, {})
            snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            snapshot_path.write_text(body)
        except Exception as e:
            log(TAG, "ERROR", f"failed to write snapshot: {e}")
        return EXIT_HARD_FAIL

    # Refresh next_actions from the queue before snapshotting (fail-soft).
    try:
        from generate_next_actions import generate as regen_next_actions
        regen_next_actions(run_dir)
    except Exception as e:
        log(TAG, "WARN", f"next_actions regenerate failed (snapshot continues): {e}")

    # Build and write the snapshot (overwrite).
    body = build_snapshot(run_dir, state)
    try:
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_text(body)
    except Exception as e:
        log(TAG, "ERROR", f"failed to write snapshot to {snapshot_path}: {e}")
        return EXIT_OK

    # Save git status sidecar (best-effort).
    git_status = _git(["status", "--short"])
    try:
        git_status_path.parent.mkdir(parents=True, exist_ok=True)
        git_status_path.write_text(
            f"# git status --short @ {now_iso()}\n"
            f"# repo: {REPO_ROOT}\n"
            f"{git_status}"
        )
    except Exception as e:
        log(TAG, "WARN", f"could not write git status sidecar {git_status_path}: {e}")

    # Bump run_state.json only when we actually have one.
    if state:
        _bump_state(state_path, state)

    # hook protocol: stdout is reserved for JSON; diagnostic → stderr
    print(f"snapshot written: {snapshot_path}", file=sys.stderr)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
