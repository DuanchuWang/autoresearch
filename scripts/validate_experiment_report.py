#!/usr/bin/env python3
"""Validate 60_experiments/experiment_ledger.md for the autonomous-research-workflow.

Advisory / fail-soft: never exits non-zero. Missing file -> WARN + exit 0.
Parses '## E000X' headers; checks each block contains the required field labels
(Status, Branch, Commit impl, Commit result, Hypothesis, Judgement). Detects
duplicate EIDs and (optionally) missing E000X_*/ directories.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from collections import Counter, OrderedDict
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _arw_common import (
    REPO_ROOT, RUNS_DIR, now_iso, log, find_run_dir, require_run_dir,
    LEDGER_REL, EXIT_OK,
)

TAG = "validate_experiment_report"

# Required field labels per experiment block (substring match, case-sensitive,
# matching the canonical ledger field names).
REQUIRED_LABELS = [
    "Status", "Branch", "Commit impl", "Commit result", "Hypothesis", "Judgement",
]

# Match "## E0001" or "## E0001_slug". \b won't fire between a digit and '_'
# (both word chars), so require a non-digit after the EID instead.
HEADER_RE = re.compile(r"^##\s+(E\d{4})(?![0-9])", re.MULTILINE)
JUDGEMENT_RE = re.compile(r"Judgement\s*:?\s*(\w+)", re.IGNORECASE)
EID_DIR_RE = re.compile(r"^(E\d{4})_")


def _split_blocks(text):
    """Return an OrderedDict {eid: block_text} in document order, plus a list of
    (eid, all_occurrence_line_indexes) for duplicate detection."""
    blocks = OrderedDict()
    occurrences = []
    # Find all header positions
    matches = list(HEADER_RE.finditer(text))
    for idx, m in enumerate(matches):
        eid = m.group(1)
        start = m.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        block = text[start:end]
        # last occurrence wins for content but we track all
        blocks[eid] = block
        occurrences.append((eid, m.start()))
    return blocks, occurrences


def _extract_judgement(block: str) -> str:
    m = JUDGEMENT_RE.search(block)
    return m.group(1) if m else "<missing>"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Validate experiment_ledger.md (advisory).")
    ap.add_argument("--run-dir", default=None, help="Override active run directory.")
    ap.add_argument("-v", "--verbose", action="store_true", help="Verbose stderr logging.")
    ap.add_argument("--check-dirs", action="store_true", default=True,
                    help="Also check whether 60_experiments/E000X_*/ dirs exist "
                         "(default: on; use --no-check-dirs to disable).")
    ap.add_argument("--no-check-dirs", dest="check_dirs", action="store_false")
    args = ap.parse_args(argv)

    run_dir = find_run_dir(args.run_dir) if args.run_dir else require_run_dir(TAG)
    if run_dir is None:
        print(f"[{TAG}] no active run; nothing to validate.")
        return EXIT_OK

    if args.verbose:
        log(TAG, "INFO", f"run_dir = {run_dir}")

    ledger_path = run_dir / LEDGER_REL
    if not ledger_path.is_file():
        log(TAG, "WARN", f"missing ledger: {ledger_path}")
        print(f"[{TAG}] run_dir={run_dir.name}: ledger absent (WARN). Exit 0.")
        return EXIT_OK

    try:
        text = ledger_path.read_text()
    except OSError as e:
        log(TAG, "WARN", f"could not read {ledger_path}: {e}")
        print(f"[{TAG}] run_dir={run_dir.name}: ledger unreadable (WARN). Exit 0.")
        return EXIT_OK

    blocks, occurrences = _split_blocks(text)

    if not blocks:
        log(TAG, "WARN", f"no '## E000X' blocks found in {ledger_path}.")
        print(f"[{TAG}] run_dir={run_dir.name}: no experiment blocks found (WARN). Exit 0.")
        return EXIT_OK

    # Duplicate EIDs (same EID appears in >=2 headers)
    occ_counts = Counter(eid for eid, _ in occurrences)
    duplicates = [eid for eid, c in occ_counts.items() if c > 1]
    for eid in duplicates:
        log(TAG, "WARN", f"duplicate EID {eid} appears {occ_counts[eid]} times in ledger.")

    # Index existing experiment dirs (E000X_*)
    exp_root = run_dir / "60_experiments"
    existing_eid_dirs = {}
    if exp_root.is_dir():
        for sub in exp_root.iterdir():
            if not sub.is_dir():
                continue
            m = EID_DIR_RE.match(sub.name)
            if m:
                existing_eid_dirs.setdefault(m.group(1), []).append(sub.name)

    warnings = []
    missing_field_report = []
    missing_dir_report = []
    judgements = OrderedDict()

    for eid, block in blocks.items():
        missing_labels = [lab for lab in REQUIRED_LABELS if lab not in block]
        if missing_labels:
            msg = f"{eid}: block missing required labels: {', '.join(missing_labels)}"
            log(TAG, "WARN", msg)
            warnings.append(msg)
            missing_field_report.append((eid, missing_labels))
        judgements[eid] = _extract_judgement(block)
        if args.check_dirs:
            if eid not in existing_eid_dirs:
                msg = f"{eid}: referenced in ledger but no 60_experiments/{eid}_*/ directory found."
                log(TAG, "WARN", msg)
                warnings.append(msg)
                missing_dir_report.append(eid)

    # ---- Human summary to stdout ----
    print(f"[{TAG}] run_dir={run_dir.name}")
    print(f"  ledger: {ledger_path.relative_to(run_dir)}")
    print(f"  experiments found: {len(blocks)}")
    print(f"  EIDs + judgements:")
    for eid, j in judgements.items():
        flag = ""
        if occ_counts[eid] > 1:
            flag = f"  [DUP x{occ_counts[eid]}]"
        print(f"    - {eid}  Judgement={j}{flag}")
    if duplicates:
        print(f"  WARN: duplicate EIDs ({len(duplicates)}): {', '.join(duplicates)}")
    if missing_field_report:
        print(f"  WARN: blocks missing required labels ({len(missing_field_report)}):")
        for eid, labs in missing_field_report:
            print(f"    - {eid}: {', '.join(labs)}")
    if args.check_dirs and missing_dir_report:
        print(f"  WARN: referenced EIDs without matching dir ({len(missing_dir_report)}): "
              f"{', '.join(missing_dir_report)}")
    if not warnings:
        print("  warnings: none")
    print(f"[{TAG}] advisory check complete. Exit 0.")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
