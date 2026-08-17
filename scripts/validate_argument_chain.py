#!/usr/bin/env python3
"""Validate RUN_DIR/00_seed/argument_chain.md (8-ring archive).

Fail-soft: missing run dir or missing file -> WARN + exit 0.
Hard-fail: file present but missing/invalid traceability, missing 8 rings,
or evidence-ledger claim_id not in claim_ledger.jsonl (when ledger has rows).
"""
from __future__ import annotations

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _arw_common import (  # noqa: E402
    ARGUMENT_CHAIN_REL, CLAIM_LEDGER_REL, EXIT_HARD_FAIL, EXIT_OK,
    find_run_dir, load_jsonl, log, require_run_dir,
)

TAG = "validate_argument_chain"
VALID_TRACE = {"T0", "T1", "T2"}
TRACE_RE = re.compile(r"^traceability:\s*(T[012])\s*$", re.M)
RING_STATUS_RE = re.compile(
    r"^\|\s*([1-8])\s+",
    re.M,
)
CLAIM_ID_RE = re.compile(r"\b(C[A-Za-z0-9_]+)\b")


def _section(text: str, heading: str) -> str:
    """Return markdown from '## heading' until the next '## ' or EOF."""
    pat = re.compile(rf"^##\s+{re.escape(heading)}\s*$", re.M)
    m = pat.search(text)
    if not m:
        return ""
    rest = text[m.end():]
    nxt = re.search(r"^##\s+", rest, re.M)
    return rest[: nxt.start()] if nxt else rest


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Validate argument_chain.md contract.")
    ap.add_argument("--run-dir", default=None, help="Override active run directory.")
    args = ap.parse_args(argv)

    run_dir = find_run_dir(args.run_dir) if args.run_dir else require_run_dir(TAG)
    if run_dir is None:
        print(f"[{TAG}] no active run; nothing to validate.")
        return EXIT_OK

    path = run_dir / ARGUMENT_CHAIN_REL
    if not path.is_file():
        log(TAG, "WARN", f"missing {path}; nothing to validate.")
        print(f"[{TAG}] run_dir={run_dir.name}: argument_chain absent (WARN). Exit 0.")
        return EXIT_OK

    text = path.read_text(encoding="utf-8")
    hard = False
    warnings = []

    tm = TRACE_RE.search(text)
    if not tm:
        log(TAG, "ERROR", "missing or invalid frontmatter traceability: T0|T1|T2")
        hard = True
        grade = None
    else:
        grade = tm.group(1)
        if grade not in VALID_TRACE:
            log(TAG, "ERROR", f"traceability={grade!r} not in {sorted(VALID_TRACE)}")
            hard = True

    status_sec = _section(text, "3. Eight-ring status")
    status_nums = {m.group(1) for m in RING_STATUS_RE.finditer(status_sec)}
    if status_nums != {str(i) for i in range(1, 9)}:
        log(TAG, "ERROR",
            f"eight-ring status table must have rows 1–8 (got {sorted(status_nums)})")
        hard = True

    audit_sec = _section(text, "2. Source-audit table (default for T2; R1 carrier)")
    if not audit_sec:
        audit_sec = _section(text, "2. Source-audit table")
    audit_nums = {m.group(1) for m in RING_STATUS_RE.finditer(audit_sec)}
    if grade == "T2" and audit_nums != {str(i) for i in range(1, 9)}:
        log(TAG, "ERROR",
            f"T2 source-audit table must have rows 1–8 (got {sorted(audit_nums)})")
        hard = True
    elif grade in {"T0", "T1"} and audit_nums and audit_nums != {str(i) for i in range(1, 9)}:
        warnings.append("source-audit rows incomplete")

    ledger_claims = load_jsonl(run_dir / CLAIM_LEDGER_REL, TAG) or []
    known_ids = {c.get("claim_id") for c in ledger_claims if isinstance(c, dict)}
    known_ids.discard(None)
    ev_sec = _section(text, "5. Evidence ledger (T4; claim_id = claim_ledger.jsonl)")
    if not ev_sec:
        ev_sec = _section(text, "5. Evidence ledger")
    orphan = []
    for line in ev_sec.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if not cells or cells[0] in {"claim_id", "----------"}:
            continue
        cid = cells[0]
        if cid and cid != "claim_id" and not cid.startswith("-"):
            if known_ids and cid not in known_ids:
                orphan.append(cid)
    if orphan:
        log(TAG, "ERROR",
            f"evidence ledger claim_id not in claim_ledger.jsonl: {orphan[:8]}")
        hard = True

    print(f"[{TAG}] run_dir={run_dir.name}")
    print(f"  traceability = {grade or '<missing>'}")
    print(f"  ring_rows    = {sorted(status_nums)}")
    print(f"  warnings     = {', '.join(warnings) if warnings else 'none'}")
    if hard:
        print(f"[{TAG}] HARD FAIL: {path}. Exit 1.")
        return EXIT_HARD_FAIL
    print(f"[{TAG}] OK. Exit 0.")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
