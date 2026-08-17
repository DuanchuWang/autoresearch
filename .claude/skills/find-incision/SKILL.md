---
name: find-incision
description: >-
  Use in S1–S5 (and rehab ring 1–4 re-anchor) to run deterministic multi-source
  literature search via scripts/literature_search.py, then judge incision quality
  against I1–I5. “Nobody has done X” is not a gap. Do not skip paper-harvester
  quotas; this skill feeds them.
---

# Find incision (找切口)

## 何时使用
- S1 seed plan / S2 harvest query design / S4 gap synthesis.
- Rehab step “literature re-anchor” when rings 1–4 are `[Unverified]`.
- Not a replacement for `paper-harvester` (that still writes `manifest.jsonl`).

## 输入
- `argument_chain_constitution.md` (I1–I5, search rules)
- `RUN_DIR/00_seed/search_queries.md` and `argument_chain.md`
- Gold set if the operator named must-cite papers

## 输出
- JSON under `RUN_DIR/10_literature/find/` (`lit_raw.json`, `collision.json`, …)
- Append search log to `10_literature/provenance_audit.md`
- Update rings 1–4 notes in `argument_chain.md` with `[Verified]`/`[Unverified]`

## 禁止事项
- 禁止用 WebSearch 代替 `literature_search.py` 的 search/collision/gold/gate/stats
  （脚本不可用时才降级，并打 `[Tool Unavailable: literature_search]`）。
- 禁止声称覆盖完整，除非有 gold 召回、uncovered_sources、两轮饱和。
- 禁止把 “没人做过” 写成 gap（I4）。

## 步骤
1. `python3 scripts/literature_search.py check` (connectivity; fail-soft).
2. `search --query "..." --out RUN_DIR/10_literature/find/lit_raw.json`
3. `collision --signature "core terms" --alias "synonyms / older names"`
4. Optional `gold --gold gold_set.txt lit_*.json`
5. `stats` then `gate` after the model partitioned relevance (write
   `relevance_partition.json` first).
6. Feed hits to `paper-harvester` to become manifest rows (no fabricated URLs).
7. Score the candidate idea against **I1–I5**. Fail I3 if ≥4 unrelated modules
   each claim credit. Fail I4 if motivation is only a publication gap.

## 质量 gate
Provenance log lists actual subcommands. Hits used as gap evidence are in
manifest or tagged `[Unverified]`. I1–I5 recorded in `30_gap/gap_report.md`.
