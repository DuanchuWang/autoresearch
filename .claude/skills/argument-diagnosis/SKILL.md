---
name: argument-diagnosis
description: >-
  Use at S6/S12/S15/S17 or after draft-rehab to audit the 8-ring chain for
  HARKing (自证), inverted order, the four traps, and overclaim. Writes
  30_gap/argument_diagnosis.md. Does not mark paper_gate passed.
---

# Argument diagnosis (逻辑诊断)

## 何时使用
- After `draft-rehab`, before proposal lock, and at S17 internal review.
- When `reviewer2-agent` needs the 自证 / 链序 face.
- Not for language polish (`style-polish`) and not for writing prose (`paper-writer`).

## 输入
- `argument_chain_constitution.md`
- `RUN_DIR/00_seed/argument_chain.md`
- `RUN_DIR/40_proposal/claim_ledger.jsonl` + `proposal.md` if any
- `RUN_DIR/80_paper/` if a draft exists
- `RUN_DIR/10_literature/manifest.jsonl`

## 输出
- `RUN_DIR/30_gap/argument_diagnosis.md`

## 禁止事项
- 禁止把自洽但自证的叙事判 PASS。
- 禁止用实验结果当环 1–4 的证据，除非显式「发现」且有外部佐证。
- 禁止改 claim_ledger status 为 supported。

## 步骤
1. Read constitution, then argument_chain (T0/T1/T2). T2 ⇒ no prediction–result table.
2. **Chain order:** rings 1→8. Inversion = `[断裂: 链序]`.
3. **自证红旗** (any hit → `[Warning: 自证风险]`):
   - 动机段引用自己的图/表且无外部 paper_id
   - gap 细节只有自己数据才知道
   - 瓶颈形状与方法优势完美匹配且无外部 limitation
   - 找不到 opposing paper
   - T2 却写了冻结预测
4. **四大陷阱:** (1) 没人做过 ≠ 值得做 (2) 切口大而全 (3) 涨点 ≠ 机理 (4) 过声称.
5. Six questions (anchor, bottleneck, mechanism, evidence design, bounded conclusion, insight).
6. Counterfactual: if all metrics reversed, would the motivation paragraph survive?
   If not → 自证.
7. Write the report with overall: breaks, 自证 risk, weakest ring, honest next ARW state.

## 质量 gate
Report has 防自证 table + 四陷阱 table + 六问. Ring marked passed only if not broken.
