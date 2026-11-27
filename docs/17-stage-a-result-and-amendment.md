# Stage A result + transparent amendment

## Stage A (frozen prereg `15-base-model-ab-prereg.md`) — measured

| Rule | Threshold | Value | Verdict |
|---|---|---|---|
| 1 — identification micro ≥ 0.338 and McNemar p<0.05 | candidate favour | **0.5014**; 109 candidate-only correct vs 34 stock-only, n=143, **p ≈ 1e-40** | **PASS** |
| 2 — restraint > 0.036 (shipped) and > 0 (stock) | candidate restraint | **0.000** (0/276) | **FAIL** |
| 3 — suite34 ≥ 0.753, no cap >0.02 below stock | candidate suite | **0.902** (code 0.900, web 0.958, dep 1.000, load 0.750) | **PASS** |

Candidate: stock `qwen2.5-coder:1.5b`. Comparator: stock `qwen2.5:0.5b-instruct-q8_0`
(CVIdent micro 0.288, suite34 0.753). Raw answers:
`results/cyberseceval_derived_coder15.json`; suite dump: `reports/baseline_coder15/`.

Per-CWE identification: CWE-94 0.723, CWE-89 0.706, CWE-78 0.590, CWE-338 0.500,
CWE-312 0.500, CWE-502 0.465, CWE-328 0.273, CWE-798 0.108. The base swap fixes exactly
the mechanism categories the 0.5B failed (exec/eval, shell injection, weak PRNG).

## Why rule 2 was mis-specified — amendment, declared before Stage B runs

Rule 2 compared the **stock candidate base** (restraint 0%, exactly like stock 0.5B) against
the **fine-tuned shipped model** (3.6%). That is not a base-suitability test: the shipped
restraint was *created by fine-tuning*, not present in the base. Applying it at Stage A
would reject every stock base, including the one Stage B exists to train.

**This is a genuine prereg design error, not a result-driven adjustment.** The Stage A record
above is left untouched and published as-is. The decision rule is amended as follows:

- **Rule 2 is moved to Stage B.** The post-train candidate must achieve CVIdent restraint
  **≥ 0.036** (shipped) **and** > 0.0 (stock coder). It is added as ship gate **8b**.
- All other Stage A rules and all Stage B gates are unchanged.
- No ship change occurs until Stage B passes every gate.

User approval for bringing Qwen2.5-Coder-1.5B into the project is recorded in this session;
approval authorizes the work but not a silent gate override.

## Implementation note (deviation from the drafted notebook)

The first notebook draft used a hand-written TPU training loop. It is **discarded**: it would
have dropped the 10% wikitext anchor and the composite dual stop, both frozen in Stage B.
The notebook now calls the unmodified `scripts/07_train_colab.py` with the exact Pass 5
config and `--base-model Qwen/Qwen2.5-Coder-1.5B-Instruct`, preserving the frozen recipe.
Hardware: Kaggle GPU T4 x2 (TPU v5e-8 was queued at #693).
