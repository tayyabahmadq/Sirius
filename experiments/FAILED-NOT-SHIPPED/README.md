> # ⛔ QUARANTINE — FAILED EXPERIMENTS, NOT SHIPPED
>
> **Nothing in this folder is part of the delivered SIRIUS model.**
> The deployed artifact is `sirius-final` (Pass 5), documented in
> [../../docs/04-final-results.md](../../docs/04-final-results.md).
>
> These documents are kept only as an honest, auditable record of *what was tried and
> why it did not ship*. Do not treat any number here as a SIRIUS result.

## Why this folder exists

Phases 5 / 5R / 6 attempted to extend the auditor into a 9-capability "head of security"
(threat modeling, architecture review, API/CI/container checks, secrets, incident response,
logging). Two training attempts were made; **both failed acceptance**, and the pre-registered
failure branches were honored — no post-hoc knob-turning, no silent promotion.

| Experiment | Outcome | Why it did not ship |
|---|---|---|
| Pass 6 v1 (87 lead items) | FAILED | lead 0.127, restraint 0/5, suite34 0.673 |
| Pass 5R / chained-base control | FAILED control | adapter lost to runtime resets; recovered adapter not behaviorally equivalent (RECOVERY-WEAK) |
| Pass 6 v2 (5,208 items, same-session chain) | FAILED | lead 0.419 (<0.55), restraint 12/20 (<16/20), dependency_cve 0.875→0.625 |

## The shipped result (for contrast)

| Metric | Baseline | **Shipped `sirius-final` (Pass 5)** |
|---|---:|---:|
| suite34 overall | 0.753 | **0.795** |
| code_vuln | 0.700 | **0.700** (V02–V06: 1/5 → 4/5) |
| web_config | 0.688 | **0.917** |
| dependency_cve | 0.875 | **0.875** |
| Post-quant PPL ratio | — | **0.938** ≤ 1.05 ✓ |

## Contents (all FAILED — reference only)

- `07-phase5-result.md` — pass6 v1 post-mortem
- `08-phase5r-controls.md` — significance / serving-stack controls
- `09-prereg-phase5r.md` — pre-registration for the corrected retry
- `10-phase5r-decision.md` — RECOVERY-WEAK decision
- `11-phase6-prereg.md` — same-session chain pre-registration
- `12-phase6-result.md` — pass6 v2 acceptance failure

## Lessons carried forward (the useful part)

1. The retention/PPL gate is necessary but not sufficient — a recovered adapter can match
   PPL (0.806) yet fail behavioral equivalence. Persist adapters immediately.
2. Restraint must be *trained* with counterfactual safe/vulnerable pairs; prompting cannot
   create it (stock and pass5 both scored 0–1/20 traps).
3. Led capabilities improved 0.127 → 0.419 with 1,800 lead items and 774 restraint items —
   the next fix is more safe twins and seed coverage for the six sub-0.50 capabilities, not
   a larger rank.
4. Two evaluator bugs were found and fixed during this work (missing `--items v2`, and a
   `localhost` URL without scheme); an all-error 0.019 run was discarded, not reported.
