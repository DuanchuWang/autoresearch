#!/usr/bin/env python3
"""Create a new research_runs/<YYYY-MM-DD>_<slug>/ workspace.

This is the portable entry point. It does not assume any scientific codebase.
Pass --target-repo to symlink or clone the code under 50_code/target_repo.

Examples:
  python3 scripts/init_run.py --topic my_idea
  python3 scripts/init_run.py --topic my_idea --target-repo /path/to/code
  python3 scripts/init_run.py --topic my_idea --target-repo https://github.com/org/repo
  python3 scripts/init_run.py --topic my_idea --literature-mode directed
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _arw_common import (  # noqa: E402
    EXIT_HARD_FAIL, EXIT_OK, REPO_ROOT, RUNS_DIR, TASKQ_REL, atomic_write_text,
    default_literature_mode, log, now_iso,
)
from generate_next_actions import generate as regen_next_actions  # noqa: E402

TAG = "init_run"
SLUG_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,80}$")

TREE = [
    "state",
    "memory",
    "00_seed",
    "00_seed/rehab_source",
    "10_literature/core/papers",
    "10_literature/core/code",
    "10_literature/adjacent_a/papers",
    "10_literature/adjacent_a/code",
    "10_literature/adjacent_b/papers",
    "10_literature/adjacent_b/code",
    "10_literature/adjacent_c/papers",
    "10_literature/adjacent_c/code",
    "10_literature/bib",
    "20_notes/cards",
    "30_gap",
    "40_proposal/feasibility_reviews",
    "40_proposal/novelty_reviews",
    "40_proposal/reviewer2_reviews",
    "50_code",
    "60_experiments/E0000_sentinel",
    "70_analysis",
    "80_paper/figures",
    "80_paper/tables",
    "90_package",
    "subagent_reports",
]


def _slugify(topic: str) -> str:
    s = topic.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s[:60] or "run"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not text.endswith("\n"):
        text += "\n"
    path.write_text(text, encoding="utf-8")


def _link_or_clone_target(dest: Path, spec: str) -> str:
    """Return a short note. Fail-soft: never raise on clone/link errors."""
    spec = spec.strip()
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() or dest.is_symlink():
        return f"target_repo already present at {dest}"
    if spec.startswith("http://") or spec.startswith("https://") or spec.startswith("git@"):
        url, commit = spec, None
        if "@" in spec.rsplit("/", 1)[-1] and not spec.startswith("git@"):
            url, commit = spec.rsplit("@", 1)
        cmd = ["git", "clone", "--depth", "1", url, str(dest)]
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
            if p.returncode != 0:
                log(TAG, "WARN", f"git clone failed: {p.stderr[-400:]}")
                return f"clone failed: {p.stderr[-200:]}"
            if commit:
                subprocess.run(["git", "-C", str(dest), "fetch", "--depth", "1", "origin", commit],
                               capture_output=True, timeout=120)
                subprocess.run(["git", "-C", str(dest), "checkout", commit],
                               capture_output=True, timeout=60)
            return f"cloned {url} -> {dest}"
        except Exception as e:
            log(TAG, "WARN", f"clone error: {e}")
            return f"clone error: {e}"
    src = Path(spec).expanduser()
    if not src.exists():
        log(TAG, "WARN", f"target_repo path does not exist: {src}")
        return f"missing path: {src}"
    try:
        dest.symlink_to(src.resolve())
        return f"symlink {dest} -> {src.resolve()}"
    except OSError:
        try:
            shutil.copytree(src, dest, symlinks=True)
            return f"copied {src} -> {dest}"
        except Exception as e:
            log(TAG, "WARN", f"copy target_repo failed: {e}")
            return f"copy failed: {e}"


def build_run(run_dir: Path, run_id: str, topic: str, literature_mode: str,
              target_note: str) -> None:
    for rel in TREE:
        (run_dir / rel).mkdir(parents=True, exist_ok=True)

    state = {
        "run_id": run_id,
        "topic": topic,
        "current_state": "S1_RESEARCH_SEED_PLAN",
        "literature_mode": literature_mode,
        "proposal_status": "unlocked",
        "current_branch": f"research/{run_id}-best",
        "best_branch": f"research/{run_id}-best",
        "latest_experiment_id": "E0000",
        "active_goal": f"Scaffold ready. Fill LAUNCH.md / 00_seed and advance to S2.",
        "active_task_ids": [],
        "completed_task_ids": ["T0001"],
        "blocked_task_ids": [],
        "compact_count": 0,
        "last_compact_at": "",
        "last_commit": "",
        "baseline_status": "not_started",
        "publication_candidate_status": "not_ready",
        "stop_continue_count": 0,
        "resource_status": {
            "gpu_slots": 0,
            "active_train_jobs": [],
            "max_parallel_training": 1,
        },
        "gates": {
            "literature_gate": "not_started",
            "proposal_gate": "not_started",
            "baseline_gate": "not_started",
            "experiment_gate": "not_started",
            "paper_gate": "not_started",
            "final_gate": "not_started",
        },
    }
    atomic_write_text(run_dir / "state" / "run_state.json",
                      json.dumps(state, indent=2, ensure_ascii=False))

    tasks = {
        "schema_version": 1,
        "run_id": run_id,
        "tasks": [
            {
                "task_id": "T0001",
                "title": "Initialize run workspace",
                "state": "done",
                "owner_agent": "research-orchestrator",
                "state_ref": "S0_INIT",
                "blocks": ["T0002"],
                "blocked_by": [],
                "artifact_paths": [str(run_dir / "state" / "run_state.json")],
                "notes": f"Created by scripts/init_run.py at {now_iso()}. {target_note}",
            },
            {
                "task_id": "T0002",
                "title": "S1_RESEARCH_SEED_PLAN: write first_plan.md, initial_gap.md, search_queries.md",
                "state": "pending",
                "owner_agent": "research-orchestrator",
                "state_ref": "S1_RESEARCH_SEED_PLAN",
                "blocks": ["T0004"],
                "blocked_by": ["T0001"],
                "artifact_paths": [
                    "00_seed/first_plan.md",
                    "00_seed/initial_gap.md",
                    "00_seed/search_queries.md",
                ],
                "notes": "",
            },
            {
                "task_id": "T0004",
                "title": "S2_LITERATURE_COLLECTION: harvest papers into manifest.jsonl",
                "state": "pending",
                "owner_agent": "paper-harvester",
                "state_ref": "S2_LITERATURE_COLLECTION",
                "blocks": [],
                "blocked_by": ["T0002"],
                "artifact_paths": [
                    "10_literature/manifest.jsonl",
                    "10_literature/provenance_audit.md",
                ],
                "notes": f"literature_mode={literature_mode}",
            },
        ],
    }
    atomic_write_text(run_dir / TASKQ_REL, json.dumps(tasks, indent=2, ensure_ascii=False))

    atomic_write_text(run_dir / "state" / "resource_locks.json", json.dumps({
        "schema_version": 1,
        "run_id": run_id,
        "gpu_slots": [],
        "active_jobs": [],
        "max_parallel_training": 1,
        "max_parallel_downloads": 6,
        "max_parallel_paper_reading": 8,
        "disk_budget_gb": None,
        "rules": [
            "Long training jobs MUST acquire a gpu_slot / active_jobs lock before starting.",
            "Only result-auditor may write 60_experiments/leaderboard.tsv.",
        ],
    }, indent=2))
    _write(run_dir / "state" / "blockers.jsonl", "")
    _write(run_dir / "state" / "current_goal.md",
           f"# Current goal\n\nScaffold for `{run_id}`.\nSee `memory/next_actions.md`.\n")

    _write(run_dir / "memory" / "decisions.md",
           f"# Decisions\n\n- {now_iso()} init_run created `{run_id}` (mode={literature_mode}).\n")
    _write(run_dir / "memory" / "open_questions.md",
           "# Open Questions\n\n"
           "- Fill `LAUNCH.md` `research_direction` and `target_repo` if still blank.\n")
    _write(run_dir / "memory" / "compact_snapshot.md", "# Compact Snapshot\n\n(not yet compacted)\n")
    _write(run_dir / "memory" / "compact_resume_prompt.md",
           "Read `state/run_state.json` then `memory/next_actions.md`. Do not re-ask the operator.\n")

    _write(run_dir / "00_seed" / "first_plan.md", f"# First plan\n\nTopic: {topic}\n\n(rewrite at S1)\n")
    _write(run_dir / "00_seed" / "initial_gap.md", "# Initial gap\n\n(rewrite at S1)\n")
    _write(run_dir / "00_seed" / "search_queries.md", "# Search queries\n\n(rewrite at S1)\n")
    chain_src = REPO_ROOT / "templates" / "argument_chain.md"
    if chain_src.is_file():
        text = (chain_src.read_text(encoding="utf-8")
                .replace("{{TOPIC}}", topic)
                .replace("{{RUN_ID}}", run_id))
        _write(run_dir / "00_seed" / "argument_chain.md", text)
    else:
        _write(run_dir / "00_seed" / "argument_chain.md", f"# Argument chain\n\nTopic: {topic}\n")

    _write(run_dir / "10_literature" / "manifest.jsonl", "")
    _write(run_dir / "10_literature" / "provenance_audit.md", "# Provenance audit\n")
    _write(run_dir / "10_literature" / "bib" / "references.bib", "")

    schema_src = REPO_ROOT / "templates" / "paper_card_schema.md"
    if schema_src.is_file():
        shutil.copy2(schema_src, run_dir / "20_notes" / "paper_card_schema.md")
    else:
        _write(run_dir / "20_notes" / "paper_card_schema.md", "# Paper card schema\n")
    _write(run_dir / "20_notes" / "synthesis_matrix.md", "# Synthesis matrix\n")

    _write(run_dir / "30_gap" / "gap_report.md", "# Gap report\n")
    _write(run_dir / "30_gap" / "idea_candidates.jsonl", "")
    _write(run_dir / "30_gap" / "reviewer2_attacks.md", "# Reviewer2 attacks\n")
    _write(run_dir / "30_gap" / "gap_revision_history.md", "# Gap revision history\n")

    _write(run_dir / "40_proposal" / "proposal.md", "# Research Proposal\n")
    _write(run_dir / "40_proposal" / "claim_ledger.jsonl", "")
    _write(run_dir / "40_proposal" / "evidence_matrix.md", "# Evidence matrix\n")
    _write(run_dir / "40_proposal" / "revision_history.md", "# Proposal revision history\n")
    atomic_write_text(run_dir / "40_proposal" / "proposal_status.json", json.dumps({
        "status": "unlocked", "updated_at": now_iso(),
    }, indent=2))

    prot_src = REPO_ROOT / "templates" / "protected_files.yaml"
    if prot_src.is_file():
        text = prot_src.read_text(encoding="utf-8").replace("{{RUN_ID}}", run_id)
        _write(run_dir / "50_code" / "protected_files.yaml", text)
    _write(run_dir / "50_code" / "repo_map.md", "# Repo map\n\n(fill at S7)\n")
    _write(run_dir / "50_code" / "implementation_plan.md", "# Implementation plan\n")

    _write(run_dir / "60_experiments" / "experiment_ledger.md",
           "# Experiment Ledger\n\n"
           "> Never delete a block; never reuse an EID.\n\n"
           "## E0000 — scaffold sentinel (not a real experiment)\n"
           "- Status: sentinel\n"
           "- Judgement: sentinel\n"
           "- Follow-up: Replace with E0001_baseline at S8.\n")
    _write(run_dir / "60_experiments" / "leaderboard.tsv",
           "eid\tbranch\tcommit\tmetric\tvalue\tdelta\tfair\tjudgement\tts\n")
    _write(run_dir / "60_experiments" / "failure_taxonomy.md", "# Failure taxonomy\n")
    _write(run_dir / "60_experiments" / "E0000_sentinel" / "README.md",
           "Sentinel placeholder. Real experiments start at E0001.\n")

    for name in ("ablations.md", "significance_tests.md", "error_analysis.md", "result_synthesis.md"):
        _write(run_dir / "70_analysis" / name, f"# {name[:-3]}\n")
    argmap_src = REPO_ROOT / "templates" / "writing" / "03_argument_map.md"
    if argmap_src.is_file():
        shutil.copy2(argmap_src, run_dir / "70_analysis" / "argument_map.md")
    else:
        _write(run_dir / "70_analysis" / "argument_map.md", "# Argument map\n")
    for name in ("paper.md", "related_work.md", "method.md", "experiments.md",
                 "limitations.md", "claim_to_evidence.md"):
        _write(run_dir / "80_paper" / name, f"# {name[:-3]}\n")
    contracts_src = REPO_ROOT / "templates" / "writing" / "04_section_contracts.md"
    if contracts_src.is_file():
        shutil.copy2(contracts_src, run_dir / "80_paper" / "section_contracts.md")
    else:
        _write(run_dir / "80_paper" / "section_contracts.md", "# Section contracts\n")
    _write(run_dir / "90_package" / "reproducibility_checklist.md", "# Reproducibility checklist\n")
    atomic_write_text(run_dir / "90_package" / "artifact_manifest.json",
                      json.dumps({"artifacts": []}, indent=2))
    _write(run_dir / "90_package" / "submission_readiness_report.md", "# Submission readiness\n")
    _write(run_dir / "90_package" / "final_gate_report.md", "# Final gate\n")

    _write(run_dir / "README.md",
           f"# Run `{run_id}`\n\n"
           f"- topic: {topic}\n"
           f"- literature_mode: {literature_mode}\n"
           f"- target: {target_note}\n"
           f"- truth: `state/run_state.json`, `state/task_queue.json`, "
           f"`40_proposal/claim_ledger.jsonl`, `00_seed/argument_chain.md`\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Create a portable autoresearch run workspace.")
    ap.add_argument("--topic", required=True, help="Short topic slug or title.")
    ap.add_argument("--run-id", default=None, help="Override RUN_ID (default YYYY-MM-DD_<slug>).")
    ap.add_argument("--literature-mode", default="",
                    help="directed | exploratory. Blank + concrete topic => directed.")
    ap.add_argument("--target-repo", default="",
                    help="Local path or git URL(+@commit) for 50_code/target_repo.")
    ap.add_argument("--force", action="store_true", help="Reuse an existing empty-enough run dir.")
    args = ap.parse_args(argv)

    slug = _slugify(args.topic)
    if args.run_id:
        run_id = args.run_id.strip()
        if not SLUG_RE.match(run_id.replace("-", "x")) and not re.match(r"^\d{4}-\d{2}-\d{2}_[\w-]+$", run_id):
            log(TAG, "ERROR", f"invalid --run-id: {run_id}")
            return EXIT_HARD_FAIL
    else:
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        run_id = f"{day}_{slug}"

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    run_dir = RUNS_DIR / run_id
    if run_dir.exists() and not args.force:
        log(TAG, "ERROR", f"run dir already exists: {run_dir} (pass --force to reuse)")
        return EXIT_HARD_FAIL

    mode = default_literature_mode(args.literature_mode or None, args.topic)
    target_note = "no target_repo yet"
    build_run(run_dir, run_id, args.topic.strip(), mode, target_note)
    if args.target_repo.strip():
        target_note = _link_or_clone_target(run_dir / "50_code" / "target_repo", args.target_repo)
        readme = run_dir / "README.md"
        readme.write_text(readme.read_text(encoding="utf-8").replace("no target_repo yet", target_note),
                          encoding="utf-8")

    pointer = RUNS_DIR / ".active_run"
    pointer.write_text(run_id + "\n", encoding="utf-8")
    try:
        regen_next_actions(run_dir)
    except Exception as e:
        log(TAG, "WARN", f"generate_next_actions failed: {e}")

    log(TAG, "INFO", f"run_dir={run_dir}")
    log(TAG, "INFO", f"active_run={run_id} mode={mode} target={target_note}")
    print(f"created {run_dir}")
    print(f"active run -> {run_id}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
