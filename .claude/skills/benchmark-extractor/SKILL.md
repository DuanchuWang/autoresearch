---
name: benchmark-extractor
description: Use to mine dataset / baseline / metric / protocol from a paper PDF and its linked code repo, writing results into the manifest entry and the paper card's experiment-settings section — invoke during S2/S3 when a paper needs its benchmark context captured for later experiment planning.
---

# Benchmark Extractor (基准信息抽取)

## 何时使用
- `S2_LITERATURE_COLLECTION` 末尾或 `S3_PAPER_READING_CARDS` 中，对每篇 core/adjacent_a 论文抽取实验设置。
- S7（实验计划）前，汇总所有 baseline 时复用本 skill 输出。
- 不要用于纯理论论文（无实验设置 → 直接标 `pdf_failed` 软失败退出）。

## 输入
- 一个 `paper_id`（manifest 中已有条目）。
- 该论文 PDF：`RUN_DIR/10_literature/<category>/<paper_id>.pdf`。
- （可选）`code_url` / `code_path` / `code_commit`（用于交叉验证 config 文件）。
- `RUN_DIR/00_seed/research_seed.md`（本 run 关注的 dataset/metric 优先级）。

## 输出
- 更新 manifest 该行：`status=audited`，并在 `note` 字段写 `benchmarks_extracted=true`。
- 在对应精读卡 `RUN_DIR/20_notes/cards/PXXXX_<slug>.md` 的 `## 实验设置` 段补全字段。
- 追加 `RUN_DIR/40_proposal/benchmarks.jsonl`：一行一个 (dataset, baseline, metric, protocol) 组合，字段：`paper_id, dataset, split, metric_name, metric_value, baseline_name, protocol(seed/folds/hardware), source_loc(表号/页码/code_file:line), extracted_at`。

## 禁止事项
- 禁止把不同 dataset/split 的数字混进同一行（必须逐组合拆行）。
- 禁止省略 `source_loc`：PDF 来源写 `TableN,pM`；代码来源写 `path:line`。
- 禁止编造 metric_value；表格缺失则写 `null` 并记 open_question。
- 禁止覆盖 benchmarks.jsonl（追加）。

## 必须写入的产物路径
- `RUN_DIR/40_proposal/benchmarks.jsonl` （主产物，追加）
- `RUN_DIR/20_notes/cards/PXXXX_<slug>.md` （仅编辑 `## 实验设置` 段）
- `RUN_DIR/10_literature/manifest.jsonl` （回写本行 status/note）
- `RUN_DIR/memory/open_questions.md` （缺失项追加）

## 步骤
1. 读 manifest 行 + PDF；若 PDF 缺失 → `record_blocker` 软失败退出。
2. 定位实验章节：先扫“Experiments / Results / Ablation / Implementation Details”标题。
3. **Dataset**：列出每个用到的数据集 + split + 类别数 + 点云数（若 3D）；写 `source_loc`。
4. **Metric**：识别主指标（mAP/NDS/AP/mIoU 等）+ 阈值（IoU=0.25/0.5 等）；次指标单独行。
5. **Baseline**：每个对比方法一行，含其 metric_value；标注是否为论文复现还是原作引用。
6. **Protocol**：seed 数、train/val 划分、epoch、batch、硬件（GPU 型号 ×N）；缺则 `-`。
7. 若 `code_url` 存在且能 `Read` 到 config（如 `configs/xxx.py`），交叉验证 step 3-6 的数字；不一致时以 PDF 为准并在 `note` 写 `code_disagrees=true`。
8. 对每个 (dataset,baseline,metric) 组合追加一行 benchmarks.jsonl（`extracted_at=now_iso()`）。
9. 把精读卡 `## 实验设置` 段用 Markdown 表格重写，列与 benchmarks.jsonl 字段对齐。
10. 更新 manifest 行 `status=audited`。

## 质量 gate
通过 `S3→S4` 前置（属 literature_gate 一部分）须：core 类全部 status∈{read,audited}；benchmarks.jsonl 中每个 core paper 至少 1 行；每行 `source_loc` 非空；research_seed 列出的主指标在本 run 关注的 dataset 上至少被 5 篇 core 覆盖。否则保留 S3。
