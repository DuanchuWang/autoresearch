---
name: draft-rehab
description: >-
  Use when LAUNCH.md run_mode=rehab or the operator brings an existing draft,
  experiment report, or training log that must be reverse-engineered into an
  8-ring argument chain before S2 harvest. Anti-HARKing: never invent a
  pre-experiment motivation contract. Do not auto-pass experiment_gate.
---

# Draft rehab (初稿逆构)

## 何时使用
- `LAUNCH.md` `run_mode: rehab`.
- Operator drops a draft / 实验报告 / `run.log` and the run has no honest
  `00_seed/argument_chain.md` yet.
- Do **not** use for a greenfield S0→S2 start. Do **not** write `80_paper/paper.md`
  here (that is `paper-writer` after `70_analysis/argument_map.md` exists).

## 输入
- `argument_chain_constitution.md` (T1–T7, R1–R7, T0/T1/T2).
- `RUN_DIR/00_seed/intake.md` and `rehab_materials` paths.
- Files under `RUN_DIR/00_seed/rehab_source/` (copy materials here first).
- Optional: `40_proposal/claim_ledger.jsonl`, `60_experiments/`.

## 输出
- `RUN_DIR/00_seed/argument_chain.md` filled (traceability, source-audit, 8 rings, 补料清单).
- Append-only rows in `40_proposal/claim_ledger.jsonl` (`status=planned` unless a
  real `metrics.json` supports the number).
- `RUN_DIR/30_gap/argument_diagnosis.md` stub pointing at remaining breaks.
- Update `state/task_queue.json`; run `python3 scripts/generate_next_actions.py`.

## 禁止事项
- 禁止事后补造预测（R2）或把草稿自己的故事当外部 gap。
- 禁止把 `baseline_gate` / `experiment_gate` 标 passed。
- 禁止把缺失环写成 passed；标 `[缺失]` 并进补料清单。
- 禁止编造 paper_id / DOI / metric。

## 步骤
1. Copy operator paths into `00_seed/rehab_source/` (fail-soft missing files).
2. Triage: list what exists (draft / tables / logs / notes). Assign **T0 / T1 / T2**.
3. Source-audit every ring: literature / prior-notes / discovery / missing.
   Flag 自证 if motivation cites own figures with no external paper_id.
4. If literature is unverified, schedule `literature_search.py search` +
   `paper-harvester` (directed). Do not claim coverage complete.
5. Rebuild rings 5–8 from facts (operations, measurements, results). Interpretation
   labelled as interpretation.
6. Map claims ↔ table/fig/EID. Grade A–D. Append `claim_ledger.jsonl`.
7. Write 补料清单. Set `current_state` to the weakest honest ARW state
   (usually `S2_LITERATURE_COLLECTION`; `S8_BASELINE` only if target_repo + real
   experiment dirs exist).
8. `python3 scripts/validate_argument_chain.py --run-dir RUN_DIR`.

## 质量 gate
`argument_chain.md` has YAML `traceability` ∈ {T0,T1,T2}; 8 source-audit rows;
no invented predictions on T2; no gate skip; next_actions regenerated.
