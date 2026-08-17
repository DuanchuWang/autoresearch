---
name: idea-evaluator
description: Use to score an idea from idea_candidates.jsonl across three reviewer perspectives (S5_IDEA_EVALUATION) — novelty, feasibility, and adversarial reviewer2 — before proposal_lock; pass condition novelty>=75, feasibility>=70, reviewer2 fatal=0.
---

# Idea Evaluator (三视角评审与评分)

## 何时使用
- `S5_IDEA_EVALUATION`：从 `30_gap/idea_candidates.jsonl` 取出待评 idea。
- proposal_lock（S6）前，必须先用本 skill 给每个候选 idea 打分。
- 不要用于已 locked 的 proposal（那是 S17 内审）；不要在 gap 未形成前调用。

## 输入
- 一个 `idea_id`（如 `I0003`），从 `RUN_DIR/30_gap/idea_candidates.jsonl` 读取该行。
- `RUN_DIR/40_proposal/claim_ledger.jsonl`（用于核对 supporting/opposing 的真实证据）。
- `RUN_DIR/10_literature/manifest.jsonl`（反查 code_url / code_path 是否可复现，影响 feasibility）。
- `RUN_DIR/00_seed/research_seed.md`（topic 约束、可用算力上限 → 影响 feasibility）。

## 输出
- 三份评审报告（各一份 md）：
  - `RUN_DIR/40_proposal/novelty_reviews/<idea_id>.md`
  - `RUN_DIR/40_proposal/feasibility_reviews/<idea_id>.md`
  - `RUN_DIR/40_proposal/reviewer2_reviews/<idea_id>.md`
- 一份合并分数：`RUN_DIR/40_proposal/idea_scores.jsonl`（每 idea 一行：novelty/feasibility/reviewer2 分数 + fatal_issues[] + verdict）。
- 若 fatal>0 或分数不达标，向 `state/task_queue.json` 追加“修改 idea”任务；不直接删 idea。

## 禁止事项
- 禁止打分无依据：每个扣分项必须引用具体 claim_id 或 paper_id。
- 禁止把 reviewer2 写成“肯定 + 鼓励”；reviewer2 必须尽力挑致命伤（fail-catalyst 角色）。
- 禁止在分数未达 gate 时擅自把 idea 标 accepted（那是 S6 的工作）。
- 禁止覆盖已有 review（同名追加 `_v2`）。

## 必须写入的产物路径
- `RUN_DIR/40_proposal/novelty_reviews/<idea_id>.md`
- `RUN_DIR/40_proposal/feasibility_reviews/<idea_id>.md`
- `RUN_DIR/40_proposal/reviewer2_reviews/<idea_id>.md`
- `RUN_DIR/40_proposal/idea_scores.jsonl`（追加，不覆盖）
- `RUN_DIR/memory/decisions.md`（仅追加：记录 verdict 与理由）

## 步骤
1. 读 idea 行；若 schema 缺字段 → `record_blocker('idea_schema_incomplete_<idea_id>')` 软失败退出。
2. **Novelty 评审**（0-100）：从 supporting_papers 反查 manifest，判断 technical_contributions 是否被任一论文已实现；逐项打分维度 = `问题新度(30) + 方法新度(40) + 评估角度新度(30)`。每项扣分附 paper_id 引用。
3. **Feasibility 评审**（0-100）：维度 = `数据可得(25) + 基线可复现(25, 看 code_url/code_path) + 算力匹配(25, 对比 research_seed 的 gpu_slots) + 工程复杂度(25)`。低于阈值的维度写“补救建议”。
4. **Reviewer2 评审**（fatal 计数 + severity 列表）：强制列出 ≥5 条攻击点，每条标 `severity∈{fatal,major,minor}` + `claim_id`。fatal 定义：能直接让结论不成立的逻辑/实验漏洞。
5. 合并写 `idea_scores.jsonl`：`{idea_id, novelty, feasibility, reviewer2_fatal_count, verdict∈{pass,revise,reject}}`，时间戳 `now_iso()`。
6. verdict 规则：`novelty>=75 and feasibility>=70 and reviewer2_fatal_count==0 → pass`；否则 `revise`（fatal=0 但分数不够）或 `reject`（fatal>=1）。
7. 把 verdict 与核心理由追加到 `memory/decisions.md`，并在 task_queue 写下一步（pass→S6 准备 lock；revise→回 S4 改 idea；reject→标记 removed）。

## 质量 gate
推进 `S5→S6`（proposal_gate）须：至少 1 个 idea verdict=pass；所有 reject 的 idea 在 idea_candidates.jsonl 标 `status=removed`（追加新行，不删旧）；novelty_reviews/feasibility_reviews/reviewer2_reviews 三件齐备且每条扣分有 paper_id 引用。否则保留 S5。
