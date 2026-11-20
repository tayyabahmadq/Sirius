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
