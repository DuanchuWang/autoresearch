#!/usr/bin/env python3
"""Validate run_state.json for the autonomous-research-workflow contract.

Fail-soft: missing run dir or missing state file -> WARN + exit 0.
Hard-fail: present-but-malformed state file (invalid JSON, not a dict, unknown
enum value) -> ERROR + exit 1.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _arw_common import (
    EXIT_HARD_FAIL, EXIT_OK, REPO_ROOT, RUNS_DIR, STATE_REL, VALID_LITERATURE_MODES,
    VALID_STATES, find_run_dir, load_json, log, now_iso, require_run_dir,
)

TAG = "validate_run_state"

REQUIRED_KEYS = [
    "run_id", "topic", "current_state", "proposal_status", "current_branch",
    "best_branch", "latest_experiment_id", "active_goal", "active_task_ids",
    "completed_task_ids", "blocked_task_ids", "compact_count", "gates",
    "resource_status", "baseline_status",
]

VALID_PROPOSAL = {"unlocked", "locked"}
VALID_GATE = {"not_started", "in_progress", "passed", "failed"}
VALID_BASELINE = {"not_started", "reproduced", "gap_recorded"}
EID_RE = re.compile(r"^E\d{4}$")

GATE_KEYS = [
    "literature_gate", "proposal_gate", "baseline_gate",
    "experiment_gate", "paper_gate", "final_gate",
]


def _load_state_raw(path):
    """Load state strictly: distinguish missing vs malformed. Returns (dict|None, ok_bool)."""
    if not path.is_file():
        log(TAG, "WARN", f"missing state file: {path}; nothing to validate.")
        return None, True
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        log(TAG, "ERROR", f"invalid JSON in {path}: {e}")
        return None, False
    if not isinstance(data, dict):
        log(TAG, "ERROR", f"state root is not a JSON object in {path} (got {type(data).__name__}).")
        return None, False
    return data, True


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Validate run_state.json contract.")
    ap.add_argument("--run-dir", default=None, help="Override active run directory.")
    ap.add_argument("-v", "--verbose", action="store_true", help="Verbose stderr logging.")
    args = ap.parse_args(argv)

    run_dir = find_run_dir(args.run_dir) if args.run_dir else require_run_dir(TAG)
    if run_dir is None:
        # require_run_dir already logged WARN
        print(f"[{TAG}] no active run; nothing to validate.")
        return EXIT_OK

    if args.verbose:
        log(TAG, "INFO", f"run_dir = {run_dir}")

    state_path = run_dir / STATE_REL
    data, ok = _load_state_raw(state_path)
    if not ok:
        print(f"[{TAG}] HARD FAIL: malformed state file {state_path}")
        return EXIT_HARD_FAIL
    if data is None:
        # missing file -> WARN already logged; advisory summary then exit 0
        print(f"[{TAG}] run_dir={run_dir.name}: state file absent (WARN). Exit 0.")
        return EXIT_OK

    hard_fail = False
    warnings = []

    # Required keys
    missing_keys = [k for k in REQUIRED_KEYS if k not in data]
    if missing_keys:
        log(TAG, "ERROR", f"missing required keys: {', '.join(missing_keys)}")
        hard_fail = True

    # current_state enum
    cs = data.get("current_state")
    if cs is not None and cs not in VALID_STATES:
        log(TAG, "ERROR", f"current_state={cs!r} not in VALID_STATES.")
        hard_fail = True

    # proposal_status enum
    ps = data.get("proposal_status")
    if ps is not None and ps not in VALID_PROPOSAL:
        log(TAG, "ERROR", f"proposal_status={ps!r} not in {sorted(VALID_PROPOSAL)}.")
        hard_fail = True

    # literature_mode is optional (missing => exploratory). If present, must be valid.
    lm = data.get("literature_mode")
    if lm is not None and str(lm).strip() != "":
        lm_norm = str(lm).strip().lower()
        if lm_norm not in VALID_LITERATURE_MODES:
            log(TAG, "ERROR",
                f"literature_mode={lm!r} not in {sorted(VALID_LITERATURE_MODES)}.")
            hard_fail = True

    # baseline_status enum (advisory field per spec, but listed in REQUIRED_KEYS)
    bs = data.get("baseline_status")
    if bs is not None and bs not in VALID_BASELINE:
        log(TAG, "ERROR", f"baseline_status={bs!r} not in {sorted(VALID_BASELINE)}.")
        hard_fail = True

    # gates
    gates = data.get("gates")
    if gates is not None:
        if not isinstance(gates, dict):
            log(TAG, "ERROR", f"gates is not an object (got {type(gates).__name__}).")
            hard_fail = True
        else:
            for gk in GATE_KEYS:
                gv = gates.get(gk)
                if gv is None:
                    log(TAG, "WARN", f"gate '{gk}' missing; treating as not_started.")
                    warnings.append(f"gate {gk} missing")
                elif gv not in VALID_GATE:
                    log(TAG, "ERROR", f"gates.{gk}={gv!r} not in {sorted(VALID_GATE)}.")
                    hard_fail = True

    # latest_experiment_id format
    eid = data.get("latest_experiment_id")
    if eid is not None and not (isinstance(eid, str) and EID_RE.match(eid)):
        log(TAG, "ERROR", f"latest_experiment_id={eid!r} does not match ^E\\d{{4}}$.")
        hard_fail = True

    # Task-list overlap check (WARN only, not fatal)
    active = set(data.get("active_task_ids") or [])
    completed = set(data.get("completed_task_ids") or [])
    blocked = set(data.get("blocked_task_ids") or [])
    overlap_ac = active & completed
    overlap_ab = active & blocked
    overlap_cb = completed & blocked
    if overlap_ac:
        msg = f"task ids in both active & completed: {sorted(overlap_ac)}"
        log(TAG, "WARN", msg); warnings.append(msg)
    if overlap_ab:
        msg = f"task ids in both active & blocked: {sorted(overlap_ab)}"
        log(TAG, "WARN", msg); warnings.append(msg)
    if overlap_cb:
        msg = f"task ids in both completed & blocked: {sorted(overlap_cb)}"
        log(TAG, "WARN", msg); warnings.append(msg)

    # ---- Human summary to stdout ----
    print(f"[{TAG}] run_dir={run_dir.name}")
    print(f"  run_id               = {data.get('run_id')}")
    print(f"  topic                = {data.get('topic')}")
    print(f"  current_state        = {cs}")
    print(f"  proposal_status      = {ps}")
    print(f"  literature_mode      = {data.get('literature_mode', '<missing→exploratory>')}")
    print(f"  latest_experiment_id = {eid}")
    print(f"  baseline_status      = {bs}")
    print(f"  tasks (active/completed/blocked) = "
          f"{len(active)}/{len(completed)}/{len(blocked)}")
    if isinstance(gates, dict):
        print("  gates:")
        for gk in GATE_KEYS:
            print(f"    {gk:16s} = {gates.get(gk, '<missing>')}")
    if warnings:
        print(f"  warnings ({len(warnings)}):")
        for w in warnings:
            print(f"    - {w}")
    else:
        print("  warnings: none")

    if hard_fail:
        print(f"[{TAG}] HARD FAIL: contract violation(s) in {state_path}. Exit 1.")
        return EXIT_HARD_FAIL
    print(f"[{TAG}] OK. Exit 0.")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
