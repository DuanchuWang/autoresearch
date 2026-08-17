#!/usr/bin/env python3
"""parse_metrics.py — flatten a metrics.json and print a scalar summary.

Walks a metrics JSON, collects leaf numeric values with dotted keys, heuristically
picks a 'primary' metric (or accepts --primary KEY), and prints: exp/dir,
primary metric + value, top-5 metrics by absolute value.

Fail-soft: missing file -> WARN + exit 0. Malformed JSON -> WARN + exit 0
(metrics.json is operator/runner output, not a contract artifact).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# --- stdlib-only helper bootstrap -------------------------------------------------
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _arw_common import (  # noqa: E402
    REPO_ROOT, now_iso, log,
    find_run_dir, require_run_dir,
    EXIT_OK,
)

TAG = "parse_metrics"

# Heuristic primary-metric substrings (case-insensitive). Order = preference.
_PRIMARY_HINTS = ("mAP".lower(), "nds", "ap@", "ap_", "ap30", "ap40", "ap50", "ap70",
                  "acc", "accuracy", "iou", "score", "f1", "precision", "recall")
# Strong negatives — never auto-pick these as primary.
_PRIMARY_NEG = ("loss", "lr", "epoch", "iter", "step", "time", "memory", "mem", "rank")


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _flatten(obj, prefix=""):
    """Yield (dotted_key, scalar_number) for every leaf numeric value."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = f"{prefix}.{k}" if prefix else str(k)
            yield from _flatten(v, key)
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            key = f"{prefix}[{i}]"
            yield from _flatten(v, key)
    elif _is_number(obj):
        yield prefix, obj


def _pick_primary(flat: dict[str, float], forced: str | None):
    """Return (key, value) for the primary metric, or (None, None)."""
    if forced:
        # Direct dotted-key match first.
        if forced in flat:
            return forced, flat[forced]
        # Case-insensitive suffix match.
        for k, v in flat.items():
            if k.lower() == forced.lower():
                return k, v
        # Substring match.
        for k, v in flat.items():
            if forced.lower() in k.lower():
                return k, v
        log(TAG, "WARN", f"--primary '{forced}' not found among {len(flat)} scalar keys.")
        return None, None
    # Heuristic: prefer keys whose tail segment matches a hint and avoids negatives.
    candidates = []
    for k, v in flat.items():
        kl = k.lower()
        if any(neg in kl for neg in _PRIMARY_NEG):
            continue
        tail = kl.rsplit(".", 1)[-1]
        score = 0
        for i, hint in enumerate(_PRIMARY_HINTS):
            if hint in kl:
                # Earlier hints rank higher; prefer matches in the tail.
                score = max(score, (100 - i) + (50 if hint in tail else 0))
        if score > 0:
            candidates.append((score, k, v))
    if not candidates:
        return None, None
    candidates.sort(key=lambda t: (-t[0], t[1]))
    _, k, v = candidates[0]
    return k, v


def _resolve_metrics_path(args) -> Path | None:
    """Resolve the metrics.json to parse from args."""
    if args.metrics_path:
        p = Path(args.metrics_path)
        if p.is_dir():
            # Tolerate passing an exp dir as the positional.
            cand = p / "metrics.json"
            if cand.is_file():
                return cand
            log(TAG, "WARN", f"positional is a directory with no metrics.json: {p}")
            return None
        if not p.is_file():
            log(TAG, "WARN", f"metrics file not found: {p}")
            return None
        return p
    if args.exp_dir:
        ed = Path(args.exp_dir)
        if not ed.is_dir():
            # Maybe it's an EID under the active run.
            run_dir = find_run_dir()
            if run_dir is not None:
                glob = list((run_dir / "60_experiments").glob(f"{ed.name}*"))
                if glob:
                    ed = glob[0]
        cand = ed / "metrics.json"
        if cand.is_file():
            return cand
        log(TAG, "WARN", f"no metrics.json in exp dir: {ed}")
        return None
    return None


def _load_metrics(path: Path):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        log(TAG, "WARN", f"missing file: {path}")
        return None
    except json.JSONDecodeError as e:
        log(TAG, "WARN", f"invalid JSON in {path}: {e}")
        return None


def _fmt(v) -> str:
    if isinstance(v, float):
        # Trim to 6 significant-ish digits without scientific noise.
        return f"{v:.6g}"
    return str(v)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Flatten a metrics.json and print a scalar metric summary."
    )
    ap.add_argument("metrics_path", nargs="?", default=None,
                    help="Path to a metrics.json file (or an exp dir containing one).")
    ap.add_argument("--exp-dir", "-e", default=None,
                    help="Experiment dir holding metrics.json (alternative to the positional).")
    ap.add_argument("--primary", default=None,
                    help="Force a primary metric key (substring or dotted key).")
    ap.add_argument("-v", "--verbose", action="store_true",
                    help="Print all scalar metrics, not just the top-5.")
    args = ap.parse_args(argv)

    if not args.metrics_path and not args.exp_dir:
        ap.error("provide a metrics_path or --exp-dir")

    mpath = _resolve_metrics_path(args)
    if mpath is None:
        return EXIT_OK

    data = _load_metrics(mpath)
    if data is None:
        return EXIT_OK

    flat = dict(_flatten(data))
    if not flat:
        log(TAG, "WARN", f"no scalar numeric metrics found in {mpath}")
        print(f"# {mpath}")
        print(f"# (no scalar numeric metrics) @ {now_iso()}")
        return EXIT_OK

    primary_key, primary_val = _pick_primary(flat, args.primary)

    # Top-N by absolute value (most metrics are small positives; this surfaces the heavy hitters).
    top = sorted(flat.items(), key=lambda kv: abs(kv[1]), reverse=True)
    n = len(flat) if args.verbose else min(5, len(flat))

    label = str(mpath.parent if mpath.name == "metrics.json" else mpath)
    print(f"# parse_metrics @ {now_iso()}")
    print(f"exp/dir: {label}")
    if primary_key is not None:
        print(f"primary_metric: {primary_key}")
        print(f"primary_value:  {_fmt(primary_val)}")
    else:
        print("primary_metric: n/a")
        print("primary_value:  n/a")
    print(f"scalar_count:   {len(flat)}")
    print(f"top_{n}:")
    for k, v in top[:n]:
        marker = "  *" if k == primary_key else "   "
        print(f"{marker} {k} = {_fmt(v)}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
