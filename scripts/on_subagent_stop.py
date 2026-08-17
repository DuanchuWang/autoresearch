#!/usr/bin/env python3
"""SubagentStop hook (audit + reminder, fail-soft).

When a subagent finishes, append a stop record to RUN_DIR/subagent_reports/_stops.log and
emit a stderr REMINDER that findings must be persisted to subagent_reports/<name>_<ts>.md
and task_queue.json updated — never chat-only. This hook cannot force the subagent (it has
already stopped); it enforces an audit trail and a nudge for the orchestrator.
"""
from __future__ import annotations
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _arw_common import find_run_dir, now_iso, log, append_md  # noqa: E402

TAG = "on_subagent_stop"


def main() -> int:
    try:
        raw = sys.stdin.read()
        evt = json.loads(raw) if raw.strip() else {}
    except Exception:
        evt = {}
    agent = (evt.get("agent_name") or evt.get("name")
             or (evt.get("agent") or {}).get("name") or "unknown")
    ts = now_iso()
    rd = find_run_dir()
    if rd is not None:
        stops = rd / "subagent_reports" / "_stops.log"
        try:
            stops.parent.mkdir(parents=True, exist_ok=True)
            with stops.open("a") as f:
                f.write(f"{ts}\t{agent}\tstop\n")
        except Exception as e:
            log(TAG, "WARN", f"could not write stops log: {e}")
    log(TAG, "REMIND", f"subagent '{agent}' stopped. Persist findings to "
                       f"subagent_reports/{agent}_{ts.replace(':','')}.md and update "
                       f"state/task_queue.json before relying on its output. No chat-only results.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
