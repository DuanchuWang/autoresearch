#!/usr/bin/env python3
"""PreToolUse guard for the autonomous research workflow.

Reads the Claude Code PreToolUse hook payload from stdin and BLOCKS destructive or
contract-violating operations. Emits the structured denial JSON + writes the reason to
stderr + exits 2 (universal "block" signal). On allow: exits 0 silently.

Blocks:
  * Bash: `rm` targeting any protected research artifact (data/raw, 10_literature,
    20_notes, 40_proposal, 60_experiments, experiment_ledger.md, claim_ledger.jsonl,
    run_state.json, manifest.jsonl, protected_files.yaml, leaderboard.tsv).
  * Bash: `rm` with both -r and -f (rm -rf style), regardless of target.
  * Bash: `git reset --hard`, `git clean -fd`/`-df`/`-fdx`.
  * Write/Write_file/Edit/NotebookEdit to an eval-harness path UNLESS the active run's
    run_state.json has current_state == S_EVAL_HARNESS_REVISION.

Fail-soft: if the run cannot be resolved or run_state cannot be read, the eval-harness
guard logs a WARN and ALLOWS (so a broken state file can be repaired) — but the hard
destructive Bash patterns block unconditionally.

Debug: set ARW_HOOK_DEBUG=1 to log decisions to stderr.
"""
from __future__ import annotations
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _arw_common import (  # noqa: E402
    REPO_ROOT, find_run_dir, load_json, log, VALID_STATES, STATE_REL, PROTECTED_YAML_REL,
)

TAG = "hook_guard"
DEBUG = os.environ.get("ARW_HOOK_DEBUG") == "1"

# --- Bash destructive detection -------------------------------------------------
PROTECTED_ARTIFACT_RE = re.compile(
    r"(?:^|[/\s\"'])(?:"
    r"data/raw|10_literature|20_notes|40_proposal|60_experiments|"
    r"experiment_ledger\.md|claim_ledger\.jsonl|run_state\.json|"
    r"manifest\.jsonl|protected_files\.yaml|leaderboard\.tsv"
    r")(?:[/\s\"']|$)"
)
GIT_RESET_HARD_RE = re.compile(r"\bgit\s+reset\s+--(?:hard|keep)\b")
GIT_CLEAN_FD_RE = re.compile(r"\bgit\s+clean\s+-[A-Za-z]*[fd][A-Za-z]*[fd]")
RM_TOKEN_RE = re.compile(r"\brm\b")
FLAGS_RE = re.compile(r"-([A-Za-z]+)")


def bash_violation(cmd: str):
    """Return (rule_name, human_reason) if cmd is destructive, else None."""
    low = cmd.lower()
    if GIT_RESET_HARD_RE.search(low):
        return ("git reset --hard",
                "history rewrite that can erase failed experiments — forbidden by §10/§15.")
    if GIT_CLEAN_FD_RE.search(low):
        return ("git clean -fd",
                "removes untracked experiment outputs — forbidden by §10/§15.")
    if RM_TOKEN_RE.search(low):
        if PROTECTED_ARTIFACT_RE.search(low):
            return ("rm protected artifact",
                    "removing a protected research artifact (ledger/state/literature/"
                    "notes/experiments) is forbidden. Mark as failed/superseded instead.")
        # rm with BOTH -r and -f (any combo, any order) => rm -rf style
        combined = "".join(FLAGS_RE.findall(low))
        if "r" in combined and "f" in combined:
            return ("rm -rf",
                    "recursive forced delete is forbidden. Remove specific files only, "
                    "and never protected artifacts.")
    return None


# --- Eval-harness protection ----------------------------------------------------
# Built-in defaults; extended at runtime by the run's 50_code/protected_files.yaml.
DEFAULT_EVAL_GLOBS = [
    "eval/**", "**/eval/**",
    "official_metrics/**", "**/official_metrics/**",
    "**/evaluate*.py", "scripts/evaluate.py",
    "baseline_configs/**", "**/baseline_configs/**",
    "**/evaluation/**",
]


def _parse_protected_yaml(path: Path) -> list[str]:
    """Minimal YAML parse for the `protected:` list (no PyYAML dependency)."""
    globs = []
    if not path.is_file():
        return globs
    in_protected = False
    for raw in path.read_text().splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not line.startswith(" ") and stripped.endswith(":"):
            in_protected = stripped[:-1].lower() == "protected"
            continue
        if in_protected and stripped.startswith("- "):
            item = stripped[2:].strip().strip('"').strip("'")
            if item:
                globs.append(item)
    return globs


def _glob_to_regex(glob: str) -> str:
    """Convert a glob to an anchored regex. `**` matches across `/`, `*` within a segment."""
    i, out = 0, []
    g = glob.replace("\\", "/")
    while i < len(g):
        c = g[i]
        if c == "*":
            if i + 1 < len(g) and g[i + 1] == "*":
                out.append(".*")           # ** matches anything including /
                i += 2
            else:
                out.append("[^/]*")        # * within a path segment
        elif c == "?":
            out.append("[^/]")
        else:
            out.append(re.escape(c))
        i += 1
    return "^" + "".join(out) + "$"


def _matches_eval(path_str: str, globs: list[str]) -> bool:
    if not path_str:
        return False
    p = Path(path_str).expanduser().resolve()
    try:
        rel = p.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        rel = p.as_posix()
    for g in globs:
        try:
            if re.match(_glob_to_regex(g), rel):
                return True
        except re.error:
            continue
    return False


def eval_harness_violation(file_path: str | None):
    """Return (rule_name, human_reason) if a Write/Edit hits the eval harness out-of-state."""
    if not file_path:
        return None
    run_dir = find_run_dir()
    if run_dir is None:
        if DEBUG:
            log(TAG, "WARN", "no active run; eval-harness guard skipped (allow).")
        return None  # fail-open for state repair
    rs = load_json(run_dir / STATE_REL, TAG)
    if not isinstance(rs, dict):
        if DEBUG:
            log(TAG, "WARN", f"unreadable {STATE_REL}; eval-harness guard skipped (allow).")
        return None  # fail-open so the state can be fixed
    state = rs.get("current_state", "")
    if state == "S_EVAL_HARNESS_REVISION":
        return None  # explicitly authorized
    if state not in VALID_STATES and state != "":
        # Unknown state — be conservative but allow repair; just warn.
        if DEBUG:
            log(TAG, "WARN", f"unknown current_state='{state}'; guard skipped.")

    globs = list(DEFAULT_EVAL_GLOBS)
    globs += _parse_protected_yaml(run_dir / PROTECTED_YAML_REL)
    # Only treat eval-ish globs as harness (not e.g. 10_literature which is also listed).
    eval_globs = [g for g in globs if any(k in g.lower() for k in
                   ("eval", "metric", "baseline_config"))]
    if _matches_eval(file_path, eval_globs):
        return ("eval-harness edit",
                f"editing the eval harness is only allowed in S_EVAL_HARNESS_REVISION "
                f"(current_state={state}). To proceed: set current_state="
                f"S_EVAL_HARNESS_REVISION, get codex-review-agent + result-auditor review, "
                f"produce an old/new metric compatibility report, single commit, and log "
                f"the reason in memory/decisions.md.")
    return None


# --- Hook protocol --------------------------------------------------------------
def deny(rule: str, reason: str):
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": f"[{TAG}] BLOCKED ({rule}): {reason}",
        }
    }
    print(json.dumps(payload))
    print(f"[{TAG}][DENY] {rule}: {reason}", file=sys.stderr, flush=True)
    sys.exit(2)


def allow():
    if DEBUG:
        log(TAG, "INFO", "allowed.")
    sys.exit(0)


def main() -> int:
    raw = sys.stdin.read()
    try:
        evt = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as e:
        # Don't block on a malformed hook payload — log and allow.
        log(TAG, "WARN", f"could not parse hook payload: {e}; allowing.")
        sys.exit(0)
    tool = evt.get("tool_name", "")
    tin = evt.get("tool_input", {}) or {}

    if tool in ("Bash",):
        cmd = tin.get("command", "") or ""
        viol = bash_violation(cmd)
        if viol:
            deny(*viol)
        allow()
    elif tool in ("Write", "Write_file", "Edit", "WriteFile", "NotebookEdit", "MultiEdit"):
        fp = tin.get("file_path") or tin.get("path") or ""
        viol = eval_harness_violation(fp)
        if viol:
            deny(*viol)
        allow()
    else:
        # Only Bash + Write/Edit are guarded; everything else allowed.
        allow()
    return 0


if __name__ == "__main__":
    main()
