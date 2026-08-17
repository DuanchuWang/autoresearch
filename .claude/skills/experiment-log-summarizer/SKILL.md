---
name: experiment-log-summarizer
description: Use to distill a finished experiment's run.log + metrics.json into a compact result summary (primary metric, baseline delta, anomalies) for S12_RESULT_AUDIT and for paper tables — invoke after an E000X directory has both run.log and metrics.json.
---

# Experiment Log Summarizer (实验结果摘要)

## 何时使用
- `S12_RESULT_AUDIT`：每个 `E000X_<slug>/` 跑完后（run.log + metrics.json 齐全）。
- `S13_KEEP_AND_EXPAND_ABLATION` / `S15_FULL_ABLATION`：汇总多 seed 结果。
- 不要用于 status≠finished 的实验（先由 failure-forensics 处理）。

## 输入
- 一个 `experiment_id`（如 `E0003`），从 `RUN_DIR/60_experiments/experiment_ledger.md` 定位其目录 `E000X_<slug>/`。
- `RUN_DIR/60_experiments/E000X_<slug>/run.log`
- `RUN_DIR/60_experiments/E000X_<slug>/metrics.json`
- `RUN_DIR/60_experiments/E000X_<slug>/config.yaml`（用于核对指标定义）
- baseline 的 metrics（从同一 ledger 的 baseline 实验目录或 benchmarks.jsonl 取）。

## 输出
- `RUN_DIR/60_experiments/E000X_<slug>/result_summary.md`：定长结构（见步骤 3）。
- `RUN_DIR/60_experiments/E000X_<slug>/result_summary.json`：机读版（primary_metric, baseline_delta, anomalies[], verdict_hint）。
- 把 verdict_hint 追加到 experiment_ledger.md 该 `## E000X` 块的 `Judgement` 行候选值。
- 异常项 → `memory/open_questions.md`。

## 禁止事项
- 禁止从 run.log 抄数字（必须以 metrics.json 为准；log 仅用于异常诊断）。
- 禁止把 NaN/Inf 当有效结果；遇则标 anomaly。
- 禁止改写 experiment_ledger.md 的已有字段（仅追加 `Judgement` 候选 + 注释行）。
- 禁止覆盖 result_summary（重跑追加 `_v2`）。

## 必须写入的产物路径
- `RUN_DIR/60_experiments/E000X_<slug>/result_summary.md`
- `RUN_DIR/60_experiments/E000X_<slug>/result_summary.json`
- `RUN_DIR/60_experiments/experiment_ledger.md` （仅追加注释）
- `RUN_DIR/memory/open_questions.md` （异常追加）

## 步骤
1. 校验 E000X 目录有 `run.log` 与 `metrics.json`；缺一 → `record_blocker('exp_missing_artifacts_<EID>')` 软失败退出。
2. 从 config.yaml 读 `primary_metric` 字段（如 `pts_bbox_NuScenes/mAP`）；未声明则回退 research_seed 的默认主指标，并在 summary 标注。
3. 写 result_summary.md（固定六段）：
   - `## Primary metric`：值 + 单位 + epoch。
   - `## Baseline delta`：Δ vs baseline（绝对 + 相对%），baseline 来源标注。
   - `## Secondary metrics`：表格，每行 1 指标 + baseline + delta。
   - `## Training dynamics`：从 run.log 抽 loss 曲线关键点（首/末/最低 loss + 出现 epoch）；显存峰值。
   - `## Anomalies`：列出 NaN/Inf/early-stop-未触发/val 反弹 等，每条挂 log 行号。
   - `## Verdict hint`：`success|failure|inconclusive|buggy|timeout|sentinel`（仅建议，最终由 result-auditor 定）。
4. 同步写 result_summary.json：`{experiment_id, primary_metric, primary_value, baseline_value, baseline_delta_abs, baseline_delta_pct, anomalies:[{type,log_line}], verdict_hint, generated_at}`。
5. 若 `baseline_delta_pct < -1%`（劣化）或 anomalies 非空 → 追加 open_questions 一行，并在 ledger `## E000X` 块追加注释 `> summarizer: <一句话>`。
6. 把 verdict_hint 作为 `Judgement` 候选值追加到 ledger 该块（不删原值，用 `/` 分隔多重候选）。

## 质量 gate
通过 `experiment_gate`（S12 推进条件）须：本 run 所有 finished 的 E000X 均有 result_summary.md+json；每条 baseline_delta 计算可追溯（baseline 来源非空）；anomalies 为空或全部已有 open_question 记录。否则保留 S12，把缺口写进 task_queue。
