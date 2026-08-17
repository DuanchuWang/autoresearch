---
name: failure-forensics
description: Use to classify a failed/inconclusive experiment into one of 11 failure categories and produce a retry plan (S14_FAILURE_ANALYSIS_AND_RETRY) — invoke when an E000X has Judgement in {failure, inconclusive, buggy, timeout, sentinel}.
---

# Failure Forensics (失败实验分类与重试)

## 何时使用
- `S14_FAILURE_ANALYSIS_AND_RETRY`：experiment_ledger 中某 `## E000X` 的 Judgement ∈ {failure, inconclusive, buggy, timeout, sentinel}。
- 也可在 S12 发现有 sentinel/buggy 时提前调用。
- 不要用于 success 的实验（那是 ablation 的事）；不要在实验未跑完时调用。

## 输入
- 一个失败 `experiment_id`（如 `E0005`）。
- `RUN_DIR/60_experiments/E000X_<slug>/{run.log, metrics.json, config.yaml, command.sh, environment.txt, code_diff.patch}`。
- `RUN_DIR/60_experiments/E000X_<slug>/result_summary.md`（来自 experiment-log-summarizer；若无则先跑那个 skill）。
- baseline 的 result_summary（用于判断是否数据/配置级问题）。

## 输出
- `RUN_DIR/70_analysis/failure_taxonomy.md`：11 类总表（每次调用追加一个 `### E000X` 子节，不覆盖）。
- `RUN_DIR/70_analysis/E000X_retry_plan.md`：分类结论 + 根因假设 + 3 层修复（quick/medium/deep）+ 重试实验草案。
- 向 `state/task_queue.json` 追加重试任务（不自动开 S9）。

## 禁止事项
- 禁止只给“换个 seed 再试”作为唯一方案（必须先定位根因类别）。
- 禁止把 sentinel（占位/未真跑）当 buggy；sentinel 单独一类，处理是“真正跑一次”。
- 禁止覆盖 failure_taxonomy.md（追加子节）。
- 禁止删除原 E000X 目录（EID 永不覆盖；重试开新 E000Y）。

## 必须写入的产物路径
- `RUN_DIR/70_analysis/failure_taxonomy.md` （追加 `### E000X` 子节）
- `RUN_DIR/70_analysis/E000X_retry_plan.md` （主产物）
- `RUN_DIR/state/task_queue.json` （追加 retry 任务）
- `RUN_DIR/memory/decisions.md` （记录分类结论）

## 11 类失败分类（固定枚举）
F01_data_mismatch / F02_label_bug / F03_config_drift / F04_code_regression / F05_shape_format / F06_oom_or_hang / F07_nan_loss / F08_premature_converge / F09_metric_misread / F10_environment (cuda/cudnn/dep) / F11_sentinel_or_skipped。

## 步骤
1. 读 E000X 全部 artifact；缺 run.log → 分类直指 F11，跳到步骤 5。
2. 扫 run.log 关键词：`CUDA out of memory`→F06；`NaN`/`inf`→F07；`RuntimeError`/`AttributeError`/`KeyError`→F04/F05；`mismatch`/`shape`→F05；`No module named`/`version`→F10。
3. 比对 config.yaml 与 baseline config：字段级 diff → 若关键字段（lr/batch/loss_weight/data_path）不一致 → F03。
4. 比对 metrics.json 与 result_summary：若数值合理但 metric 字段名解读错 → F09；若 loss 早早平稳且远差于 baseline → F08。
5. 在 failure_taxonomy.md 追加 `### E000X` 子节：表格 `类别 | 证据(log行号/字段diff) | 置信(高/中/低)`。若多类并存，主类放第一行。
6. 写 E000X_retry_plan.md：
   - `## 分类`：主类 + 次类。
   - `## 根因假设`：≥1 条，每条挂证据。
   - `## Quick fix`（≤30 min）：如改 batch / patch shape / 改 metric 字段。
   - `## Medium fix`（≤1 天）：如对齐 config / 改 dataloader。
   - `## Deep fix`（>1 天）：如换模块 / 重写 loss；附“何时升级到 deep”判据。
   - `## 重试实验草案`：新 EID（从 run_state.latest_experiment_id 自增）、config delta、预期验证指标、判 success 的阈值。
7. 把“重试实验草案”作为一条任务写进 task_queue（status=pending, owner=orchestrator），不直接开 S9。
8. 在 memory/decisions.md 追加一行分类结论 + 时间戳。

## 质量 gate
推进 `S14→S15`（或回 S9）须：每个 failure/inconclusive 的 E000X 在 failure_taxonomy.md 都有子节且主类置信≥中；retry_plan 的三层修复至少 quick+medium 非空；新重试 EID 已进 task_queue。否则保留 S14，把缺口写进 task_queue。若同一根因连续 3 次重试仍失败 → 升级到 S_FAIL_CLOSED_REPORT（在 retry_plan 顶部标红）。
