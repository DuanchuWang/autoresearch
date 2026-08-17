# Autoresearch

Claude Code 上的**自主科研操作系统**：文献 → gap → 方案锁定 → 实现 → 实验审计 → 论文包。
本仓库只含工作流（agents / hooks / 账本 / gate），**不含**具体算法代码或实验权重。

两层：

| 层 | 文件 | 管什么 |
|---|---|---|
| OS | `CLAUDE.md`、S0–S18、`research_runs/`、hooks | 怎么执行、实验账本、gate |
| 论证 | `argument_chain_constitution.md` | 8 环、T1–T7、防自证、切口 I1–I5 |

已有初稿/实验记录用 `LAUNCH.md` 的 `run_mode: rehab`，先跑 `draft-rehab`，**不会**因此把 `experiment_gate` 标通过。

Originally extracted from a mmdetection3d checkout; argument-chain rules distilled in-repo (not a third-party suite dump). Local `*.zip` files are gitignored.

## 放到任何机器

```bash
git clone <this-repo> autoresearch
cd autoresearch
python3 scripts/init_run.py --topic my_idea --target-repo /path/to/your/code
```

然后用 Claude Code **打开本仓库根目录**。对 CC 说「按 LAUNCH.md 启动」。

| 角色 | 在哪 |
|---|---|
| 科研 OS（本仓库） | `CLAUDE.md` `.claude/` `scripts/` `research_runs/` |
| 论证链 | `research_runs/<RUN>/00_seed/argument_chain.md` |
| 科学代码 | `research_runs/<RUN>/50_code/target_repo/`（symlink 或 clone） |
| 实验账本 | `research_runs/<RUN>/60_experiments/` |
| 论文包 | `research_runs/<RUN>/90_package/` |

Hooks 全部走 `bash scripts/arw_hook.sh …`，用脚本自己的位置定位仓库根，**没有** `/root/code/...` 绝对路径。

## 目录

```
CLAUDE.md                              控制器指令（怎么执行）
argument_chain_constitution.md         论证层宪法（8 环 / 防自证 / I1–I5）
LAUNCH.md                              操作者启动表单（含 rehab）
autonomous_research_workflow_prompt.md 规范（规则是什么）
arw.yaml                               可选：smoke_import 等
.claude/agents/                        17 个 subagent
.claude/skills/                        含 draft-rehab / find-incision / argument-diagnosis / style-polish
.claude/settings.json                  hooks（相对路径）
scripts/                               校验 / literature_search.py / init_run.py
templates/                             论证链骨架、写作 contracts
research_runs/<RUN_ID>/                一次研究的全部事实源
```

## 常用命令

```bash
python3 scripts/init_run.py --topic demo --literature-mode directed
python3 scripts/literature_search.py check
python3 scripts/generate_next_actions.py
python3 scripts/validate_run_state.py
python3 scripts/validate_argument_chain.py
python3 scripts/tests/test_arw_opt.py
```

环境变量：

- `ARW_RUN_DIR` — 覆盖当前 run 目录
- `ARW_TARGET_REPO` — 覆盖科学代码路径
- `ARW_SMOKE_IMPORT` — smoke 时 `import` 的包名（如 `mmdet3d`）
- `ARW_SMOKE_SCOPE` — PostToolUse 对哪些前缀跑 smoke（逗号分隔）
- `ARW_FIND_*` — `literature_search.py` 源/超时/缓存/Semantic Scholar key

## 明确不包含

- 具体论文 run（例如 PointPillars 实验日志、checkpoint、PDF）
- 第三方写作套件的原文树 / 组织安装脚本 / 本地 zip
- 目标仓库的源码

## 测试

`python3 scripts/tests/test_arw_opt.py` 应全部通过，且 agents / settings 中不得出现宿主机绝对路径。
