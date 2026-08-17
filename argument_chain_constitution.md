# Argument-chain constitution

This file is the argument-layer source of truth for this repo. The OS layer
(`CLAUDE.md`, S0–S18, `research_runs/`) says *how work is executed*. This file
says *what a defensible scientific argument is*. When they disagree on argument
standards, this file wins. When they disagree on execution, `CLAUDE.md` wins.

Durable home of the chain for a run: `RUN_DIR/00_seed/argument_chain.md`.
Claims still live in `RUN_DIR/40_proposal/claim_ledger.jsonl` (one JSON object
per line). The evidence table in the argument chain must use the same `claim_id`.

Do not name ARW states S0–S18 as “S1–S5” here. Incision quality standards are
**I1–I5**.

## 1. Eight rings (order is forced)

A piece of work must answer these in order. Missing a ring is a break, not a
style issue. Inverting the order is a break — especially using experimental
results to back-fill motivation or gap (HARKing / 自证).

1. **Why** — a concrete problem (not a field), and why it matters.
2. **What others did** — actual prior work and *their* stated limitations (not a straw man).
3. **Gap** — a hole confirmed by external literature. “Nobody has done X” is not a gap.
4. **Bottleneck** — a root cause. Problems solvable by more GPU or more data are symptoms.
5. **Method** — one core mechanism (not a pile of engineering tricks).
6. **Experiments** — test the mechanism, rule out alternatives, support claims.
7. **Conclusions** — bounded, data-backed, no overclaim.
8. **Insight** — falsifiable, transferable, not tied to one implementation.

## 2. Iron laws (T1–T7)

**T1 Chain order.** Rings 1→8. Never invert. Never let results mint the motivation.

**T2 External source.** Motivation, gap, and bottleneck come from outside: papers,
prior-work self-limitations, or secondary analysis of published data. Unlabelled
self-experiment analysis pretending to be an external source is 自证.

**T3 Verify vs discover.** Own results have two legal roles:

- **Verify** a hypothesis that existed *before* the experiment, from literature.
- **Discover** a phenomenon in the data — must be labelled “discovery”, needs
  independent corroboration / external support. A discovery cannot also be the
  pre-existing motivation.

**T4 Evidence map.** Every claim maps to a table, figure, or literature id.
No evidence → delete the claim or demote it to Discussion / Future Work.

**T5 Bounded conclusions.** Claim scope ≤ experimental coverage. High-risk words
(solved / proved / general / significant / robust) need an explicit tested
boundary.

**T6 Mechanism, not trick.** Each component answers: bottleneck needs X → this
module supplies X → standard alternatives fail here. “We used X and it helped”
is an engineering report.

**T7 Falsifiable insight.** An insight is a proposition a future paper could
overturn. If you cannot sketch an observation that would make it *wrong*, it
is not an insight.

## 3. Post-hoc reconstruction (R1–R7)

Most rehab launches arrive *after* experiments, with a draft or a log dump.
There is often no pre-experiment motivation contract. Reconstruction must:

- **R1** Motivation/gap from exactly one of: (a) real pre-experiment notes,
  (b) a real literature search (script-backed, tagged `[Verified]`/`[Unverified]`),
  or (c) an explicit “discovery” label (T3). Never invent a prediction from the
  draft’s own story.
- **R2** Never forge “what we predicted”. Prediction–result tables exist only
  at traceability T0/T1.
- **R3** Every run carries T0/T1/T2. Downstream review must degrade with the
  grade; never silently treat T2 as T0.
- **R4** Missing rings stay `[缺失]` and go on the 补料清单. Do not fake them.
- **R5** Facts first (operations + measurements + results). Interpretation is
  labelled as interpretation.
- **R6** Rehab does not launder a bad argument. Keep the grade and the break
  list on the output.
- **R7** 补料清单 lists what would upgrade T2→T1/T0 (proposal, lab notes,
  failed runs, raw logs).

## 4. Traceability grades

| Grade | Condition | Role |
|---|---|---|
| **T0** | Pre-experiment motivation contract / locked blueprint | Verify-type; prediction–result table allowed |
| **T1** | Partial pre-materials (proposal, early draft, lab notes) | Partial reconstruct; mark the rebuilt range |
| **T2** | Only post-hoc draft/report/logs | Default discovery-type; source-audit table instead of predictions |

Upgrade only when 补料清单 items actually appear on disk.

## 5. Evidence grades (A–D)

| Grade | Typical condition | Where it may appear |
|---|---|---|
| **A** | Full-text literature, ≥2 independent sources; or own experiment with repeats and alternatives ruled out | Core “first / mechanism” claims |
| **B** | Abstract-level literature or single-run experiment with alternatives checked | Ordinary body claims |
| **C** | Existence-level cite; discovery not yet corroborated | Discussion / Future Work only |
| **D** | No source | Not a claim: delete or fetch evidence |

Ring 7 (conclusions) requires ≥ B. “First / mechanism-level” wording requires A.
A discovery without external support is capped at C.

## 6. Incision standards (I1–I5)

These are quality floors for gap/idea work. They are **not** ARW states.

| Id | Floor | Fail if |
|---|---|---|
| **I1 Exhaustive literature** | Search saturates; collision (signature + alias windows) recorded | One-angle search then “no related work” |
| **I2 Coherence** | Claims tagged Fact / Inference / Hypothesis; method is paper-executable | “Obviously” on a critical step |
| **I3 Incisive novelty** | One core mechanism; removing it should collapse the method | ≥4 unrelated modules each claiming credit |
| **I4 Real motivation** | Observable failure / anomaly / quantified bottleneck | Publication gap only (“nobody did this”) |
| **I5 Mechanism-driven** | Each design choice: hypothesis → mapping → predicted behaviour → test | “Inspired by X / empirically found” |

Deterministic search steps use `python3 scripts/literature_search.py`
(`search` / `collision` / `gold` / `gate` / `stats` / `check`). LLM web tools
are fallback only: tag `[Tool Unavailable: literature_search]` and mark hits
`[Unverified]`. A “coverage complete” claim needs gold-set recall, an uncovered-
source list, and two saturated rounds — otherwise it is “partial coverage”.

## 7. Search and coverage

- Scripts do deterministic work (HTTP, merge, stats, gates). The model judges
  relevance and writes cards.
- Never pretend a search ran. If a source is down, log `[Source Unavailable]`.
- Coverage-complete statements without the three logs above are forbidden.

## 8. Mapping onto this OS

| Constitution object | File |
|---|---|
| 8-ring archive | `RUN_DIR/00_seed/argument_chain.md` |
| Claims | `RUN_DIR/40_proposal/claim_ledger.jsonl` |
| Rehab sources | `RUN_DIR/00_seed/rehab_source/` |
| Argument map (before prose) | `RUN_DIR/70_analysis/argument_map.md` |
| Section contracts | `RUN_DIR/80_paper/section_contracts.md` |
| Diagnosis report | `RUN_DIR/30_gap/argument_diagnosis.md` |
| Style scan | `RUN_DIR/80_paper/style_scan.md` |

`experiment_gate` and `baseline_gate` are still OS gates. Filling the argument
chain never marks those gates passed. Missing metrics stay missing.
