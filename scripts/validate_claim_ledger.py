#!/usr/bin/env python3
"""Validate 40_proposal/claim_ledger.jsonl for the autonomous-research-workflow.

Advisory / fail-soft: never exits non-zero. Missing file -> WARN + exit 0.
Checks required keys, type/status enums, duplicate claim_ids, and flags
supported-claims with empty evidence and any unsupported/overstated claims
(these must not reach the paper).
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _arw_common import (
    REPO_ROOT, RUNS_DIR, now_iso, log, find_run_dir, require_run_dir,
    load_jsonl, CLAIM_LEDGER_REL, EXIT_OK,
)

TAG = "validate_claim_ledger"

REQUIRED_KEYS = [
    "claim_id", "claim", "type", "supporting_papers", "opposing_papers",
    "required_experiment_ids", "required_ablation_ids", "status", "evidence_paths",
]

VALID_TYPES = {
    "literature_gap", "method_claim", "experimental_claim", "limitation_claim",
}
VALID_STATUSES = {
    "planned", "supported", "weakened", "unsupported", "overstated", "removed",
}

# Statuses that must not reach the paper.
PAPER_FORBIDDEN = {"unsupported", "overstated"}


def _is_list(x):
    return isinstance(x, list)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Validate claim_ledger.jsonl (advisory).")
    ap.add_argument("--run-dir", default=None, help="Override active run directory.")
    ap.add_argument("-v", "--verbose", action="store_true", help="Verbose stderr logging.")
    args = ap.parse_args(argv)

    run_dir = find_run_dir(args.run_dir) if args.run_dir else require_run_dir(TAG)
    if run_dir is None:
        print(f"[{TAG}] no active run; nothing to validate.")
        return EXIT_OK

    if args.verbose:
        log(TAG, "INFO", f"run_dir = {run_dir}")

    ledger_path = run_dir / CLAIM_LEDGER_REL
    claims = load_jsonl(ledger_path, TAG)
    if not claims:
        print(f"[{TAG}] run_dir={run_dir.name}: claim ledger empty or absent (WARN). Exit 0.")
        return EXIT_OK

    status_counts = Counter()
    type_counts = Counter()
    missing_keys = []
    bad_type = []
    bad_status = []
    supported_no_evidence = []
    forbidden_in_paper = []
    seen_ids = {}
    duplicates = []

    for i, claim in enumerate(claims, 1):
        if not isinstance(claim, dict):
            log(TAG, "ERROR", f"claim {i} is not a JSON object; skipping.")
            continue
        cid = claim.get("claim_id", f"<line {i}>")
        for k in REQUIRED_KEYS:
            if k not in claim:
                log(TAG, "ERROR", f"claim {cid}: missing required key '{k}'.")
                missing_keys.append((cid, k))
        # type enum
        t = claim.get("type")
        if t is not None and t not in VALID_TYPES:
            log(TAG, "ERROR", f"claim {cid}: type={t!r} not in {sorted(VALID_TYPES)}.")
            bad_type.append((cid, t))
        else:
            type_counts[t] += 1
        # status enum
        s = claim.get("status")
        if s is not None and s not in VALID_STATUSES:
            log(TAG, "ERROR", f"claim {cid}: status={s!r} not in {sorted(VALID_STATUSES)}.")
            bad_status.append((cid, s))
        else:
            status_counts[s] += 1
        # list-typed fields present?
        for lk in ("supporting_papers", "opposing_papers",
                   "required_experiment_ids", "required_ablation_ids",
                   "evidence_paths"):
            v = claim.get(lk)
            if v is not None and not _is_list(v):
                log(TAG, "WARN", f"claim {cid}: '{lk}' is not a list (got {type(v).__name__}).")
        # supported but no evidence -> WARN
        if s == "supported":
            ev = claim.get("evidence_paths") or []
            if not ev:
                msg = f"claim {cid}: status=supported but evidence_paths is empty."
                log(TAG, "WARN", msg)
                supported_no_evidence.append(cid)
        # unsupported / overstated must not reach the paper
        if s in PAPER_FORBIDDEN:
            msg = (f"claim {cid}: status={s} must NOT reach the paper "
                   f"(review for removal or restatement).")
            log(TAG, "WARN", msg)
            forbidden_in_paper.append((cid, s))
        # duplicate claim_id
        if cid != f"<line {i}>":
            if cid in seen_ids:
                log(TAG, "WARN", f"duplicate claim_id={cid} "
                                 f"(first at line {seen_ids[cid]}, again at {i}).")
                duplicates.append(cid)
            else:
                seen_ids[cid] = i

    # ---- Human summary to stdout ----
    print(f"[{TAG}] run_dir={run_dir.name}")
    print(f"  total claims: {len(claims)}  (unique claim_ids: {len(seen_ids)})")
    print("  status counts:")
    for s in ["planned", "supported", "weakened", "unsupported", "overstated", "removed"]:
        print(f"    {s:12s} = {status_counts.get(s, 0)}")
    print("  type counts:")
    for t in sorted(VALID_TYPES):
        print(f"    {t:18s} = {type_counts.get(t, 0)}")
    if missing_keys:
        print(f"  claims missing required keys: {len(missing_keys)} (see stderr)")
    if bad_type:
        print(f"  claims with bad type: {len(bad_type)} (see stderr)")
    if bad_status:
        print(f"  claims with bad status: {len(bad_status)} (see stderr)")
    if supported_no_evidence:
        print(f"  WARN: supported claims with empty evidence ({len(supported_no_evidence)}):")
        for cid in supported_no_evidence:
            print(f"    - {cid}")
    if forbidden_in_paper:
        print(f"  WARN: paper-forbidden statuses ({len(forbidden_in_paper)}):")
        for cid, s in forbidden_in_paper:
            print(f"    - {cid}  ({s})")
    if duplicates:
        print(f"  WARN: duplicate claim_ids ({len(duplicates)}):")
        for cid in duplicates:
            print(f"    - {cid}")
    print(f"[{TAG}] advisory check complete. Exit 0.")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
