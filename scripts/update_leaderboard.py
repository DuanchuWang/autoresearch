#!/usr/bin/env python3
"""update_leaderboard.py — upsert one experiment row into 60_experiments/leaderboard.tsv.

Reads the exp's metrics.json (primary metric via heuristic), the report.md Judgement
line, and writes/updates a TSV row keyed by eid. Replaces in place if the eid already
exists; otherwise appends. The header row is always preserved.

Fail-soft: missing metrics.json / report.md -> WARN + 'n/a' in the cell, exit 0.
The leaderboard file itself is created with the canonical header if absent.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

# --- stdlib-only helper bootstrap -------------------------------------------------
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _arw_common import (  # noqa: E402
    REPO_ROOT, now_iso, log,
    find_run_dir, require_run_dir,
    EXIT_OK,
)

TAG = "leaderboard"

# Canonical header — must match the existing leaderboard.tsv exactly.
HEADER = ["eid", "contribution", "dataset", "seed", "primary_metric",
          "primary_value", "baseline_delta", "judgement", "commit", "report_path"]

_PRIMARY_HINTS = ("mAP".lower(), "nds", "ap@", "ap_", "ap30", "ap40", "ap50", "ap70",
                  "acc", "accuracy", "iou", "score", "f1")
_PRIMARY_NEG = ("loss", "lr", "epoch", "iter", "step", "time", "memory", "mem", "rank")
BASELINE_EID = "E0001"


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _flatten(obj, prefix=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = f"{prefix}.{k}" if prefix else str(k)
            yield from _flatten(v, key)
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            yield from _flatten(v, f"{prefix}[{i}]")
    elif _is_number(obj):
        yield prefix, obj


def _pick_primary(flat: dict[str, float]):
    """Heuristic primary metric (mirrors parse_metrics.py). Returns (key, value) or (None, None)."""
    candidates = []
    for k, v in flat.items():
        kl = k.lower()
        if any(neg in kl for neg in _PRIMARY_NEG):
            continue
        tail = kl.rsplit(".", 1)[-1]
        score = 0
        for i, hint in enumerate(_PRIMARY_HINTS):
            if hint in kl:
                score = max(score, (100 - i) + (50 if hint in tail else 0))
        if score > 0:
            candidates.append((score, k, v))
    if not candidates:
        return None, None
    candidates.sort(key=lambda t: (-t[0], t[1]))
    return candidates[0][1], candidates[0][2]


def _discover_exp_dir(run_dir: Path, eid: str):
    """Find RUN_DIR/60_experiments/<eid>_* (or exactly <eid>) ."""
    base = run_dir / "60_experiments"
    if not base.is_dir():
        return None
    exact = base / eid
    if exact.is_dir():
        return exact
    hits = sorted(base.glob(f"{eid}_*"))
    hits = [h for h in hits if h.is_dir()]
    return hits[0] if hits else None


def _load_json(path: Path):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        log(TAG, "WARN", f"missing file: {path}")
        return None
    except json.JSONDecodeError as e:
        log(TAG, "WARN", f"invalid JSON in {path}: {e}")
        return None


# Match the report's Judgement line under either markdown list or 'Key:' form.
_JUDGE_RE = re.compile(r"^\s*(?:[-*]\s*)?Judg(?:e|ment)\s*[:：]\s*(.+?)\s*$",
                       re.IGNORECASE | re.MULTILINE)
_CONTRIB_RE = re.compile(r"^\s*(?:[-*]\s*)?Contribution\s*[:：]\s*(.+?)\s*$",
                         re.IGNORECASE | re.MULTILINE)
_DATASET_RE = re.compile(r"^\s*(?:[-*]\s*)?Dataset\s*[:：]\s*(.+?)\s*$",
                         re.IGNORECASE | re.MULTILINE)
_SEED_RE = re.compile(r"^\s*(?:[-*]\s*)?Seed\s*[:：]\s*(.+?)\s*$",
                      re.IGNORECASE | re.MULTILINE)


def _field(report_text: str, rx: re.Pattern) -> str:
    m = rx.search(report_text)
    return m.group(1).strip() if m else ""


def _clean_cell(s: str) -> str:
    """Make a value TSV-safe (no tabs / newlines)."""
    if s is None:
        return "n/a"
    s = str(s).replace("\t", " ").replace("\r", " ").replace("\n", " ").strip()
    return s if s else "n/a"


def _fmt_num(v) -> str:
    if isinstance(v, float):
        return f"{v:.6g}"
    return str(v)


def _read_leaderboard(path: Path):
    """Return (header_list, rows_list_of_lists). Creates with HEADER if missing."""
    if not path.is_file():
        log(TAG, "INFO", f"leaderboard not found; creating {path} with canonical header.")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\t".join(HEADER) + "\n")
        return HEADER, []
    lines = path.read_text().splitlines()
    if not lines:
        path.write_text("\t".join(HEADER) + "\n")
        return HEADER, []
    header = lines[0].split("\t")
    rows = [ln.split("\t") for ln in lines[1:] if ln.strip()]
    return header, rows


def _baseline_value(rows, header):
    """Pull the primary_value cell for BASELINE_EID if present, else None."""
    try:
        vi = header.index("primary_value")
        ei = header.index("eid")
    except ValueError:
        return None
    for r in rows:
        if len(r) > vi and r[ei].strip() == BASELINE_EID:
            try:
                return float(r[vi])
            except (ValueError, TypeError):
                return None
    return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Upsert one experiment row into 60_experiments/leaderboard.tsv."
    )
    ap.add_argument("--eid", required=True, help="Experiment ID, e.g. E0002.")
    ap.add_argument("--exp-dir", default=None,
                    help="Experiment dir (else discovered as RUN_DIR/60_experiments/<eid>_*)")
    ap.add_argument("--commit", default=None,
                    help="Commit hash for the result commit (optional).")
    ap.add_argument("--report-path", default=None,
                    help="Path to report.md (default: <exp_dir>/report.md).")
    ap.add_argument("--run-dir", default=None,
                    help="Override run dir (defaults to $ARW_RUN_DIR / .active_run / newest).")
    args = ap.parse_args(argv)

    run_dir = find_run_dir(args.run_dir) if args.run_dir else require_run_dir(TAG)
    if run_dir is None:
        return EXIT_OK

    eid = args.eid.strip()
    if not re.fullmatch(r"E\d{4}", eid):
        log(TAG, "WARN", f"eid '{eid}' is not of form E000X; proceeding anyway.")

    # Resolve exp dir.
    if args.exp_dir:
        exp_dir = Path(args.exp_dir)
        if not exp_dir.is_dir():
            # Maybe a name under the active run.
            disc = _discover_exp_dir(run_dir, exp_dir.name)
            exp_dir = disc or exp_dir
    else:
        exp_dir = _discover_exp_dir(run_dir, eid)
        if exp_dir is None:
            log(TAG, "WARN", f"no exp dir found for {eid} under {run_dir / '60_experiments'}.")

    metrics_path = (exp_dir / "metrics.json") if exp_dir else None
    report_path = Path(args.report_path) if args.report_path else (
        (exp_dir / "report.md") if exp_dir else None
    )

    # Metrics.
    primary_metric = "n/a"
    primary_value = "n/a"
    if metrics_path and metrics_path.is_file():
        data = _load_json(metrics_path)
        if data is not None:
            flat = dict(_flatten(data))
            if flat:
                pk, pv = _pick_primary(flat)
                if pk is not None:
                    primary_metric = _clean_cell(pk)
                    primary_value = _clean_cell(_fmt_num(pv))
            else:
                log(TAG, "WARN", f"no scalar metrics in {metrics_path}")
    else:
        log(TAG, "WARN", f"no metrics.json at {metrics_path}")

    # Report fields.
    contribution = "n/a"
    dataset = "n/a"
    seed = "n/a"
    judgement = "n/a"
    if report_path and report_path.is_file():
        try:
            rtext = report_path.read_text()
            contribution = _clean_cell(_field(rtext, _CONTRIB_RE) or "n/a")
            dataset = _clean_cell(_field(rtext, _DATASET_RE) or "n/a")
            seed = _clean_cell(_field(rtext, _SEED_RE) or "n/a")
            judgement = _clean_cell(_field(rtext, _JUDGE_RE) or "n/a")
        except Exception as e:
            log(TAG, "WARN", f"could not read report {report_path}: {e}")
    else:
        log(TAG, "WARN", f"no report.md at {report_path}")

    lb_path = run_dir / "60_experiments" / "leaderboard.tsv"
    header, rows = _read_leaderboard(lb_path)

    # Baseline delta vs E0001 (only meaningful for the primary metric if numeric).
    baseline_delta = "n/a"
    base_val = _baseline_value(rows, header)
    if (eid != BASELINE_EID and base_val is not None
            and primary_value not in ("n/a", "")):
        try:
            cur = float(primary_value)
            baseline_delta = _clean_cell(f"{cur - base_val:+.6g}")
        except (ValueError, TypeError):
            baseline_delta = "n/a"

    commit = _clean_cell(args.commit) if args.commit else "n/a"
    report_cell = _clean_cell(str(report_path)) if report_path else "n/a"

    # Build the row aligned to HEADER (pad/truncate defensively).
    row_map = {
        "eid": eid,
        "contribution": contribution,
        "dataset": dataset,
        "seed": seed,
        "primary_metric": primary_metric,
        "primary_value": primary_value,
        "baseline_delta": baseline_delta,
        "judgement": judgement,
        "commit": commit,
        "report_path": report_cell,
    }
    new_row = [row_map.get(h, "n/a") for h in HEADER]

    # Upsert: replace if eid present, else append.
    try:
        ei = header.index("eid")
    except ValueError:
        # No eid column — preserve as-is, just append.
        ei = -1
    replaced = False
    if ei >= 0:
        for i, r in enumerate(rows):
            if len(r) > ei and r[ei].strip() == eid:
                rows[i] = new_row
                replaced = True
                break
    if not replaced:
        rows.append(new_row)

    # Write back.
    try:
        lb_path.parent.mkdir(parents=True, exist_ok=True)
        out_lines = ["\t".join(HEADER)] + ["\t".join(r) for r in rows]
        lb_path.write_text("\n".join(out_lines) + "\n")
    except Exception as e:
        log(TAG, "ERROR", f"failed to write leaderboard {lb_path}: {e}")
        return EXIT_OK

    print("\t".join(new_row))
    print("leaderboard updated")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
