# Paper Card Schema (深度精读卡片)

> Status: **TEMPLATE** — the canonical deep-reading card schema (§7). One card per paper in
> `20_notes/cards/` (file name = `<paper_id>.md`). Front matter is mirrored in
> `10_literature/manifest.jsonl`.

A paper card is NOT a summary. It is a **deep, structured, critical** reading note whose purpose
is to feed gap synthesis (S4) and claim verification (S6/S12). Every field below is required; if a
field is genuinely absent for a paper, write `N/A — <reason>` rather than leaving it blank.

---

## 0. 元信息 (Metadata)

- **paper_id:** (matches `10_literature/manifest.jsonl`)
- **title:**
- **authors:**
- **venue / year:**
- **arxiv_id / doi / url:**
- **code_url / code_commit:**
- **category:** core | adjacent_a | adjacent_b | adjacent_c
- **read_at:** (UTC timestamp)
- **reader:** (agent / human)
- **reading_time_min:**
- **pdf_path:** (local path)
- **note_path:** (this file)

## 1. 一句话概括 (One-sentence summary)

(1-2 句话, 面向同行, 必须包含: 任务 + 方法核心 + 主要结果数字 + 数据集。禁止空话如 "提出了一种新方法"。)

## 2. 研究问题与动机 (Problem & motivation)

- **任务定义 (Task):**
- **输入/输出 (I/O):**
- **为什么现在做 (Why now):**
- **现实/工程动机 (Practical driver):**
- **未被解决的子问题 (The exact unsolved sub-problem this paper attacks):**

## 3. 相关工作谱系 (Related work lineage)

- **直接前驱 (Direct predecessors):** (论文 + 它们各自做到了哪一步)
- **同时代竞争 (Concurrent competitors):**
- **本工作位于谱系的哪个位置 (Where it sits):**
- **它替代/超越的具体方法 (What it supersedes, concretely):**

## 4. 核心方法 (Core method)

- **整体框架 (Overall pipeline):**
- **关键模块 1 (Key module 1):** 输入 → 处理 → 输出, 用一段话能复现的程度。
- **关键模块 2 (Key module 2):**
- **关键模块 3 (Key module 3):**
- **训练信号 / 损失 (Training signal / loss):**
- **推理路径 (Inference path):**
- **工程实现的关键 trick (Implementation tricks that matter):**
- **超参表关键项 (Hyper-parameters that matter):**

## 5. 实验设置 (Experimental setup)

- **数据集 (Datasets) + 划分 (splits):**
- **评估指标 (Metrics) + 计算约定 (convention):**
- **基线 (Baselines):** (名称 + 是否自复现 + 报告数字来源)
- **种子 / 重复 (Seeds / repeats):**
- **硬件 / 运行时 (Hardware / runtime):**
- **消融配置 (Ablation grid):**

## 6. 结果判读 (Results interpretation)

- **主表关键数字 (Headline numbers):**
- **相对最强基线的提升幅度 (Delta vs strongest baseline):**
- **消融结论 (What each ablation shows):**
- **失败/负面结果 (Negative results the paper admits):**
- **作者未强调但可疑的数字 (Suspicious numbers the authors bury):**
- **统计显著性 (Statistical significance reported?):** yes/no/partial

## 7. 可迁移结论与局限 (Transferable claims & limitations) — *most important for gap synthesis*

- **可迁移的强结论 (Transferable strong claims):** (每条配 evidence: 论文表/图编号)
- **方法层面的局限 (Method-level limitations):**
- **实验层面的局限 (Experimental limitations):** 数据集/规模/指标/种子
- **作者承认的局限 (Limitations the authors admit):**
- **作者未承认但存在的局限 (Limitations the authors hide):**
- **可证伪点 (Falsifiable points):** (哪些结论换个设定就很可能不成立)

## 8. 对本项目的关系 (Relation to our project)

- **可复用的代码 / 数据 (Reusable code/data):** (路径 / commit / license)
- **可复用的方法组件 (Reusable method components):**
- **可作为基线 (As a baseline?):** yes/no, 在哪个数据集上, 复现成本
- **可被本项目反驳的结论 (Claims we could rebut):**
- **可被本项目继承的结论 (Claims we can inherit):**
- **与本项目的冲突点 (Conflicts with our direction):**

## 9. 引用与证据 (Citations & evidence)

- **关键引用 (Key citations) + 引用它的工作 (Works citing it):**
- **被引用数 / 影响力 (Citation count / impact):**
- **本卡片结论的可追溯证据 (Traceable evidence for every claim in this card):** 表/图/页码

## 10. 阅读元评估 (Reading self-audit)

- **理解置信度 (Comprehension confidence):** high / medium / low
- **需要二次确认的点 (Points needing double-check):**
- **待与作者/代码核对的疑问 (Open questions for code/author check):**
- **建议下一步精读的论文 (Suggested next papers):**
- **claims_verified:** (bool — 是否已对照 manifest.jsonl 的 claims_verified 字段)

---

## 卡片质量 gate (Card quality gate)

一张卡片**只有满足以下全部条件**才算完成 (manifest.jsonl `status` 才能从 `read` 升级到 `audited`):

1. §1 一句话概括包含具体数字与数据集;
2. §4 三个关键模块每个都能让另一位读者复现;
3. §7 至少给出 2 条可迁移强结论 + 2 条作者未承认的局限;
4. §8 明确回答 "能否作为基线" 与复现成本;
5. §9 每条结论都能定位到论文表/图/页码;
6. §10 理解置信度非 low (若 low, 必须留待二次精读)。
