# Phase 5R — Step 0 control results (before retry)

## 0a — Significance (22_significance.py selftest: PASS)

| Claim | Numbers | p / CI | Verdict |
|---|---|---|---|
| suite34 pass5→pass6 "regression" 0.795→0.673 | ≈4 net flips on 34 | exact McNemar (4,0) p=0.125; (5,1) 0.219; (6,2) 0.289 | **not significant** — directionally lower, cause unresolved |
| lead eval 50-item means | pass5 0.107 (5/50), pass6 0.127 (6/50), stock 0.200 | Wilson 95%: 6/50 = [0.056, 0.238], 10/50 = [0.112, 0.330] | overlapping — no lead "win" |

The original doc's causal claim ("replay dilution lost ~0.12") is **withdrawn** (07a correction).

## 0c — Serving-stack A/B on the 110-item v2 eval

| Model + stack | Lead overall | Restraint | Floor gate |
|---|---:|---:|---|
| stock Q8_0 + ROLE/playbook stack | 0.063 | 1/20 (5%) | FAIL (all 9 caps + restraint) |
| sirius-final + same stack | 0.059 | 0/20 (0%) | FAIL |

The v2 eval is much harder than v1 (10/cap, 20 traps). Both models are near zero;
**role-split gives no advantage** on v2 — stock is 0.004 higher, well within noise.
Restraint is not a prompting capability; it must be trained with counterfactual pairs.

## 0b — Chained-base control: BLOCKED (not skipped)

Requires `sirius_merged_pass5_s05` bare. The pass5 adapter/merged dir were wiped by Colab
runtime resets; Colab GPU quota is currently exhausted (CPU-only runtime) and Saturn Cloud
free tier has restricted network access. **No conclusion about the suite delta is possible
yet** — this is explicitly an unresolved control, not a "pass6 damaged the suite" finding.

## Next action (unchanged from Part 4)
1. Recover pass5 adapter (one ~30-min T4 run) → reconstruct chained base → run 0b.
2. If 0b ≈0.67 → chain at s=1.0 / resume pass5 adapter; if ≈0.79 → fix data/recipe only.
3. Then train pass6 v2 with the corrected recipe (r=16, lr 1e-4, 2 epochs, gate/up/down,
   5,208 items, new-signal share 40.4%, 63 counterfactual pairs).
4. Never report a suite delta as real until 0b and McNemar agree.

## Data verified locally (Step 1)
`sirius_train_pass6_lead_v2.jsonl`: 5,208 items — replay 3,105 / knowledge 216 / lead-v1 87 /
lead-v2 1,800; 200/cap × 9; 774 restraint items (14.9%); 63 counterfactual pairs;
0 13-gram overlap with all eval sets; selftest of `lead_eval_items_v2.json` 110/110.
