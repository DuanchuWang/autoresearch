"""Shared helpers for the autonomous-research-workflow scripts.

Stdlib-only so it runs on any python3. Each script does:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from _arw_common import ...

Active-run discovery order:
  1. $ARW_RUN_DIR  (absolute path to a run directory)
  2. research_runs/.active_run  (one-line file holding a RUN_ID)
  3. newest directory under research_runs/

Fail-soft policy: missing data / repo / config never crashes a script — it logs a WARN
(and optionally appends to state/blockers.jsonl or memory/open_questions.md) and exits 0.
Hard validation failures (malformed state that breaks the workflow contract) exit non-zero.
"""
from __future__ import annotations
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = REPO_ROOT / "research_runs"

# Canonical sub-paths relative to a run dir (single source of truth for all scripts).
STATE_REL = "state/run_state.json"
TASKQ_REL = "state/task_queue.json"
BLOCKERS_REL = "state/blockers.jsonl"
LEDGER_REL = "60_experiments/experiment_ledger.md"
CLAIM_LEDGER_REL = "40_proposal/claim_ledger.jsonl"
MANIFEST_REL = "10_literature/manifest.jsonl"
ARGUMENT_CHAIN_REL = "00_seed/argument_chain.md"
OPEN_Q_REL = "memory/open_questions.md"
DECISIONS_REL = "memory/decisions.md"
SNAPSHOT_REL = "memory/compact_snapshot.md"
NEXT_ACTIONS_REL = "memory/next_actions.md"
NEXT_ACTIONS_JOURNAL_REL = "memory/next_actions.journal.md"
PROTECTED_YAML_REL = "50_code/protected_files.yaml"
NEXT_ACTIONS_MARKER = "<!-- ARW_GENERATED_NEXT_ACTIONS -->"
MAX_NEXT_ACTION_LINES = 22

# literature_mode is optional on existing runs (missing => exploratory).
VALID_LITERATURE_MODES = {"directed", "exploratory"}
LITERATURE_MINIMUMS = {
    "exploratory": {
        "core": 15, "adjacent_a": 5, "adjacent_b": 5, "adjacent_c": 5, "dedup": 30,
    },
    "directed": {
        # Operator already named a concrete direction: harvest the kill-shots,
        # not a 30-paper adjacent quota. adjacent_a is the opposing-paper bucket.
        "core": 8, "adjacent_a": 5, "adjacent_b": 0, "adjacent_c": 0, "dedup": 12,
    },
}

# Valid state-machine states (see CLAUDE.md §4).
VALID_STATES = {
    "S0_INIT", "S1_RESEARCH_SEED_PLAN", "S2_LITERATURE_COLLECTION",
    "S3_PAPER_READING_CARDS", "S4_GAP_SYNTHESIS", "S5_IDEA_EVALUATION",
    "S6_PROPOSAL_LOCK", "S7_REPO_AUDIT_AND_EXPERIMENT_PLAN", "S8_BASELINE_REPRODUCTION",
    "S9_IMPLEMENT_IDEA_ATOMICALLY", "S10_CODE_REVIEW_AND_SMOKE_TEST",
    "S11_EXPERIMENT_RUN", "S12_RESULT_AUDIT", "S13_KEEP_AND_EXPAND_ABLATION",
    "S14_FAILURE_ANALYSIS_AND_RETRY", "S15_FULL_ABLATION_AND_MULTI_SEED",
    "S16_PAPER_DRAFT", "S17_INTERNAL_REVIEW", "S18_PUBLICATION_CANDIDATE_PACKAGE",
    "S_EVAL_HARNESS_REVISION", "S_BLOCKED_EXTERNAL", "S_FAIL_CLOSED_REPORT",
}

EXIT_OK = 0
EXIT_HARD_FAIL = 1          # contract violation — surface to caller
EXIT_SOFT_FAIL = 0          # missing data — already logged, do not break flows


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(tag: str, level: str, msg: str) -> None:
    """Emit a prefixed line to stderr (never stdout — stdout is reserved for hook JSON)."""
    print(f"[{tag}][{level}] {msg}", file=sys.stderr, flush=True)


def find_run_dir(explicit: str | None = None) -> Path | None:
    """Resolve the active run directory, or None if none exists."""
    cand = explicit or os.environ.get("ARW_RUN_DIR")
    if cand:
        p = Path(cand).expanduser().resolve()
        return p if p.is_dir() else None
    pointer = RUNS_DIR / ".active_run"
    if pointer.is_file():
        rid = pointer.read_text().strip()
        if rid:
            p = (RUNS_DIR / rid).resolve()
            if p.is_dir():
                return p
    if RUNS_DIR.is_dir():
        subs = sorted(
            (d for d in RUNS_DIR.iterdir() if d.is_dir() and not d.name.startswith(".")),
            key=lambda d: d.stat().st_mtime,
            reverse=True,
        )
        return subs[0] if subs else None
    return None


def require_run_dir(tag: str) -> Path | None:
    rd = find_run_dir()
    if rd is None:
        log(tag, "WARN", f"no active run found under {RUNS_DIR}; set $ARW_RUN_DIR or "
                         f"write a RUN_ID into research_runs/.active_run. Nothing to do.")
    return rd


def load_json(path: Path, tag: str, default=None):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        log(tag, "WARN", f"missing file: {path}")
        return default
    except json.JSONDecodeError as e:
        log(tag, "ERROR", f"invalid JSON in {path}: {e}")
        return default


def load_jsonl(path: Path, tag: str) -> list:
    if not path.is_file():
        log(tag, "WARN", f"missing file: {path}")
        return []
    out = []
    for i, line in enumerate(path.read_text().splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError as e:
            log(tag, "ERROR", f"invalid JSON at {path}:{i}: {e}")
    return out


def append_jsonl(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def append_md(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(text.rstrip() + "\n")


def record_blocker(run_dir: Path, blocker_id: str, category: str, title: str,
                   impact: str, workaround: str) -> None:
    append_jsonl(run_dir / BLOCKERS_REL, {
        "blocker_id": blocker_id, "raised_at": now_iso()[:10], "category": category,
        "title": title, "impact": impact, "workaround": workaround,
        "status": "open", "resolved_at": "",
    })


def note_open_question(run_dir: Path, text: str) -> None:
    append_md(run_dir / OPEN_Q_REL, f"\n## AUTO @ {now_iso()}\n- {text}\n")


def atomic_write_text(path: Path, text: str) -> None:
    """Write UTF-8 text atomically via a temp file in the same directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = text if text.endswith("\n") else text + "\n"
    fd, tmp = tempfile.mkstemp(prefix=".tmp.", suffix=path.suffix or ".txt",
                               dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass


def literature_mode_of(state) -> str:
    """Return directed|exploratory. Missing/blank/unknown → exploratory (fail-soft)."""
    if not isinstance(state, dict):
        return "exploratory"
    raw = state.get("literature_mode")
    if raw is None:
        return "exploratory"
    m = str(raw).strip().lower()
    if m in VALID_LITERATURE_MODES:
        return m
    if m in ("", "default", "待定", "默认"):
        return "exploratory"
    return "exploratory"


def default_literature_mode(explicit, research_direction: str = "") -> str:
    """LAUNCH.md default: explicit directed|exploratory wins; else directed iff direction is concrete."""
    if explicit is not None and str(explicit).strip() != "":
        m = str(explicit).strip().lower()
        if m in VALID_LITERATURE_MODES:
            return m
        if m in ("default", "待定", "默认"):
            pass  # fall through to direction heuristic
        else:
            return "exploratory"
    rd = str(research_direction or "").strip()
    if rd and rd not in ("待定", "默认", "default"):
        return "directed"
    return "exploratory"


def literature_minimums(mode: str) -> dict:
    key = mode if mode in LITERATURE_MINIMUMS else "exploratory"
    return dict(LITERATURE_MINIMUMS[key])


def completed_task_ids(run_state, tasks) -> set:
    """Union of run_state.completed_task_ids and task_queue rows with state=done.

    The two sources drift in long runs; dependents must unblock when *either*
    source says the blocker is done.
    """
    out: set[str] = set()
    if isinstance(run_state, dict):
        for tid in run_state.get("completed_task_ids") or []:
            if tid:
                out.add(str(tid))
    for t in tasks or []:
        if not isinstance(t, dict):
            continue
        if t.get("state") == "done" and t.get("task_id"):
            out.add(str(t["task_id"]))
    return out


def task_blockers_satisfied(task: dict, completed_ids) -> bool:
    blockers = task.get("blocked_by") or []
    done = set(completed_ids or [])
    return all(b in done for b in blockers)


def iter_runnable_tasks(tasks, completed_ids=None) -> list:
    """in_progress first (queue order), then pending whose blockers are done."""
    done = set(completed_ids or [])
    in_progress = []
    pending_ready = []
    for t in tasks or []:
        if not isinstance(t, dict):
            continue
        st = t.get("state")
        if st == "in_progress":
            in_progress.append(t)
        elif st == "pending" and task_blockers_satisfied(t, done):
            pending_ready.append(t)
    return in_progress + pending_ready


def first_runnable_task(tasks, completed_ids=None):
    items = iter_runnable_tasks(tasks, completed_ids)
    return items[0] if items else None
