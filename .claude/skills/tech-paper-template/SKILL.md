---
name: tech-paper-template
description: Use to draft the paper/proposal skeleton (S16_PAPER_DRAFT or pre-S6 proposal lock) from an accepted idea plus the claim ledger — produces problem/gap/method/3 contributions/experiment matrix/risk/fallback sections with zero unsupported claims.
---

# Tech Paper Template (论文骨架生成)

## 何时使用
- `S16_PAPER_DRAFT`：基于已 lock 的 proposal 与实验证据起草论文骨架。
- 也可在 S6 前，用本 skill 生成 `40_proposal/proposal.md` 供 lock 审阅。
- 不要用于 S5 之前的 idea（缺证据，会产出 unsupported claim）；不要用于 benchmark 论文（用 benchmark-paper-template）。

## 输入
- `RUN_DIR/40_proposal/proposal_locked.json`（含 accepted idea_id、locked contributions）。
- `RUN_DIR/40_proposal/claim_ledger.jsonl`（仅采纳 status∈{supported,planned} 且 evidence_paths 非空的 claim）。
- `RUN_DIR/60_experiments/experiment_ledger.md`（已完成的 E000X，作为实验矩阵输入）。
- `RUN_DIR/30_gap/gap_report.md`（problem/gap 段落依据）。

## 输出
- `RUN_DIR/80_paper/skeleton.md`（或 `40_proposal/proposal.md`，二选一，由调用方指定）。
- `RUN_DIR/80_paper/claim_to_section_map.json`（claim_id → section anchor，便于审稿反查）。
- 向 `claim_ledger.jsonl` 追加 `status=removed` 行，标记无法支撑而删除的 claim（不删原行）。

## 禁止事项
- 禁止写入 `claim_ledger` 中不存在或 status=unsupported/overstated 的 claim。
- 禁止把 planned claim 写成已验证结论（必须用“我们将/拟”措辞）。
- 禁止超过 3 个 contribution（强制聚焦）。
- 禁止编造实验结果；未跑的实验在 matrix 中标 `pending`。
- 禁止覆盖已存在 skeleton（改后缀 `_v2`）。

## 必须写入的产物路径
- `RUN_DIR/80_paper/skeleton.md` （主产物）
- `RUN_DIR/80_paper/claim_to_section_map.json` （claim 审计追溯）
- `RUN_DIR/40_proposal/claim_ledger.jsonl` （追加 removed 行）
- `RUN_DIR/memory/decisions.md` （记录“哪些 claim 被剔除及原因”）

## 步骤
1. 加载 proposal_locked + claim_ledger；过滤 `status∈{supported,planned}` 的 claim，记为 `usable_claims`。
2. 写 `## 1 Problem & Motivation`：引用 gap_report 第一段，每句断言挂一个 claim_id（用 `[C<paper_id>_<seq>]` 内联标）。
3. 写 `## 2 Gap`：三段式（已知方案 / 共性局限 / 未被解决的问题），全部从 gap_report 抄录并挂 claim_id；无 claim 支撑的句子删除并记入 `removed`。
4. 写 `## 3 Method`：对每个 technical_contribution 一小节，描述输入→模块→输出；planned contribution 用“拟提出”。
5. 写 `## 4 Contributions`：严格 ≤3 条编号列表，每条映射到 ≥1 个 supported claim。
6. 写 `## 5 Experiment Matrix`：表格列 `实验ID | 目标claim | dataset | baseline | metric | 状态`。状态从 experiment_ledger 读（已跑的填结果，未跑填 pending）。
7. 写 `## 6 Risks & Fallback`：每条 risk 对应 idea 的 `expected_risks[]`，每条 fallback 必须可执行（指明 fallback 实验 ID）。
8. 自检：遍历 skeleton 每个内联 claim 标记，核对其在 `usable_claims` 中存在；不在的，要么删除该句、要么把对应 claim_ledger 行追加为 `removed`（带原因）。
9. 生成 claim_to_section_map.json：`{claim_id: [section_anchor, ...]}`，便于 S17 内审抽查。

## 质量 gate
推进 `S16→S17`（paper_gate 前置）须：skeleton 6 节齐全；每个 contribution 挂 ≥1 supported claim；experiment matrix 中所有 supported claim 均有对应实验且状态非 pending；claim_to_section_map 无悬空引用；claim_ledger 中无 status=overstated 残留（已转 removed 或 weakened）。
