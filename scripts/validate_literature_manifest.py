#!/usr/bin/env python3
"""Validate 10_literature/manifest.jsonl for the autonomous-research-workflow.

Advisory / fail-soft: never exits non-zero. Missing file -> WARN + exit 0.
Reports per-category counts, dedup totals, and PASS/PENDING against minimums.
Optionally appends a one-line provenance note (once per day) to
10_literature/provenance_audit.md.
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _arw_common import (
    EXIT_OK, MANIFEST_REL, REPO_ROOT, RUNS_DIR, STATE_REL, append_md, find_run_dir,
    literature_minimums, literature_mode_of, load_json, load_jsonl, log, now_iso,
    require_run_dir,
)

TAG = "validate_literature_manifest"

REQUIRED_KEYS = ["paper_id", "title", "year", "category", "status"]
VALID_CATEGORIES = {"core", "adjacent_a", "adjacent_b", "adjacent_c"}
VALID_STATUSES = {"found", "downloaded", "pdf_failed", "code_missing", "read", "audited"}

# Fallback only; live minimums come from literature_mode_of(run_state).
MINIMUMS = {
    "core": 15,
    "adjacent_a": 5,
    "adjacent_b": 5,
    "adjacent_c": 5,
}
DEDUP_MIN = 30


def _dedup_key(entry):
    arxiv = (entry.get("arxiv_id") or "").strip().lower()
    if arxiv:
        return f"arxiv:{arxiv}"
    doi = (entry.get("doi") or "").strip().lower()
    if doi:
        return f"doi:{doi}"
    return f"title:{(entry.get('title') or '').strip().lower()}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Validate literature manifest.jsonl (advisory).")
    ap.add_argument("--run-dir", default=None, help="Override active run directory.")
    ap.add_argument("-v", "--verbose", action="store_true", help="Verbose stderr logging.")
    args = ap.parse_args(argv)

    run_dir = find_run_dir(args.run_dir) if args.run_dir else require_run_dir(TAG)
    if run_dir is None:
        print(f"[{TAG}] no active run; nothing to validate.")
        return EXIT_OK

    if args.verbose:
        log(TAG, "INFO", f"run_dir = {run_dir}")

    state = load_json(run_dir / STATE_REL, TAG, default={}) or {}
    mode = literature_mode_of(state)
    mins = literature_minimums(mode)
    minimums = {k: mins[k] for k in ("core", "adjacent_a", "adjacent_b", "adjacent_c")}
    dedup_min = int(mins["dedup"])

    manifest_path = run_dir / MANIFEST_REL
    entries = load_jsonl(manifest_path, TAG)
    if not entries:
        # Missing or empty file -> load_jsonl already logged WARN
        print(f"[{TAG}] run_dir={run_dir.name}: manifest empty or absent (WARN). Exit 0.")
        # still try provenance stamp for the day (idempotent) — but only if dir exists
        _maybe_stamp_provenance(run_dir, n=0)
        return EXIT_OK

    cat_counts = Counter()
    status_counts = Counter()
    missing_key_lines = []
    bad_category = []
    bad_status = []
    dedup_counter = Counter()
    dup_report = []

    for i, entry in enumerate(entries, 1):
        if not isinstance(entry, dict):
            log(TAG, "ERROR", f"entry {i} is not a JSON object; skipping.")
            continue
        for k in REQUIRED_KEYS:
            if k not in entry or entry.get(k) in (None, ""):
                log(TAG, "ERROR", f"entry {i} (paper_id={entry.get('paper_id','?')}) "
                                  f"missing required key '{k}'.")
                missing_key_lines.append((i, entry.get("paper_id"), k))
        cat = entry.get("category")
        if cat is not None and cat not in VALID_CATEGORIES:
            log(TAG, "ERROR", f"entry {i} paper_id={entry.get('paper_id','?')} "
                              f"category={cat!r} not in {sorted(VALID_CATEGORIES)}.")
            bad_category.append((i, cat))
        else:
            cat_counts[cat] += 1
        st = entry.get("status")
        if st is not None and st not in VALID_STATUSES:
            log(TAG, "ERROR", f"entry {i} paper_id={entry.get('paper_id','?')} "
                              f"status={st!r} not in {sorted(VALID_STATUSES)}.")
            bad_status.append((i, st))
        else:
            status_counts[st] += 1
        dk = _dedup_key(entry)
        dedup_counter[dk] += 1

    # Duplicate detection (same dedup key used by >=2 entries)
    for dk, c in dedup_counter.items():
        if c > 1:
            msg = f"duplicate literature entry: {dk} appears {c} times"
            log(TAG, "WARN", msg)
            dup_report.append((dk, c))

    dedup_total = len(dedup_counter)

    # PASS/PENDING against minimums (never FAIL-exit). min=0 categories always PASS.
    minimum_results = {}
    for cat, mn in minimums.items():
        got = cat_counts.get(cat, 0)
        if mn <= 0:
            minimum_results[cat] = ("PASS", got, mn)
        else:
            minimum_results[cat] = ("PASS" if got >= mn else "PENDING", got, mn)
    dedup_verdict = ("PASS" if dedup_total >= dedup_min else "PENDING",
                     dedup_total, dedup_min)

    # ---- Human summary to stdout ----
    print(f"[{TAG}] run_dir={run_dir.name}")
    print(f"  literature_mode: {mode}")
    print(f"  manifest entries: {len(entries)}")
    print("  per-category counts:")
    for cat in ["core", "adjacent_a", "adjacent_b", "adjacent_c"]:
        verdict, got, mn = minimum_results[cat]
        print(f"    {cat:12s} = {cat_counts.get(cat,0):3d}  (min {mn})  [{verdict}]")
    print("  per-status counts:")
    for st in sorted(VALID_STATUSES):
        print(f"    {st:12s} = {status_counts.get(st,0)}")
    print(f"  dedup total: {dedup_total}  (min {DEDUP_MIN})  [{dedup_verdict[0]}]")
    if dup_report:
        print(f"  duplicates ({len(dup_report)}):")
        for dk, c in dup_report:
            print(f"    - {dk}: {c}")
    if missing_key_lines:
        print(f"  entries with missing required keys: {len(missing_key_lines)} (see stderr)")
    if bad_category:
        print(f"  entries with bad category: {len(bad_category)} (see stderr)")
    if bad_status:
        print(f"  entries with bad status: {len(bad_status)} (see stderr)")

    overall = "PASS" if all(v[0] == "PASS" for v in minimum_results.values()) and \
                       dedup_verdict[0] == "PASS" else "PENDING"
    print(f"  overall minimums: {overall}")
    print(f"[{TAG}] advisory check complete. Exit 0.")

    _maybe_stamp_provenance(run_dir, n=len(entries))
    return EXIT_OK


def _maybe_stamp_provenance(run_dir: Path, n: int) -> None:
    """Append a one-line provenance note for today if not already present."""
    prov_path = run_dir / "10_literature" / "provenance_audit.md"
    today = now_iso()[:10]
    line = f"- {today}  validate_literature_manifest  entries={n}"
    try:
        existing = prov_path.read_text() if prov_path.is_file() else ""
    except OSError:
        existing = ""
    if today in existing and "validate_literature_manifest" in existing:
        return
    append_md(prov_path, line)


if __name__ == "__main__":
    sys.exit(main())
