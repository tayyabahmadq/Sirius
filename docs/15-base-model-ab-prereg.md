# Base-model A/B preregistration — confirmatory Stage A

**Status: FROZEN before the Stage A run.** Date: 2026-11-28.

## Why

The shipped `sirius-final` (0.5B) lost the external CyberSecEval-derived identification
test (0.225 vs stock 0.288, McNemar p=0.0467) while gaining a little restraint (3.6% vs 0%).
The leading hypothesis is now **base-model capacity/specialization**, not more fine-tuning
data: a code-specialized model should handle language-level mechanisms (exec, shell calls,
deserialization) that the 0.5B audited corpus did not teach.

**Pilot (exploratory, not decision evidence):** 7 hand-picked CyberSecEval snippets, one per
failure CWE, frozen prompt/grader. Stock 0.5B scored 2/7; stock `qwen2.5-coder:1.5b` scored
4/7 (CWE-94, CWE-89, CWE-78, CWE-502), at 4.1s vs 3.3s warm latency on CPU. This pilot
motivated the hypothesis; the confirmatory 351-item run below is what decides it. One pilot
"pass" (CWE-502) was a keyword false positive — the grader limitation is declared below.

## Frozen design

- **Candidate:** `qwen2.5-coder:1.5b` — stock, unmodified, already installed locally.
- **Comparator:** `qwen2.5:0.5b-instruct-q8_0` — stock, results already in
  `results/cyberseceval_derived.json` (micro 0.288, restraint 0/276). No re-run.
- **Reference:** shipped `sirius-final` (micro 0.225, restraint 10/276 = 3.6%).
- **Harness:** `scripts/24_cyberseceval_derived.py`, unchanged, same frozen prompt,
  same frozen CWE keyword map, same `temperature=0`, `num_predict=120`. Output:
  `results/cyberseceval_derived_coder15.json`. The control is **on** (276 secure
  counterparts) so restraint is compared under identical conditions.
- **Secondary harness:** `scripts/04_sirius_baseline.py --model qwen2.5-coder:1.5b --full`
  on the 34-item suite, output under `reports/baseline_coder15/`; compared to the
  stock-0.5B baseline of 0.753 with per-capability 0.700 / 0.688 / 0.875 / 0.750.
- **Statistics:** paired McNemar exact between candidate and stock 0.5B over the same
  351 item indices (script `22_significance.py mcnemar b c`).

## Decision rule (frozen — no post-hoc adjustment)

**Proceed to Stage B (port the Pass 5 recipe onto the 1.5B coder) only if ALL hold:**

1. Candidate CVIdent identification micro ≥ **0.338** (stock 0.288 + 0.05), **and**
   paired McNemar vs stock 0.5B is significant **in the candidate's favour** (p < 0.05).
2. Candidate restraint-control micro > **0.036** (shipped) and > 0 (stock).
3. Candidate suite34 overall ≥ **0.753**, with no capability more than **0.02** below
   the stock-0.5B value.

**If any fails:** keep the 0.5B base and move to inference-time fixes (retrieval over
playbooks / routing). Do not retrain a larger base on the same home suite — that would
repeat the exact overfitting that this prereg exists to prevent.

**Stage A causes no ship change under any outcome.** `sirius-final` stays deployed.

## Declared limitations

- The keyword grader credits literal tokens. Stock tends to quote code verbatim; a model
  answering semantically can be undercredited. Conversely, a token used in the wrong
  context can be falsely credited (seen in the pilot on CWE-502). We report the frozen
  score as primary and qualitative misgrades in the write-up; **we do not re-grade after
  seeing results**, because that would invalidate the comparison.
- suite34 is our own suite. Passing rule 3 only checks that the base swap does not regress
  it; it is not evidence of general ability. Evidence for that comes from rule 1.

## Reproduce

```
python scripts/24_cyberseceval_derived.py \
    --models qwen2.5-coder:1.5b \
    --out results/cyberseceval_derived_coder15.json
python scripts/04_sirius_baseline.py --model qwen2.5-coder:1.5b --full \
    --outdir reports/baseline_coder15
```
