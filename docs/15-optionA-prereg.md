# Option A preregistration — reasoning-first format ablation

**Status: FROZEN before any data generation or training.** Date: 2026-11-28.
Commit before first data script: (recorded in git history).

## 0. Why this phase exists

Three facts from prior phases:

1. LABEL-first fine-tuning on our own suite did not generalize: shipped Pass 5 scored
   **0.225** vs stock **0.288** on the external CyberSecEval-derived test (McNemar p=0.0467).
2. Stock `Qwen2.5-Coder-1.5B` scored **0.501** on that same test — the base model, not rank,
   was the larger lever.
3. We have run the 351-item Python test three times and published it. It is **burned for
   selection**. Selecting a variant on it would be tuning on the test set.

Therefore:

- The 351-item Python set is demoted to **external DEV** (exploratory only; no ship claim).
- A disjoint **confirmatory lockbox** is frozen below and opened **once**, on one winner.
- **suite34 is demoted to a guardrail.** The objective flips to
  **maximize external DEV, subject to suite34 non-inferiority**. This is a principled change
  of endpoint, not a relaxation of standards.

## 1. Hypotheses

- **H1 (primary):** a reasoning-first target format improves external identification versus
  LABEL-first, holding negatives, data items, and hyperparameters constant.
- **H2 (mechanistic):** hard negatives contribute to suite-specific overfit; replacing them
  with random, label/length-matched negatives changes the format effect.

## 2. Data controls

Base corpus: `data/sirius_train_pass5.jsonl` (3,358 items; SHA256 recorded in the manifest).
Wikitext anchor: 10%, identical in all variants. No CSE-derived item enters any training data.

| Run | Target format | Negatives | Purpose |
|---|---|---|---|
| R0 | LABEL-first | hard | Control — reuse Pass 5 adapter, verify byte-identical data hash |
| R1 | Reasoning-first | hard (same items) | Isolates format (H1) |
| R2 | Mixed 50/50 | hard (same items) | Alternative format, same test |
| R3 | Reasoning-first | random, label/length-matched | Format × negatives interaction (H2) |

Reasoning-first target (cap 50–60 tokens, same item count as control — token delta logged,
not subsampled; this choice is frozen now):

```
Mechanism: <why the code is unsafe, 1–2 sentences>
Trigger: <condition that exploits it, 1 sentence>
Label: <canonical label>
```

Rationales are templated from existing verified `FUNCTION`/`RISK` fields in the Pass 5 corpus
and from our archetype taxonomy — **no teacher-model distillation**. Safe items use
`Mechanism: controls are present ... Label: not vulnerable / insufficient evidence` so CoT
does not teach overconfidence.

Contamination sweep: 13-gram + SHA256 dedup of every variant against suite34 (34 items),
the 104-item held-out eval, the 351-item DEV, and the lockbox. Report written to
`data/ablation/manifest.json`. **Amended 2026-11-28, before training:** the pre-existing
Pass 5 corpus has 244/3,358 items sharing 13-grams with suite34 prompts (paraphrases of the
same scenarios), 8 with eval100, and 0 with DEV or lockbox. This is pre-existing, byte-identical
across R0–R3, and therefore cannot confound the *format contrast*; it does inflate absolute
suite34 scores and is one more reason suite34 is a guardrail, not an endpoint. No newly authored
text in R1–R3 adds overlap (all four variants report the same 252 hits). Zero overlap is
required only for the frozen lockbox and for any newly authored rationale text — both hold.

## 3. Hyperparameters — identical for R1–R3

r=16, α=16, rsLoRA, dropout 0.05; target `q_proj,k_proj,v_proj,o_proj,down_proj`; layers 4–20;
bf16; completion-only loss; 10% wikitext anchor; lr 3e-5, 2 epochs, cosine, 5% warmup;
SplitLR (last 2 layers 1e-6, adapter 3e-5); **effective batch 16**; seed 42; early stop on
general PPL with composite stop; same trainer `scripts/07_train_colab.py`.

**Memory match (2026-11-28, before any successful run):** the 4 GB local GPU OOMs at
per-device batch 4. The new `ablation` pass config is byte-identical to pass5 except
`per_device_train_batch_size=1, gradient_accumulation_steps=16` — **effective batch remains
16**. Identical across R0–R3, so ceteris paribus is preserved. No learning-rate or data change.

**Hardware amendment (2026-11-28, before any ablation training):** Kaggle T4 sessions
recycled repeatedly mid-run (R1 lost twice at 260/462 and 292/462). To preserve the
ablation's ceteris paribus, **all four runs (R0–R3) are trained locally on the same
GTX 1650 Ti 4 GB with bf16** (torch reports bf16 support), seed 42. Identical hardware across
all arms keeps the format/negative contrast clean. **R0 is retrained locally** with the
byte-identical Pass 5 data (SHA256 in the manifest) so R0 vs R1–R3 is hardware-matched;
the shipped T4-trained Pass 5 adapter remains an external reference. This changes hardware
from Pass 5's T4 but does not change any hyperparameter or data, and the change is frozen
before seeing any ablation result. Kaggle Stage B hardware is not mixed into this lineage.

A run that fails the PPL gate is documented and quarantined — no hyperparameter retweak.

## 4. Grader

`scripts/ablation/grade_agnostic.py`: deterministic canonical-label extractor that accepts
`LABEL:`, `Label:`, or a trailing `Label:` line, plus the unchanged suite34 keyword-group
scorer from `04_sirius_baseline.py`. Keyword groups are scored on the whole answer; the
label extractor is used only for parse-rate gating, never as a rationale grader. No keyword
scoring of rationale text beyond the existing group scorer.

- 20 hand-checked unit cases in each format, committed.
- **Parity check (amended 2026-11-28, before any training):** re-grade an available raw dump
  with the new grader and require **exact reproduction of every stored per-item hit vector**.
  The original target "overall 0.795 ±1 item" cannot be met: the 0.795 acceptance run was in
  Colab and its raw outputs were never saved locally; the available dumps score 0.7453
  (`raw_dump_sirius-s05.json`) and 0.8406 (`raw_dump_sirius-pass5.json`). Per-item hit parity
  holds with zero mismatches on both, so the grader is format-equivalent to the original
  scorer; the 0.795 figure remains a separate, already-published acceptance result. This is a
  correction to the parity *definition*, not a relaxation of the ship gates.
- Grader SHA256 recorded at `reports/ablation/grader.sha256` at freeze time.

## 5. Lockbox (frozen before training, opened once)

Source: `walledai/CyberSecEval`, `instruct/javascript` + `instruct/java` parquet slices
(351 rows each), disjoint from the burned Python DEV by language and by 13-gram dedup.
These are CyberSecEval-derived but **not** the same language as DEV — declared limitation.
Per-language CWE keyword maps are derived from each slice's own `pattern_desc` and frozen in
`data/lockbox/keyword_maps.json`. Target n ≥ 300 after dedup. Item IDs and SHA256 hashes are
committed in `data/lockbox/items.sha256` **before training starts**.

Protocol: run **once**, on the single winner and its DEV-chosen scale, together with stock
0.5B and Pass 5. One McNemar exact two-sided test vs stock, α=0.05. No scale sweep, no
retries, no re-grading, no second confirmatory test. A borderline p in 0.04–0.06 is reported
as borderline, not re-rolled.

## 6. Tiered evaluation and gates

**Tier 1 — every run, hard:**

| Gate | Bar |
|---|---|
| Dual PPL ratio | ≤ 1.05 |
| suite34 (guardrail) | ≥ 0.75 (non-inferiority vs 0.795) |
| Per-category vs stock on suite34 | no category below stock − 0.10 |
| Label parse rate | ≥ 99% |
| Restraint probe | reported; regression vs Pass 5 flagged |

**Tier 2 — external DEV (351), exploratory:** each surviving variant × scale
s ∈ {0.25, 0.5, 0.75, 1.0}. McNemar vs stock and vs Pass 5 reported but labelled exploratory.
Scale is an inference dial only — never retrain for it.

**Selection rule:** among Tier-1 survivors, pick max external-DEV micro accuracy;
tie-break by suite34. Adapter scale chosen on DEV only.

**Confirmation trigger:** open the lockbox only if the winner's DEV gain is **≥ +0.05 over
stock** and **≥ +0.05 over Pass 5**. Otherwise publish the dev result, quarantine adapters,
and move to the capacity/data option.

## 7. Ship rule

Ship as Pass 7 only if **all** hold: lockbox McNemar p < 0.05 vs stock; suite34 ≥ 0.75;
PPL ≤ 1.05; no category collapse; parse rate ≥ 99%. `sirius-final` stays deployed until
full acceptance completes. Every outcome is published — winner, lockbox failure, or Tier-1
early stop.

## 8. Disclosures

Single seed per variant; 0.5B capacity ceiling remains; external DEV is burned and used only
exploratorily; lockbox is cross-language; suite34 remains a home suite used as guardrail only.
