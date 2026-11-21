# Phase 5 (pass6 security-lead injection) — result

## Verdict: FAILED — do not ship. Keep `sirius-final` (pass5) as the deployed model.

### What was run (faithful to `NEXT_PROMPT.md` Part 3)
1. **5a data** — dataset already built and verified: 3,680 items (3,358 pass5 replay +
   235 auditor knowledge + 87 lead Q&A/method/traps), 13-gram decontamination, 17 overlaps dropped.
2. **5b train** — T4 GPU:
   - Pass 5 retrained first to recover the adapter (lost to earlier runtime resets):
     gate PPL ratio 0.8062, adapter `sirius_lora_adapter_pass5` saved.
   - Chained base reconstructed at s=0.5 via script 18 (`sirius_merged_pass5_s05`).
   - Pass 6 trained on top: r=8, lr 1e-5, 1 epoch, down_proj, 10% anchor, SplitLR base.
     PPL gate ratio 0.9927 — retention fine.
3. **Dual gate** against the chained base: all scales pass; s=1.0 best (PPL ratio 0.9927,
   security loss 4.8428 → 4.8068).
4. **Export** Q6_K (505.7 MB) + Q5_K_M (420.1 MB), `ollama create sirius-pass6`.
5. **Evaluated** on the 50-item lead eval, the 34-item suite, and compared to baseline.

### Measured results

| Metric | Baseline (stock Q8_0) | Pass 5 (shipped) | Pass 6 | Target | Result |
|---|---:|---:|---:|---:|---|
| Lead capability mean (50 items) | 0.200 | 0.107 | **0.127** | ≥ 0.55 | FAIL |
| Restraint (5 traps) | 0.20 | 0.20 | **0.00** | ≥ 4/5 | FAIL |
| 34-item overall | 0.753 | 0.795 | **0.673** | ≥ 0.75 | FAIL (regression) |
| code_vuln | 0.700 | 0.700 | 0.650 | ≥ 0.680 | FAIL |
| web_config | 0.688 | 0.844 | 0.667 | ≥ 0.668 | borderline |
| dependency_cve | 0.875 | 0.875 | 0.750 | ≥ 0.855 | FAIL |
| load_testing | 0.750 | 0.750 | 0.625 | ≥ 0.730 | FAIL |
| Dual PPL ratio | — | 0.923 | 0.993 | < 1.30 | PASS |
| McNemar lead vs stock | — | p=0.219 | **p=0.289** | ≥ 0.05 | noise (not a win) |

### Diagnosis
The lead data is far too sparse to teach 9 new SDLC capabilities to a 0.5B: only **87 lead
items** across 9 capabilities (~6–13 each) plus 235 auditor-knowledge items. The conservative
pass6 recipe (r=8, 1 epoch) preserved retention but could not encode the new behaviors, while
the 3,358-item replay was diluted enough to lose ~0.12 of the pass5 suite score. Capacity
escalation (the plan's prescribed one step: r=16, 2 epochs) is unlikely to fix a data-coverage
problem; restraint in particular collapsed to 0/5 (the model manufactures findings).

### Recommendation (do NOT skip the diagnosis)
1. Keep `sirius-final` (pass5) deployed. Do not ship `sirius-pass6`.
2. Before another training run, expand the lead corpus to **≥200 items per capability**
   (9 × 200 ≈ 1,800 new items) with explicit restraint traps (~100), and rebuild with
   decontamination against all eval sets.
3. The external "CoT scratchpad" blueprint is directionally sound but requires exactly that
   data expansion: `<thinking>` targets must be generated into the training set, and new eval
   items written for the changed output contract. It is a Phase 6 project, not a tweak.
4. The serving-side improvements from that blueprint WERE adopted with zero training risk:
   dynamic context routing in `sirius_cli.py` (one playbook injected), syntax anchors and a
   golden example in `secure_code_review.md`/`api_security.md`, an explicit Restraint Rule in
   `ROLE.md`, and conservative decoding (`min_p=0.05`, `repeat_penalty=1.1`) in `cmd_ask`.

### Artifacts
- `sirius_pass6_Q6_K.gguf`, `sirius_pass6_Q5_K_M.gguf`, `sirius-pass6:latest` (local, NOT shipped)
- `sirius_eval_gate_pass6.json`, `sirius_train_log_pass6.json`
- `lead_report_sirius-pass6.json`, `sirius_reports/baseline_sirius-pass6_*.json/.md`
# 07a — Correction to 07-phase5-result.md (post-review)

Append this to `docs/07-phase5-result.md` in the repo (or commit this
file alongside it). It supersedes two claims in the original result doc.

## 1. The suite regression claim is withdrawn as unverified

The original doc attributes the 0.795 → 0.673 suite34 drop to "replay
diluted enough to lose ~0.12". Three facts contradict that causal story:

- **Scale**: −0.122 on 34 items ≈ 4 flips. Exact McNemar at the best
  plausible split (4,0) gives p = 0.125; (5,1) p = 0.219; (6,2)
  p = 0.289. Not significant at any plausible split. The delta is
  *directionally lower, not established* — the same honesty standard we
  applied to the lead-eval "wins" applies to this loss.
  (`22_significance.py selftest` reproduces these numbers from code.)
- **Mechanism**: replay of pass5 data should *preserve* pass5 behavior.
  At lr 1e-5 / r=8 / down_proj-only / 1 epoch, training barely moved
  weights — the pass6 adapter's dual-PPL ratio against its own chained
  base was 0.9927. A near-no-op run is an implausible cause of a
  0.12-point capability loss.
- **Confounds**: the deployed artifact = base + 0.5·(retrained pass5) +
  1.0·pass6. The s=0.5 chain halves the pass5 adapter, and the pass5
  adapter itself was retrained from scratch (gate ratio 0.8062 measures
  retention, not behavioral equivalence to the adapter that scored
  0.795). The categories that dropped — web_config 0.844→0.667,
  dependency_cve 0.875→0.750, load_testing 0.750→0.625 — are exactly
  the pass5-taught ones: the signature of the diluted/recovered chain.

**Required control (Step 0b in NEXT_PROMPT Part 4):** evaluate
`sirius_merged_pass5_s05` bare (no pass6 adapter) on the full
acceptance set. ≈0.67 ⇒ the chain/recovery caused the whole regression
(fix: chain at s=1.0 or resume the pass5 adapter — no second merge);
≈0.79 ⇒ pass6 training genuinely damaged the suite. Until this runs,
the regression's cause is *unresolved*.

## 2. The baseline column was under-weighted

Stock Q8_0 scored **0.200** on the lead eval — above both fine-tunes
(pass5 0.107, pass6 0.127; overlapping Wilson CIs, but directionally
consistent). Restraint: stock 1/5, pass5 1/5, pass6 0/5 — restraint was
never present to lose. Conclusion recorded for Phase 5R: the auditor
distribution suppresses lead behavior, so (a) restraint must be trained
as a first-class behavior (counterfactual safe/vuln pairs), and (b) a
role-split deployment (stock + ROLE serving stack for lead queries,
sirius-final for diff/audit gates) is a live option — the serving-stack
A/B is Step 0c.

## What stands unchanged

The no-ship verdict, the keep-pass5-deployed decision, the absolute
target failures (0.127 vs ≥0.55 lead, 0/5 vs ≥4/5 restraint), and the
refusal to escalate capacity against a data problem. The correction
narrows the *diagnosis*, not the verdict.

