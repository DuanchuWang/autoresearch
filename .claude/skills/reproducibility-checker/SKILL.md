---
name: reproducibility-checker
description: Use to verify one-click reproducibility of an experiment or the whole run (code/script/env/seed/config/artifact) — invoke at S10_SMOKE_TEST, before S18 publication packaging, and on demand; produces a checklist with missing-item gaps that block the final_gate.
---

# Reproducibility Checker (一键复现审计)

## 何时使用
- `S10_CODE_REVIEW_AND_SMOKE_TEST`：单实验冒烟前。
- `S18_PUBLICATION_CANDIDATE_PACKAGE`：发布包封箱前。
- 任何时候 orchestrator 怀疑某 E000X 或 baseline 不可复现（如换机器重跑数值飘）。
- 不要用于未实现完的 idea（先过 S10 smoke 再用）。

## 输入
- 目标范围：单个 `experiment_id` 或 `--scope=run`（全 run）或 `--scope=baseline`。
- `RUN_DIR/60_experiments/E000X_<slug>/{config.yaml, command.sh, environment.txt, code_diff.patch, metrics.json}`
- `RUN_DIR/50_code/protected_files.yaml`（标明哪些文件不可改动）。
- `RUN_DIR/state/run_state.json`（取 best_branch / commit）。
- baseline 时：`RUN_DIR/10_literature/manifest.jsonl` 的 code_url/code_commit。

## 输出
- `RUN_DIR/70_analysis/reproducibility_checklist.md`：每次调用追加一个 `## <scope> @ <timestamp>` 节，含勾选清单 + 缺失项。
- `RUN_DIR/70_analysis/reproducibility_gaps.jsonl`：机读缺口（每行 `{scope, item, severity, fix_action, created_at}`）。
- 缺失项 → `state/blockers.jsonl`（severity=fatal 时）+ `memory/open_questions.md`。

## 禁止事项
- 禁止把“能跑”当“可复现”：必须数值在容差内（primary_metric Δ≤0.5% 绝对或 research_seed 指定容差）。
- 禁止跳过 environment.txt 检查（cuda/cudann/python 版本是复现核心）。
- 禁止覆盖 checklist（追加新节，旧节作为历史）。
- 禁止自行“修复”缺失项（只记录 + 写 task；修复是 S9 的工作）。

## 必须写入的产物路径
- `RUN_DIR/70_analysis/reproducibility_checklist.md` （追加 `## <scope> @ <ts>`）
- `RUN_DIR/70_analysis/reproducibility_gaps.jsonl` （追加）
- `RUN_DIR/state/blockers.jsonl` （仅 severity=fatal 时追加，用 `record_blocker`）
- `RUN_DIR/memory/open_questions.md` （非 fatal 缺口追加）

## 复现 checklist（固定 12 项）
1. `command.sh` 存在且单行可执行（无 manual step）。
2. `config.yaml` 与 run 时一致（git diff 为空或仅路径替换）。
3. `environment.txt` 含 cuda/cudnn/python/torch 版本 + 关键依赖 pinned。
4. `code_diff.patch` 可干净 `git apply` 到 base commit。
5. base commit（run_state.last_commit / best_branch）可 checkout。
6. `seed` 在 config 显式声明（非 None）。
7. dataset 路径可解析（或给出可下载脚本/MD5）。
8. 单卡冒烟（≤100 iter 或 1% 数据）能在新环境跑通且不 OOM。
9. primary_metric 在容差内复现（重跑 1 次，对比 metrics.json）。
10. 无 protected_files 被改动（diff protected_files.yaml 列出的文件 = 空）。
11. 随机性来源可控（deterministic flag / cudnn.deterministic）。
12. 日志与 metrics 保留且未被截断（行数≥预期）。

## 步骤
1. 解析 scope，定位 E000X 目录或全 run；缺目标 → `record_blocker('repro_no_target')` 软失败退出。
2. 逐项执行 12 项 checklist：每项做“证据采集”（命令输出/文件存在/diff），写进 checklist 的 `[x]/[ ]` + 证据片段。
3. 任一项 fail → 在 reproducibility_gaps.jsonl 追加一行（severity: 1/4/8/9/12=fatal；其余=major）。
4. fatal 缺口调用 `record_blocker(run_dir, 'repro_<item>_<scope>', category='reproducibility', impact, workaround)`。
5. 计算 scope 复现分数 = 通过项/12，写进 checklist 节末尾。
6. 全 run 模式额外做：随机抽 1 个 E000X 实跑冒烟（步骤 8），把实测 metric 写进 checklist。
7. baseline 模式额外做：核对 manifest 的 code_commit 能 checkout + README 命令能复现其声称的主指标（容差内）。

## 质量 gate
通过 `final_gate`（S18 推进条件）须：scope=run 的 checklist 12 项全 `[x]`；reproducibility_gaps.jsonl 中无 severity=fatal 残留（已修复或 accepted 并记 decision）；scope=run 复现分数 = 12/12；若 baseline_gate 未通过则 final_gate 也不得通过。任一 fatal 缺口存在 → 保留 S18 或回 S14。
