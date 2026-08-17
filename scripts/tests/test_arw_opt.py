#!/usr/bin/env python3
"""Tests for the ARW next_actions generator, literature_mode, and agent path contract.

Run: python3 scripts/tests/test_arw_opt.py
Must not touch research_runs/ (uses TemporaryDirectory).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
REPO = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

from _arw_common import (  # noqa: E402
    MAX_NEXT_ACTION_LINES, NEXT_ACTIONS_JOURNAL_REL, NEXT_ACTIONS_MARKER,
    NEXT_ACTIONS_REL, STATE_REL, TASKQ_REL, completed_task_ids,
    default_literature_mode, first_runnable_task, iter_runnable_tasks,
    literature_minimums, literature_mode_of,
)
from generate_next_actions import build_next_actions, generate  # noqa: E402
import validate_run_state  # noqa: E402
import validate_literature_manifest  # noqa: E402


def _write_run(root: Path, state: dict, tasks: list, manifest_lines=None) -> Path:
    (root / "state").mkdir(parents=True)
    (root / "memory").mkdir()
    (root / "10_literature").mkdir()
    (root / STATE_REL).write_text(json.dumps(state), encoding="utf-8")
    (root / TASKQ_REL).write_text(json.dumps({"tasks": tasks}), encoding="utf-8")
    if manifest_lines is not None:
        (root / "10_literature" / "manifest.jsonl").write_text(
            "".join(json.dumps(x) + "\n" for x in manifest_lines), encoding="utf-8")
    return root


def _base_state(**kw):
    s = {
        "run_id": "test-run",
        "topic": "unit-test",
        "current_state": "S2_LITERATURE_COLLECTION",
        "proposal_status": "unlocked",
        "current_branch": "",
        "best_branch": "",
        "latest_experiment_id": "E0000",
        "active_goal": "harvest papers",
        "active_task_ids": ["T0004"],
        "completed_task_ids": ["T0001"],
        "blocked_task_ids": [],
        "compact_count": 0,
        "gates": {
            "literature_gate": "in_progress",
            "proposal_gate": "not_started",
            "baseline_gate": "not_started",
            "experiment_gate": "not_started",
            "paper_gate": "not_started",
            "final_gate": "not_started",
        },
        "resource_status": {"gpu_slots": 1, "active_train_jobs": [], "max_parallel_training": 1},
        "baseline_status": "not_started",
    }
    s.update(kw)
    return s


class TestLiteratureMode(unittest.TestCase):
    def test_missing_is_exploratory(self):
        self.assertEqual(literature_mode_of({}), "exploratory")
        self.assertEqual(literature_mode_of(None), "exploratory")

    def test_case_insensitive(self):
        self.assertEqual(literature_mode_of({"literature_mode": "Directed"}), "directed")

    def test_unknown_fail_soft_to_exploratory(self):
        self.assertEqual(literature_mode_of({"literature_mode": "foo"}), "exploratory")

    def test_minimums(self):
        e = literature_minimums("exploratory")
        d = literature_minimums("directed")
        self.assertEqual(e["core"], 15)
        self.assertEqual(e["dedup"], 30)
        self.assertEqual(d["core"], 8)
        self.assertEqual(d["adjacent_a"], 5)
        self.assertEqual(d["adjacent_b"], 0)
        self.assertEqual(d["dedup"], 12)

    def test_launch_defaults(self):
        self.assertEqual(default_literature_mode("directed", ""), "directed")
        self.assertEqual(default_literature_mode("exploratory", "some direction"), "exploratory")
        self.assertEqual(default_literature_mode("", "improve PointPillars phase aliasing"), "directed")
        self.assertEqual(default_literature_mode("待定", "improve PointPillars"), "directed")
        self.assertEqual(default_literature_mode(None, ""), "exploratory")
        self.assertEqual(default_literature_mode(None, "待定"), "exploratory")


class TestRunnable(unittest.TestCase):
    def test_pending_empty_blockers(self):
        tasks = [{"task_id": "T1", "state": "pending", "blocked_by": []}]
        self.assertEqual(first_runnable_task(tasks, set()).get("task_id"), "T1")

    def test_union_completed_unblocks(self):
        tasks = [
            {"task_id": "T0045", "state": "done", "blocked_by": []},
            {"task_id": "T0047", "state": "pending", "blocked_by": ["T0045"]},
        ]
        # run_state does NOT list T0045 as completed — queue does
        done = completed_task_ids({"completed_task_ids": []}, tasks)
        self.assertIn("T0045", done)
        ids = [t["task_id"] for t in iter_runnable_tasks(tasks, done)]
        self.assertEqual(ids, ["T0047"])

    def test_unfinished_blocker_not_runnable(self):
        tasks = [{"task_id": "T2", "state": "pending", "blocked_by": ["T1"]}]
        self.assertIsNone(first_runnable_task(tasks, set()))

    def test_in_progress_first(self):
        tasks = [
            {"task_id": "T1", "state": "pending", "blocked_by": []},
            {"task_id": "T2", "state": "in_progress", "blocked_by": []},
        ]
        self.assertEqual(first_runnable_task(tasks, set()).get("task_id"), "T2")


class TestGenerateNextActions(unittest.TestCase):
    def test_marker_and_line_cap(self):
        with tempfile.TemporaryDirectory() as td:
            rd = _write_run(Path(td), _base_state(), [
                {"task_id": "T0004", "title": "harvest", "state": "pending",
                 "owner_agent": "paper-harvester", "blocked_by": []},
            ])
            body = generate(rd)
            self.assertTrue(body.lstrip().startswith(NEXT_ACTIONS_MARKER))
            self.assertLessEqual(len(body.splitlines()), MAX_NEXT_ACTION_LINES)
            self.assertIn("T0004", body)
            self.assertIn("S2_LITERATURE_COLLECTION", body)

    def test_archives_handwritten_once(self):
        with tempfile.TemporaryDirectory() as td:
            rd = _write_run(Path(td), _base_state(), [])
            handwritten = "# Next Actions\n\n" + ("do this then that\n" * 40)
            (rd / NEXT_ACTIONS_REL).write_text(handwritten, encoding="utf-8")
            generate(rd)
            journal = (rd / NEXT_ACTIONS_JOURNAL_REL).read_text(encoding="utf-8")
            self.assertIn("do this then that", journal)
            new = (rd / NEXT_ACTIONS_REL).read_text(encoding="utf-8")
            self.assertTrue(new.lstrip().startswith(NEXT_ACTIONS_MARKER))
            self.assertNotIn("do this then that", new)
            # second generate must not grow the journal
            j1 = (rd / NEXT_ACTIONS_JOURNAL_REL).stat().st_size
            generate(rd)
            j2 = (rd / NEXT_ACTIONS_JOURNAL_REL).stat().st_size
            self.assertEqual(j1, j2)

    def test_no_archive_when_already_generated(self):
        with tempfile.TemporaryDirectory() as td:
            rd = _write_run(Path(td), _base_state(), [])
            generate(rd, archive=True)
            self.assertFalse((rd / NEXT_ACTIONS_JOURNAL_REL).is_file())

    def test_dry_run_does_not_write(self):
        with tempfile.TemporaryDirectory() as td:
            rd = _write_run(Path(td), _base_state(), [])
            cp = subprocess.run(
                [sys.executable, str(SCRIPTS / "generate_next_actions.py"),
                 "--run-dir", str(rd), "--dry-run"],
                capture_output=True, text=True, cwd=str(REPO),
            )
            self.assertEqual(cp.returncode, 0)
            self.assertIn(NEXT_ACTIONS_MARKER, cp.stdout)
            self.assertFalse((rd / NEXT_ACTIONS_REL).is_file())

    def test_missing_run_exit_0(self):
        cp = subprocess.run(
            [sys.executable, str(SCRIPTS / "generate_next_actions.py"),
             "--run-dir", "/no/such/run/dir"],
            capture_output=True, text=True, cwd=str(REPO),
        )
        self.assertEqual(cp.returncode, 0)

    def test_goal_is_one_line(self):
        goal = "line1\nline2\n" + ("x" * 400)
        body = build_next_actions(Path("/tmp"), _base_state(active_goal=goal), [])
        goal_lines = [ln for ln in body.splitlines() if ln.startswith("- EID:")]
        self.assertEqual(len(goal_lines), 1)
        self.assertNotIn("\n", goal_lines[0])


class TestValidators(unittest.TestCase):
    def test_missing_literature_mode_ok(self):
        with tempfile.TemporaryDirectory() as td:
            rd = _write_run(Path(td), _base_state(), [])
            rc = validate_run_state.main(["--run-dir", str(rd)])
            self.assertEqual(rc, 0)

    def test_directed_mode_ok(self):
        with tempfile.TemporaryDirectory() as td:
            rd = _write_run(Path(td), _base_state(literature_mode="directed"), [])
            rc = validate_run_state.main(["--run-dir", str(rd)])
            self.assertEqual(rc, 0)

    def test_bad_literature_mode_hard_fail(self):
        with tempfile.TemporaryDirectory() as td:
            rd = _write_run(Path(td), _base_state(literature_mode="foo"), [])
            rc = validate_run_state.main(["--run-dir", str(rd)])
            self.assertEqual(rc, 1)

    def test_directed_manifest_pass_with_8_core(self):
        papers = []
        for i in range(8):
            papers.append({"paper_id": f"P{i:04d}", "title": f"t{i}", "year": "2024",
                           "category": "core", "status": "read"})
        for i in range(5):
            papers.append({"paper_id": f"A{i:04d}", "title": f"a{i}", "year": "2024",
                           "category": "adjacent_a", "status": "read"})
        with tempfile.TemporaryDirectory() as td:
            rd = _write_run(Path(td), _base_state(literature_mode="directed"), [], papers)
            cp = subprocess.run(
                [sys.executable, str(SCRIPTS / "validate_literature_manifest.py"),
                 "--run-dir", str(rd)],
                capture_output=True, text=True, cwd=str(REPO),
            )
            self.assertEqual(cp.returncode, 0)
            self.assertIn("overall minimums: PASS", cp.stdout)
            self.assertIn("literature_mode: directed", cp.stdout)

    def test_exploratory_same_corpus_pending(self):
        papers = []
        for i in range(8):
            papers.append({"paper_id": f"P{i:04d}", "title": f"t{i}", "year": "2024",
                           "category": "core", "status": "read"})
        with tempfile.TemporaryDirectory() as td:
            rd = _write_run(Path(td), _base_state(literature_mode="exploratory"), [], papers)
            cp = subprocess.run(
                [sys.executable, str(SCRIPTS / "validate_literature_manifest.py"),
                 "--run-dir", str(rd)],
                capture_output=True, text=True, cwd=str(REPO),
            )
            self.assertEqual(cp.returncode, 0)
            self.assertIn("overall minimums: PENDING", cp.stdout)


class TestAgentPaths(unittest.TestCase):
    def test_no_hardcoded_scaffold_run(self):
        agents = REPO / ".claude" / "agents"
        leftover = []
        for p in agents.glob("*.md"):
            text = p.read_text(encoding="utf-8")
            if "2026-07-06_autonomous_research_workflow" in text:
                leftover.append(p.name)
            if "/root/code/mmdetection3d" in text:
                leftover.append(p.name + ":host-absolute")
        self.assertEqual(leftover, [])

    def test_run_state_path_has_state_dir(self):
        bad = []
        for p in (REPO / ".claude" / "agents").glob("*.md"):
            text = p.read_text(encoding="utf-8")
            if "`RUN_DIR/run_state.json`" in text:
                bad.append(p.name)
        self.assertEqual(bad, [])


class TestPortableHooks(unittest.TestCase):
    def test_settings_hooks_have_no_host_absolute_paths(self):
        settings = json.loads((REPO / ".claude" / "settings.json").read_text(encoding="utf-8"))
        blob = json.dumps(settings)
        self.assertNotIn("/root/", blob)
        self.assertIn("scripts/arw_hook.sh", blob)

    def test_arw_hook_runs_validate(self):
        cp = subprocess.run(
            ["bash", str(SCRIPTS / "arw_hook.sh"), "validate_run_state.py"],
            capture_output=True, text=True, cwd="/tmp",
        )
        self.assertEqual(cp.returncode, 0, cp.stderr + cp.stdout)


class TestInitRun(unittest.TestCase):
    def test_build_run_validates(self):
        sys.path.insert(0, str(SCRIPTS))
        import init_run  # noqa: WPS433
        with tempfile.TemporaryDirectory() as td:
            rd = Path(td) / "2099-01-01_unit"
            init_run.build_run(rd, "2099-01-01_unit", "unit", "directed", "no target")
            rc = validate_run_state.main(["--run-dir", str(rd)])
            self.assertEqual(rc, 0)
            state = json.loads((rd / "state" / "run_state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["literature_mode"], "directed")
            self.assertEqual(state["current_state"], "S1_RESEARCH_SEED_PLAN")
            self.assertTrue((rd / "50_code" / "protected_files.yaml").is_file())
            self.assertTrue((rd / "00_seed" / "argument_chain.md").is_file())
            self.assertTrue((rd / "70_analysis" / "argument_map.md").is_file())
            import validate_argument_chain
            self.assertEqual(validate_argument_chain.main(["--run-dir", str(rd)]), 0)


class TestArgumentChain(unittest.TestCase):
    def test_missing_file_ok(self):
        import validate_argument_chain
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(validate_argument_chain.main(["--run-dir", td]), 0)

    def test_bad_traceability_hard_fail(self):
        import validate_argument_chain
        with tempfile.TemporaryDirectory() as td:
            rd = Path(td)
            (rd / "00_seed").mkdir()
            (rd / "00_seed" / "argument_chain.md").write_text(
                "---\ntraceability: T9\n---\n## 3. Eight-ring status\n"
                "| 1 Why | x |\n| 2 Prior work | x |\n| 3 Gap | x |\n| 4 Bottleneck | x |\n"
                "| 5 Method | x |\n| 6 Experiments | x |\n| 7 Conclusions | x |\n| 8 Insight | x |\n",
                encoding="utf-8",
            )
            self.assertEqual(validate_argument_chain.main(["--run-dir", str(rd)]), 1)

    def test_orphan_claim_id_hard_fail(self):
        import validate_argument_chain
        with tempfile.TemporaryDirectory() as td:
            rd = Path(td)
            (rd / "00_seed").mkdir()
            (rd / "40_proposal").mkdir(parents=True)
            tmpl = (REPO / "templates" / "argument_chain.md").read_text(encoding="utf-8")
            tmpl = tmpl.replace(
                "|----------|-------|-----------------------------------|-------------|----------|-------|-------|\n",
                "|----------|-------|-----------------------------------|-------------|----------|-------|-------|\n"
                "| C9999 | ghost | none | literature | weak | none | D |\n",
            )
            (rd / "00_seed" / "argument_chain.md").write_text(tmpl, encoding="utf-8")
            (rd / "40_proposal" / "claim_ledger.jsonl").write_text(
                json.dumps({"claim_id": "C0001", "claim": "x"}) + "\n", encoding="utf-8")
            self.assertEqual(validate_argument_chain.main(["--run-dir", str(rd)]), 1)

    def test_constitution_has_no_private_suite_dump(self):
        text = (REPO / "argument_chain_constitution.md").read_text(encoding="utf-8")
        self.assertNotIn("XJTU3DSAIL", text)
        self.assertNotIn("3dsail-research-workflow-suite", text)
        self.assertIn("I1", text)

    def test_literature_search_cli(self):
        cp = subprocess.run(
            [sys.executable, str(SCRIPTS / "literature_search.py"), "-h"],
            capture_output=True, text=True, cwd=str(REPO),
        )
        self.assertEqual(cp.returncode, 0, cp.stderr)
        blob = cp.stdout + cp.stderr
        self.assertIn("search", blob)
        self.assertNotIn("3dsail", blob.lower())


class TestLiveRunUntouchedContract(unittest.TestCase):
    """Existing active run must still validate (literature_mode optional)."""

    def test_active_run_validate_run_state(self):
        pointer = REPO / "research_runs" / ".active_run"
        if not pointer.is_file():
            self.skipTest("no active run")
        cp = subprocess.run(
            [sys.executable, str(SCRIPTS / "validate_run_state.py")],
            capture_output=True, text=True, cwd=str(REPO),
        )
        self.assertEqual(cp.returncode, 0, cp.stderr + cp.stdout)
        self.assertIn("OK", cp.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
