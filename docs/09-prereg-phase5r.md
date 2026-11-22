# PREREG — Phase 5R: Step-0b control + Pass6-v2 protocol (pre-registered)

**Status at registration:** 0a DONE (suite delta p=0.125, not significant;
lead CIs overlap; doc-07 causal claim withdrawn, committed at `c374fc4`).
0c DONE (stock+stack 0.063 vs sirius-final+stack 0.059 on the 110-item v2
eval — tied at noise; restraint 1/20 vs 0/20). 0b PENDING on the local
pass5 adapter recovery (GTX 1650 Ti, batch 1 / seq 256).

This document freezes the decisions BEFORE the 0b numbers exist. Every
threshold below was chosen from data that predates the local recovery run.
Deviations after results are logged in the Deviations section, never
silently absorbed. The decision itself is applied mechanically by
`23_zero_b_control.py` — no eyeballing, no post-hoc branch selection.

## 0. Facts this protocol rests on (verified, not assumed)

- Shipped `sirius-final` = base + 0.5·**original** pass5 adapter, scored
  **0.795** suite34 (NEXT_PROMPT Part 2: "Pass 5 @ s=0.5 PASSED
  acceptance"). Therefore s=0.5 halving per se is NOT a live confound —
  it passed acceptance with the original adapter. The confound under
  test is the **recovered adapter's behavioral equivalence at s=0.5**
  (the 0.8062 gate ratio measured retention, not behavior).
- The v1 chained base was built from a from-scratch re-recovery after a
  Colab wipe; the local 1650 Ti run is recovery #3. Pass6 v2 will train
  on recovery #3's chained base — so the 0b control measures exactly the
  base pass6 v2 will stand on. It is both archaeology for v1's
  regression AND the entry qualification for the v2 base.
- Serving-side levers are exhausted (0c: the routing stack did not
  separate stock from the fine-tune; both ~0.06 on v2). The remaining
  lever is the training distribution — v2 data is built, verified, and
  frozen (manifest: 5208 items, 200/cap × 9, 63 counterfactual pairs,
  774 restraint items, 40.4% new-signal share, 0 eval overlap).
- Truncation at seq 256, quantified on the actual data
  (`scripts/analyze_pass5_len.py`): pass5 replay — median 116 tok,
  p90 134, 0/3358 over 256 (pessimistic chars/3 bound); v2 dataset —
  median 124 tok, p90 160, 28/5208 (0.5%) worst-case tails cut. Decision
  tokens sit first in 99.4% (replay, LABEL-first) and 100% (lead2,
  RECOMMENDATION-first) of items. **seq 256 is pre-cleared for both
  runs; seq 384 is the free upgrade if VRAM allows, not a requirement.**

## 1. Recovery-gate preconditions (must pass BEFORE 0b is interpreted)

Thresholds chosen now, banded around the observations that predate this
run (recovery #2: security ratio 0.8062; shipped pass5 general ratio
0.923):

| Metric (merged recovery vs base) | ≤ target band | action if outside |
|---|---|---|
| security-dev PPL ratio | ≤ 0.85 | > 0.85–0.95: proceed, flag WEAK-RECOVERY, s=1.0 check becomes mandatory (§2). > 0.95: do NOT run 0b — fix recovery first (§4 list), re-gate |
| general wikitext PPL ratio | ≤ 1.05 | > 1.05: recovery is damaging the base — fix first (§4), re-gate |

Recovery-gate classification is recorded in the 0b decision JSON either
way; a flagged recovery does not invalidate 0b, it sharpens its
interpretation (§2 branch B2).

## 2. The 0b decision (applied by 23_zero_b_control.py, no exceptions)

Inputs: suite34 of the **bare chained base** (base + 0.5·recovery #3, no
pass6 adapter) via `04_sirius_baseline.py --full`; lead v2 + traps of the
same artifact via `19_eval_capabilities.py --items v2` (recorded for the
archive; lead does NOT gate this decision — it gates pass6-v2
acceptance).

| suite34 of bare chained base | Branch | Action (frozen) |
|---|---|---|
| ≥ 0.75 | **CHAIN-OK** | the recovered adapter at s=0.5 is behaviorally equivalent to the original; v1's suite drop is attributed to pass6-v1 training/noise, consistent with p=0.125. Pass6 v2 trains on THIS base (script 18 output, s=0.5) |
| ≤ 0.72 | **CHAIN-HARM** | do not train on the s=0.5 chained base. Immediately run the s=1.0 sanity check (below) and branch on it |
| 0.72–0.75 | **GRAY** | default to the s=1.0 base (full adapter strength, no dilution; safer and costs nothing); log as ambiguous; s=1.0 check still runs for the record |

**s=1.0 sanity check** (runs in CHAIN-HARM and GRAY): `18 --scale 1.0`
→ `04 --full` on base + 1.0·recovery #3.

- s1.0 suite34 ≥ 0.75 → the recovery is fine at full strength; the
  failure mode is the s=0.5 **interaction** with this particular
  adapter. Action: pass6 v2 trains on the **s=1.0 merged base**.
- s1.0 suite34 < 0.75 → **RECOVERY-WEAK**: recovery #3 is behaviorally
  deficient (the local adaptation or third-time variance). Action: fix
  recovery per §4, re-gate (§1), redo 0b. **Do not proceed to pass6 v2.**

Rationale for 0.72/0.75: 0.75 is the standing acceptance bar (25.5/34
items); 0.72 is one item below it; sirius-final reference is 0.795.
Between the two is genuinely ambiguous, and the default (s=1.0) is the
option that cannot dilute the adapter.

## 3. Pass6-v2 training recipe (FROZEN — as shipped in 07_train_colab.py)

r=16 α=16 rsLoRA, **lr 1e-4, 2 epochs, target_modules gate/up/down**
(knowledge lives in the FFN), layers 4–20, bf16, completion-only, 10%
wikitext anchor interleaved, early-stop patience 3, composite stop, seed
42, data `sirius_train_pass6_lead_v2.jsonl` (manifest hash recorded at
run time). Base model = whatever §2 selected — recorded in the decision
JSON, not re-chosen later.

Allowed hardware adaptations (NOT recipe changes): micro-batch 1 with
gradient_accumulation_steps=16 (effective batch 16 preserved — Colab's
4×4); seq 256 (pre-cleared above) or 384. Forbidden post-hoc changes:
lr, epochs, r, targets, anchor ratio, data. If OOM at batch 1 seq 384 →
seq 256 (quantified safe).

## 4. Pre-ordered fixes (in this order, nothing else)

For a rejected/weak recovery: (1) verify effective batch = 16
(accumulation), (2) seq 320–384 if not already, (3) re-run once. No lr /
r / epoch / target changes — those are recipe, and the recipe is frozen.

## 5. Acceptance gates for pass6 v2 (FROZEN, from NEXT_PROMPT Part 4)

- Lead v2 overall ≥ 0.55 AND every capability floor ≥ 0.50 (n=10 each)
  AND restraint ≥ 0.80 (n=20).
- suite34 ≥ 0.75; eval100 within paired noise vs pass5 (McNemar p ≥ 0.05
  — script 22 computes it; symmetric standard: improvements also need
  p < 0.05 to be claimed as real).
- Dual PPL gate < 1.30; shipped-GGUF PPL re-check ≤ 1.05× bf16 merge.
- Reports use fixed names; per-capability numbers are published, not
  just means.

## 6. Pre-registered failure branches (no knob-turning after results)

1. Lead improves, suite34 ≥ 0.75, some capability < 0.50 → corpus gap:
   extend THAT capability's seed file (new templates via
   `scripts/seeds/gen_<cap>.py`), rebuild 21, ONE retrain maximum.
2. Restraint < 0.80 → double the safe twins (7 → 14 safe templates per
   capability), rebuild 21, ONE retrain maximum. No other change.
3. suite34 < 0.75 while lead ≥ 0.55 → recipe-vs-retention trade-off:
   deployment reverts to sirius-final; ONE free diagnostic allowed —
   `20_merge_scale_sweep.py` at capability level; if an s* passes both
   gates, ship at s*; otherwise stop and report.
4. PPL gate fail → revert to sirius-final; archive pass6-v2 artifacts.
5. Everything fails → STOP. No third blind retry. Escalation (e.g., a
   larger base model for lead queries) is a NEW phase requiring a NEW
   pre-registration — not a knob on this one.

## 7. Deviation log (append-only)

| # | Deviation | Why | Approved by |
|---|---|---|---|
| D1 | Recovery #3 runs locally (1650 Ti) instead of Colab T4 | Colab GPU quota exhausted; Saturn network-limited | protocol §0 (both are bf16; gate absorbs variance) |
| D2 | micro-batch 1 | 4 GB VRAM | allowed iff accum=16 (§3) |
| D3 | seq 256 | VRAM headroom | quantified: 0% replay / ≤0.5% v2 truncation (§0) |
| D4 | recovery #3 ≠ recovery #2 bit-identical | Colab wipes destroyed both prior adapters | gate §1 absorbs; 0b measures the exact base pass6 v2 uses |

*Registration closes here. Anything decided after the 0b numbers exist
must appear in §7 with a reason, or it did not happen.*
