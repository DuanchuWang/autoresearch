#!/usr/bin/env python3
"""PostCompact hook — injects the resume directive into context (stdout).

After a /compact, Claude Code injects this hook's stdout into the conversation. We print a
concise, hard resume instruction so the controller re-reads its state files and continues
from next_actions[0] WITHOUT re-asking the operator. Fail-soft: if state can't be read we
still print the generic directive.
"""
from __future__ import annotations
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _arw_common import find_run_dir, load_json, STATE_REL  # noqa: E402


def main() -> int:
    rd = find_run_dir()
    state_line = ""
    if rd is not None:
        rs = load_json(rd / STATE_REL, "on_post_compact")
        if isinstance(rs, dict):
            state_line = (f"\nACTIVE RUN: {rs.get('run_id','?')}  |  "
                          f"current_state={rs.get('current_state','?')}  |  "
                          f"active_goal={rs.get('active_goal','?')}")
    rd_rel = str(rd.relative_to(rd.parents[1])) if rd else "<no active run>"
    msg = f"""[POST-COMPACT RESUME]{state_line}

你刚完成上下文压缩。聊天上下文已被裁剪——文件才是事实源。不要重新询问用户。
按顺序读取以下文件，然后从 next_actions[0] 继续执行：

1. research_runs/.../state/run_state.json          (run: {rd_rel})
2. research_runs/.../memory/compact_snapshot.md
3. research_runs/.../memory/next_actions.md         ← 从第一项继续
4. research_runs/.../memory/decisions.md
5. research_runs/.../state/task_queue.json
6. research_runs/.../60_experiments/experiment_ledger.md
7. research_runs/.../40_proposal/claim_ledger.jsonl
8. research_runs/.../state/blockers.jsonl
9. git status                                       (对比 memory/git_status_before_compact.txt)

恢复规则：先读 run_state 决定当前 gate；任何决策写 decisions.md；任何不确定写
open_questions.md；不在 S_EVAL_HARNESS_REVISION 时绝不改 eval harness（hook_guard 会拦）。
立即从 next_actions[0] 继续，不重新规划、不重新询问。
"""
    # hook protocol: stdout is reserved for JSON; human-readable resume prompt → stderr
    print(msg, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
