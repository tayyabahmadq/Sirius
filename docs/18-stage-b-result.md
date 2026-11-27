# Stage B final result — trained Qwen2.5-Coder-1.5B (NOT shipped)

Prereg: `docs/16-stage-b-prereg.md`; amendment: `docs/17-stage-a-result-and-amendment.md`.
Raw answers: `results/cyberseceval_derived_stageb.json`.

## Numbers

| Metric | Stock coder 1.5B | Trained Stage B | Shipped `sirius-final` |
|---|---:|---:|---:|
| CVIdent-351 identification micro | 0.501 | **0.396** | 0.225 |
| CVIdent restraint control (276 secure counterparts) | 0.000 | **0.1739** | 0.036 |
| suite34 overall | 0.902 | **0.912** | 0.795 |
| suite34 code_vuln | 0.900 | **0.650** | 0.700 |
| Training PPL gate | — | 0.835 PASS | 0.923 |

Paired McNemar exact (two-sided) on identification:
- Stage B vs stock 0.5B: 83 Stage-B-only correct vs 45 stock-only, n=128, **p=0.001** (win).
- Stage B vs shipped: 92 vs 32, n=124, **p<0.001** (win).
- Stage B vs **stock coder 1.5B**: 42 vs 79, n=121, **p=0.001** (loss).

## Interpretation

Training the same Pass 5 recipe on the stronger coder base produced the best **restraint**
of any model so far (17.4% vs shipped 3.6%, stock 0%) and beat both 0.5B models on external
identification — but it **lost 0.105 of the stock coder's identification ability** and
collapsed code_vuln on suite34 from 0.900 to 0.650. So:

- The 0.5B → 1.5B base swap is the real capability lever.
- LABEL-first fine-tuning reliably adds restraint but **trades away general code reasoning**.
- This is direct evidence for the Option A hypothesis class: the *format and data* need to
  change before another fine-tune is worth running.

## Decision

**Not shipped.** Gate 2 (no capability >0.02 below stock coder) failed decisively; gate 1
(suite34 ≥ stock + 0.04 = 0.942) also failed. `sirius-final` remains deployed.
All artifacts (adapter, gate log, GGUF recipe) remain in the repo as evidence.
