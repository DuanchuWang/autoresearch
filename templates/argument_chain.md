---
project: "{{TOPIC}}"
run_id: "{{RUN_ID}}"
status: active
current_ring: 1
traceability: T2
created: ""
updated: ""
---

# Argument chain

> Copy of `templates/argument_chain.md`. Fill in place. Claim ids must match
> `40_proposal/claim_ledger.jsonl`. See `argument_chain_constitution.md`.

## 0. Project

- Problem (one sentence):
- Non-goals:
- Venue target:
- Traceability: T0 / T1 / T2
- Weakest ring:

## 1. Motivation contract (T0 write-once; T1 partial + labelled; T2 none — do not invent)

- Why:
- Predictions (P1..Pn, frozen):
- Success / fail rule:
- Signed date:

### Contract revisions (append only)

| date | change | reason | old prediction ids |
|------|--------|--------|--------------------|

## 2. Source-audit table (default for T2; R1 carrier)

| ring | quote from draft | source type | status | action |
|------|------------------|-------------|--------|--------|
| 1 Why | | literature / prior-notes / discovery / missing | | |
| 2 Prior work | | | | |
| 3 Gap | | | | |
| 4 Bottleneck | | | | |
| 5 Method | | | | |
| 6 Experiments | | | | |
| 7 Conclusions | | | | |
| 8 Insight | | | | |

Source type ∈ {literature, prior-limitation, secondary-analysis, own-experiment-discovery, missing}.

## 3. Eight-ring status

| ring | status | artifact | updated | gate note |
|------|--------|----------|---------|-----------|
| 1 Why | not_started | | | |
| 2 Prior work | not_started | | | |
| 3 Gap | not_started | | | |
| 4 Bottleneck | not_started | | | |
| 5 Method | not_started | | | |
| 6 Experiments | not_started | | | |
| 7 Conclusions | not_started | | | |
| 8 Insight | not_started | | | |

status ∈ {not_started, in_progress, passed, broken, missing}.
A `broken` row must include a break note + repair direction. Do not mark passed
while broken.

## 4. Prediction–result table (T0/T1 only)

| id | contract prediction | actual | match? | alternatives checked | conclusion update |
|----|---------------------|--------|--------|----------------------|-------------------|

## 5. Evidence ledger (T4; claim_id = claim_ledger.jsonl)

| claim_id | claim | evidence (table/fig/paper_id/EID) | source type | strength | depth | grade |
|----------|-------|-----------------------------------|-------------|----------|-------|-------|

grade ∈ {A, B, C, D}. Ring-7 claims need ≥ B.

## 6. 补料清单 (R7)

| missing item | rings blocked | upgrade if filled | operator can provide? |
|--------------|---------------|-------------------|------------------------|

## 7. Mode footprint

| date | skill/agent | input | output | note |
|------|-------------|-------|--------|------|

## 8. Current block and next step

- Traceability:
- Weakest ring:
- Breaks / 自证 flags:
- Suggested next ARW state (honest, no gate skip):
