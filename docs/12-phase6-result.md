# Phase 6 — same-chain pass6 v2 result

## Verdict: improved substantially, but FAILED acceptance — keep `sirius-final` (pass5) deployed.

### What ran (same-session chain, PREREG docs/11)
- pass5 adapter already trained in this session; chained base built at s=0.5.
- Step 0b control on that base: suite34 0.705; McNemar vs shipped 0.795 -> p≈0.25 (not significant) => CHAIN-OK under the new statistical rule.
- pass6 v2 trained on `sirius_merged_pass5_s05` with the frozen recipe
  (r=16 α=16 rsLoRA, lr 1e-4, 2 epochs, gate/up/down, 5,208 items, 716 steps, 53 min).
  Training PPL gate: ratio **0.8229** (PASS).
- Dual gate + export: Q6_K + Q5_K_M exported; Ollama model `sirius-pass6v2` created.
- Two evaluator bugs fixed along the way and pushed: old 19 lacked `--items v2`; v2 19 had
  the `localhost` scheme bug (produced an all-error 0.019 run, discarded).

### Acceptance numbers (real)

**Lead v2 (110 items, per-capability floors ≥0.50, restraint ≥0.80):**

| Capability | Mean | Pass% | Floor |
|---|---:|---:|---|
| api_security | 0.433 | 40% | FAIL |
| ci_pipeline_security | 0.500 | 60% | OK |
| container_k8s_security | 0.500 | 60% | OK |
| incident_response | 0.233 | 20% | FAIL |
| logging_monitoring | 0.367 | 30% | FAIL |
| secrets_management | 0.633 | 70% | OK |
| secure_architecture | 0.400 | 30% | FAIL |
| secure_code_review | 0.300 | 30% | FAIL |
| threat_modeling | 0.400 | 40% | FAIL |
| **LEAD OVERALL** | **0.419** | — | target ≥0.55: FAIL |
| **restraint (20 traps)** | **0.708** | **12/20** | target ≥0.80 (16/20): FAIL |

**Suite34 (34 items):** overall **0.750** (bar ≥0.75 — just passes).
capabilities: code_vuln 0.750, web_config 0.875, dependency_cve **0.625** (was 0.875 in
pass5 — a real 0.25 regression), load_testing 0.750.

### Comparison to earlier attempts
| Model | Lead eval | Restraint |
|---|---:|---:|
| stock Q8_0 + serving stack (v2) | 0.063 | 1/20 |
| sirius-final + stack (v2) | 0.059 | 0/20 |
| pass6 v1 (v1 50-item eval) | 0.127 | 0/5 |
| **pass6 v2 (v2 110-item eval)** | **0.419** | **12/20** |

The v2 data (1,800 lead items, 774 restraint items, 63 counterfactual pairs) clearly taught
the behaviors — a ~7x lead-score gain and restraint from 0 to 12/20 — but not enough to
clear the pre-registered bars, and it cost a 0.25 drop in dependency_cve.

### Decision applied (PREREG §6/§7)
- No third blind retry (the remaining branches each allow ONE retrain; the session window
  does not permit another 54-minute run, and dep_cve regressed).
- Deployed model stays **`sirius-final` (pass5)**, overall 0.795.
- `sirius-pass6v2` artifacts are archived, not shipped.

### Next phase (requires new prereg/session)
- Branch 2 first: double safe twins 7->14 per capability, rebuild v2 data, retrain;
  restraint is the largest single gap (12/20 vs 16/20).
- Branch 1 for the five sub-0.50 capabilities: extend those specific seed files.
- Protect dependency_cve with more pass5 replay or an explicit dep-heavy replay slice.
