# Phase 5R — Step 0b decision: RECOVERY-WEAK (NO pass6 v2)

## Mechanical decision (23_zero_b_control.py, PREREG §2)

```
suite34 bare chained base (base + 0.5·recovered pass5) : 0.705
suite34 s=1.0 merged (base + 1.0·recovered pass5)      : 0.493
BRANCH: RECOVERY-WEAK
ACTION: even s=1.0 < 0.75 — recovery #3/#4 is behaviorally deficient;
        fix per PREREG §4, re-gate, redo 0b; NO pass6 v2
```

`zero_b_decision.json` written in the Colab runtime.

## Per-capability detail (34-item suite)

| Capability | bare s=0.5 | s=1.0 | shipped `sirius-final` (original adapter, s=0.5) |
|---|---:|---:|---:|
| code_vuln_scan | 0.600 | 0.450 | 0.700 |
| web_config_checks | 0.844 | 0.458 | 0.917 |
| dependency_cve | 0.875 | 0.500 | 0.875 |
| load_runtime | 0.500 | 0.562 | 0.750 (est. from pass5 s=0.5) |
| **OVERALL** | **0.705** | **0.493** | **0.795** |

## Diagnosis

The from-scratch recovered pass5 adapter matches the original on the **retention** gate
(PPL ratio 0.8061 vs 0.8062 for the earlier recovery) but is **not behaviorally equivalent**:
the same s=0.5 merge scores 0.705 instead of the shipped 0.795, and at full strength it
collapses to 0.493. This is exactly the confound the PREREG was written to catch — the PPL
gate measures language-model retention, not the security-label behavior that pass5 learned.

Root cause of the recovery problem: every Colab session reset wiped `/content`, destroying
the original pass5 adapter. Four from-scratch recoveries (same recipe, different retrains)
all pass the PPL gate but not the behavioral control. Sequence length (256, pre-cleared with
0% replay truncation) and effective batch (16) are not the issue.

## Decision applied

- **NO pass6 v2 training.** The pre-registered failure branch is honored; no post-hoc
  knob-turning on rank, lr, epochs or data.
- **Deployed model stays `sirius-final` (pass5, overall 0.795)** — the only artifact that
  has passed the full acceptance gate.
- `sirius-pass6` (v1) and the recovered chained bases are archived, not shipped.

## What would actually unblock Phase 5R

1. Run pass5 training and pass6 v2 **in the same Colab session** — no recovery — or persist
   the pass5 adapter to Drive/a mounted volume immediately after training (`!cp -r
   sirius_lora_adapter_pass5 /content/drive/MyDrive/...`). The adapter is a few MB and easy
   to keep; losing it is what forced the unsuccessful recovery chain.
2. Re-run the 0b control on that original adapter's chained base. If it scores ≈0.79,
   CHAIN-OK applies and pass6 v2 can proceed on the frozen recipe
   (r=16, lr 1e-4, 2 epochs, gate/up/down, 5,208-item v2 data).
3. This requires a NEW pre-registration / session — it is not a knob on this one.

## Phase status

| Phase | Status |
|---|---|
| 0a significance | DONE (suite delta p=0.125, not significant) |
| 0c serving-stack A/B | DONE (role-split rejected) |
| 0b chained-base control | DONE → RECOVERY-WEAK |
| pass6 v2 training | NOT STARTED (pre-registered failure branch) |
| Deployment | `sirius-final` (pass5) unchanged |
