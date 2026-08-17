# LAUNCH.md — 自主科研工作流启动入口

> **每次开跑前**: 填好下方【启动表单】→ 保存 → 在**本仓库根目录**打开 Claude Code，发一句
> **「按 LAUNCH.md 启动」**。
>
> 本仓库是科研操作系统（文献 / gap / 实验账本 / 论文包）。科学代码仓库填在 `target_repo`，
> 不要把本仓库和算法代码混成一个 git 历史。

---

## 0. 前置

- cwd 必须是本仓库根（hooks 用 `scripts/arw_hook.sh` 定位，不依赖机器绝对路径）。
- 命令里不要出现 `rm -rf` / `git reset --hard` / `git clean -fd`（会被 hook_guard 拦截）。
- 恢复空白表单: `git checkout LAUNCH.md`。
- 也可以先 `python3 scripts/init_run.py --topic <slug> --target-repo <path-or-url>` 建 run。

---

## 1. 启动表单

> 控制器按字段名解析; 冒号后即值。除标 🔴 的两项外都可留空/`待定`/`默认`。

~~~yaml
literature_mode: directed  # directed=已有具体方向,只收 opposing set; exploratory=全量30篇
run_mode: new              # continue=最新 run | new=按 topic 新建 | rehab=已有初稿/实验记录逆构
topic:                     # new / rehab 需要,短英文 slug
research_direction:        # 🔴 必须（rehab 可从初稿抽,仍要一句话问题）
target_repo:               # 🔴 必须。本地绝对路径 / git URL[@commit] / 相对路径
rehab_materials:           # 仅 rehab。初稿/报告/log 的路径,逗号分隔; 或 无
dataset:                   # 名称 + 挂载路径 + split + license; 或 待定
compute:                   # 如 8xA100 单job24h; 或 默认
codex_network:             # 可用 / 不可用 / 不确定
venue:                     # 会场 + 截稿; 或 探索性
seeds:                     # 必读论文 / 已知基线 / 已知失败方向; 或 无
extra:                     # 其他约束
~~~

---

## 2. 发车姿势

| 姿势 | 怎么做 | 适合 |
|---|---|---|
| **A. 一次给全** | 填满表单 → 「按 LAUNCH.md 启动」 | S2→S18 |
| **B. 先给方向** | 只填 `research_direction` + `target_repo` | 文献/gap 先跑 |
| **C. CLI 建 run** | `python3 scripts/init_run.py --topic slug --target-repo PATH` | 脚本化/CI |
| **D. 初稿逆构** | `run_mode: rehab` + `rehab_materials` | 已有草稿/实验,先补 8 环再进 S2/S8 |

---

## 3. 进度看哪里

- `state/run_state.json` — `current_state`、gates、`literature_mode`
- `00_seed/argument_chain.md` — 8 环 / 可追溯性 T0–T2 / 来源审计
- `memory/next_actions.md` — 由 queue 生成的短清单
- `60_experiments/experiment_ledger.md` — 每个实验 + 判定
