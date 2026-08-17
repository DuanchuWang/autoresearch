---
name: paper-deep-note
description: Use when a paper must be converted into a structured Chinese deep-reading card (S3_PAPER_READING_CARDS) — invoke after a manifest entry reaches status=downloaded, before any claim ledger entry cites that paper.
---

# Paper Deep Note (精读卡)

## 何时使用
- 状态机推进到 `S3_PAPER_READING_CARDS`，且 `10_literature/manifest.jsonl` 中存在 `status=downloaded` 但尚无 `note_path` 的条目时。
- 任何 subagent 需要引用某论文的 claim / metric / 实验设置前，必须先有对应精读卡。
- 不要用于仅做 metadata 收集（那是 S2 的工作）；本 skill 只做深度阅读与结构化抽取。

## 输入
- `RUN_DIR/10_literature/manifest.jsonl` 中某一条 `paper_id`（如 `P0007`）及其完整 JSON 行。
- 该条目指向的本地 PDF：`RUN_DIR/10_literature/<category>/<paper_id>.pdf`（缺失则记录 blocker，软失败退出）。
- `RUN_DIR/30_gap/idea_candidates.jsonl`（可选，用于聚焦“与本 run topic 相关”的问题）。

## 输出
- 精读卡：`RUN_DIR/20_notes/cards/PXXXX_<slug>.md`，`<slug>` 取自 title 前 4 个实词小写连字符。
- 同时回写 manifest：将该 paper 的 `status` 改为 `read`，写入 `note_path`、`updated_at`、`claims_verified=true/false`。
- 若发现可验证 claim，向 `RUN_DIR/40_proposal/claim_ledger.jsonl` 追加 0..N 条候选 claim（status=planned）。

## 禁止事项
- 禁止臆造数据：所有数字必须引用 PDF 页码 / 表号 / 图号；无法定位则留 `[?]` 并写入 `memory/open_questions.md`。
- 禁止输出英文卡（本 skill 强制中文）；英文术语保留原文括注。
- 禁止覆盖已存在的 card（同名时改后缀 `_v2`，并在 manifest note 标注）。
- 禁止改动 `manifest.jsonl` 中除该 paper_id 之外的任何行。

## 必须写入的产物路径
- `RUN_DIR/20_notes/cards/PXXXX_<slug>.md` （主产物）
- `RUN_DIR/10_literature/manifest.jsonl` （仅回写本条 status/note_path/updated_at）
- `RUN_DIR/40_proposal/claim_ledger.jsonl` （可选追加，不覆盖已有 claim_id）
- `RUN_DIR/memory/open_questions.md` （仅追加，记录无法核实的 claim）

## 步骤
1. 从 manifest 取目标条目；`load_jsonl(MANIFEST_REL)` 过滤 `paper_id`。若无 `pdf_path` 或文件不存在 → `record_blocker(run_dir, 'pdf_missing_<paper_id>', ...)` 并软失败退出 (EXIT_OK)。
2. 读取 PDF（用 Read 工具 `pages` 参数分批，≤20 页/次）；优先级：Abstract → Method → Experiments/Tables → Ablation → Appendix。
3. 用以下 schema 撰写中文精读卡（每节标题固定）：
   - `## 元信息` paper_id / title / 作者 / venue / year / arxiv_id / code_url / 本卡创建时间。
   - `## 一句话总结` ≤30 字，回答“这篇做了什么、解决什么问题”。
   - `## 问题与动机` 列出论文声称要解决的 gap（用论文原话引文 + 页码）。
   - `## 方法` 核心模块图示化描述（文字即可），标注输入输出与关键超参。
   - `## 实验设置` dataset / metric / baseline / protocol / seed / hardware（缺失项标 `-`）。
   - `## 主要结果` 主表数字逐项抄录（表号+页码），并标 baseline 与本方法 delta。
   - `## 消融` 每个消融的变量 / 控制量 / 结论。
   - `## 局限与质疑` ≥3 条，对应 reviewer2 视角；每条标 `[可验证]` 或 `[主观]`。
   - `## 可复用要素` 对本 run 有用的 dataset / config / code snippet / metric 定义。
   - `## 可验证 claim 清单` 编号列表，每条 ≤25 字，用于喂给 claim_ledger。
4. 对每条“可验证 claim”，调用 `append_jsonl(CLAIM_LEDGER_REL, {...})`：`claim_id=C<paper_id>_<seq>`、`type∈{method_claim,experimental_claim,limitation_claim}`、`supporting_papers=[paper_id]`、`status=planned`、`last_verified_at=now_iso()`。
5. 回写 manifest 行：构造新 JSON 行，`status='read'`、`note_path` 指向新建卡、`updated_at=now_iso()`；写入用临时文件 + 整体替换（保护其他行），失败则 `record_blocker`。
6. 把无法核实的项追加到 `memory/open_questions.md`（一行一条），并在 card 内对应位置留 `[?]`。

## 质量 gate
通过 `literature_gate`（S3→S4 推进条件）须满足：core 类全部有 note_path 且 status=read；总 card 数 ≥ core(15)+adjacent_a/b/c(5 each)=30；每卡“可验证 claim 清单”非空；manifest 中无 `pdf_failed` 残留。否则保留 S3，把缺口写进 `state/task_queue.json`。
