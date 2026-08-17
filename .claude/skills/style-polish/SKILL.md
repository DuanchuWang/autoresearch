---
name: style-polish
description: >-
  Use after S16 paper draft when the argument chain has no open 断裂, to remove
  defensive padding and clustered AI-tells. Never polish a broken argument.
  Does not change claims, metrics, or citations.
---

# Style polish (文风打磨)

## 何时使用
- `80_paper/paper.md` exists and `argument-diagnosis` has no open 自证 / 链序 break.
- Operator asks to 去叠甲 / 去 AI 腔 after logic is fixed.
- Not for inventing stronger claims (constitution T5). Not for S4 gap work.

## 输入
- `RUN_DIR/80_paper/*.md`
- `RUN_DIR/70_analysis/argument_map.md` (claims must stay)
- `templates/writing/05_style_guide.md`

## 输出
- In-place edits to the paper files (keep meaning).
- `RUN_DIR/80_paper/style_scan.md` — hits + what changed / what was kept.

## 禁止事项
- 禁止在论证断裂未修时润色。
- 禁止删 however / 然而 / 因此 等逻辑连接，除非同一段堆叠修正前文 ≥3 次。
- 禁止改数字、paper_id、EID、claim 强度。
- 禁止把 “may indicate” 升级成 “proves”.

## 步骤
1. Confirm diagnosis file has no open 断裂. If broken → stop, point to diagnosis.
2. Scan defensive patterns: 否定定义自己; not A but B; preamble padding;
   X rather than Y; 只/仅/merely; hedge piles; caveats in the lead sentence;
   not only… but also….
3. Scan AI-tell *clusters* (`——`, label-colons, vital/crucial/delve/tapestry,
   hanging -ing, synonym carousel). Single hits are not guilt.
4. Test: if deleted, does the argument break? If not, delete.
5. Safety: keep clinical/legal hedges; keep quotes and titles.
6. Write `style_scan.md`. Re-run claim/number grep against ledger + leaderboard.

## 质量 gate
No new overclaim words without a tested boundary. Metrics still match
`metrics.json` / `leaderboard.tsv`.
