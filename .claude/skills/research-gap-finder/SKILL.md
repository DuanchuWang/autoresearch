---
name: research-gap-finder
description: Use when synthesizing research gaps and idea candidates (S4_GAP_SYNTHESIS) — invoke only after literature_gate has passed and before proposal_lock, to produce gap_report.md plus idea_candidates.jsonl with full supporting/opposing paper linkage. Quotas follow run_state.literature_mode (exploratory: ≥30 cards; directed: ≥8 cards + opposing set).
---

# Research Gap Finder (差距综合与 idea 候选)

## 何时使用
- `literature_gate=passed` 后、进入 `S4_GAP_SYNTHESIS` 时。
- 当 claim_ledger 中出现矛盾 claim（同一问题有 supporting+opposing）需要提炼为 idea 时。
- 不要在 S2/S3 之前调用；不要用于单篇精读（那是 paper-deep-note）。

## 输入
- `RUN_DIR/20_notes/cards/*.md` （exploratory ≥30 张；directed ≥8 张）。
- `RUN_DIR/40_proposal/claim_ledger.jsonl` （全部 status=planned/supported 的 claim）。
- `RUN_DIR/10_literature/manifest.jsonl` （用于反查 paper category、code_url）。
- `RUN_DIR/00_seed/research_seed.md` （topic 与约束，避免 idea 跑题）。

## 输出
- `RUN_DIR/30_gap/gap_report.md`：分主题归纳的“已知方案 / 共性局限 / 未被解决的问题”三段式表格。
- `RUN_DIR/30_gap/idea_candidates.jsonl`：每行一个 idea，完整 schema（见规范 §claim_ledger 同级）。
- 向 `memory/open_questions.md` 追加仍存疑的判断。

## 禁止事项
- 禁止产出“无 opposing paper”的 idea（每个 idea 必须 ≥1 opposing，否则改为 limitation_claim 而非 idea）。
- 禁止编造 paper_id；所有 supporting/opposing 必须存在于 manifest。
- 禁止覆盖已有 idea_candidates.jsonl（追加；若 idea_id 冲突则改后缀 `_b`）。
- 禁止把“主观感受”当 gap；gap 必须有 ≥2 篇文献或 1 个可量化指标做支撑。

## 必须写入的产物路径
- `RUN_DIR/30_gap/gap_report.md` （主报告，覆写允许）
- `RUN_DIR/30_gap/idea_candidates.jsonl` （追加）
- `RUN_DIR/memory/open_questions.md` （仅追加）
- `RUN_DIR/state/task_queue.json` （可选：为每个 idea 创建一条 S5 评估任务）

## 步骤
1. 校验前置：读 `run_state.literature_mode`（缺省 exploratory）。exploratory：`load_jsonl(MANIFEST_REL)` 中 status=read 的 core≥15、adjacent 三类各≥5；directed：core≥8 且 adjacent_a（opposing）≥5。不满足则 `record_blocker('gap_insufficient_cards')` 软失败退出。
2. 聚类：扫所有 card 的 `## 局限与质疑` 与 claim_ledger 中 type=limitation_claim 条目，按“问题域”聚类（如“长距离检测 / 小目标 / 时序融合”）。每簇写入 gap_report 第一段“已知方案”。
3. 提共性局限：对每簇统计高频局限关键词，写成表格列 `局限 | 出现论文 | 量化证据`。
4. 找空白：对每条共性局限，反查是否有论文直接解决；若 manifest 中无 `method_claim` 覆盖该局限，记为“未被解决的问题”。
5. 生成 idea：对每个“未被解决的问题”，构造一条 idea_candidates.jsonl 行，字段：
   `idea_id=I0001..` / `title` / `gap`（引用上一步空白）/ `core_hypothesis`（可证伪陈述）/ `technical_contributions[]`（≥1）/ `supporting_papers[]`（≥1，来自 card）/ `opposing_papers[]`（≥1）/ `possible_datasets[]` / `possible_baselines[]` / `expected_risks[]`（≥1）/ `minimum_viable_experiment`（一句话可执行描述）。
6. 自检：每个 idea 必须 `len(supporting_papers)>=1 and len(opposing_papers)>=1 and len(expected_risks)>=1`，否则丢弃并记入 open_questions。
7. 把 idea 数与未覆盖 gap 数写进 gap_report 末尾“Summary”，并把 S5 评估任务追加到 task_queue。

## 质量 gate
推进 `S4→S5` 须：gap_report 三段齐全；idea_candidates.jsonl 行数 ≥3 且每行 schema 完整；每条 idea 的 supporting+opposing paper_id 全部能在 manifest 命中。否则保留 S4 并把缺口写进 task_queue。
