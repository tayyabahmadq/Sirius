# Stage B preregistration — port the Pass 5 recipe to Qwen2.5-Coder-1.5B

**Status: FROZEN before execution.** Date: 2026-11-28.
**Executes only if all three Stage A rules pass** (docs/15-base-model-ab-prereg.md).
If Stage A fails, this document is void and the 0.5B base is kept.

## Why conditional

The user has approved bringing Qwen2.5-Coder-1.5B into the project. Approval authorizes the
work; the frozen Stage A evidence decides *whether* it is warranted. Skipping that gate would
repeat the exact mistake that produced the CyberSecEval loss — changing the model and then
grading it on our own suite.

## Frozen recipe (identical to shipped Pass 5, base swapped only)

`python 07_train_colab.py --pass-name pass5 --train sirius_train_pass5.jsonl
--base-model Qwen/Qwen2.5-Coder-1.5B-Instruct --skip-install-check`

- r=16, α=16, rsLoRA, dropout 0.05
- target modules `q_proj, k_proj, v_proj, o_proj, down_proj`; layers 4–20
- bf16 (no 4-bit); completion-only loss; 10% wikitext anchor
- lr 3e-5, 2 epochs, cosine + 5% warmup, effective batch 16
- SplitLR: last 2 layers unfrozen at 1e-6, adapter at 3e-5
- composite dual stop (general PPL + security loss), patience 3, min delta 0.005
- seed 42

No rank change, no epoch change, no new data. Any deviation is logged in the result doc.

## Post-training (frozen order)

1. Training PPL gate: ratio < 1.30 on wikitext test.
2. Dual gate + adapter scale sweep s ∈ {1.5, 1.0, 0.75, 0.5}; choose the **lowest** s that
   passes both gates (as in Pass 5, where s=0.5 beat s=1.0).
3. Export Q6_K + Q5_K_M via `11_export_gguf.py`; post-quant PPL ratio ≤ 1.05.
4. Re-run **all three evaluations** on the exported model:
   - suite34 (`04_sirius_baseline.py --full`) + V02–V06 label check
   - eval100 (`04b_run_eval100.py`) with paired McNemar vs stock coder
   - CVIdent-351 (`24_cyberseceval_derived.py`, frozen harness) with paired McNemar vs
     stock coder — this is **co-primary**, not an afterthought

## Ship gate (ALL required; otherwise keep `sirius-final` deployed)

| # | Gate | Threshold |
|---|---|---|
| 1 | suite34 overall | ≥ stock-coder baseline + 0.04 |
| 2 | suite34 per-capability | no capability > 0.02 below stock-coder baseline |
| 3 | V02–V06 canonical labels | ≥ 4/5 |
| 4 | dual PPL ratio | < 1.30 |
| 5 | post-quant PPL ratio | ≤ 1.05 |
| 6 | eval100 vs stock coder | not significantly worse (p ≥ 0.05 or significant in candidate's favour) |
| 7 | CVIdent identification vs stock coder | ≥ stock-coder micro, not significantly worse |
| 8 | CVIdent restraint vs stock coder | ≥ stock-coder restraint (0.0) |
| 8b | CVIdent restraint vs **shipped** model | ≥ 0.036 (moved here from Stage A rule 2 by `docs/17-stage-a-result-and-amendment.md`) |

If shipped: update README badge/results, CITATION.cff model description, models/README.md,
and create a new Ollama tag. `sirius-final` artifacts are retained, not deleted.

## Declared limitation

suite34 and eval100 remain home suites. Gate 7 is the only independent evidence of general
capability; it is therefore co-primary and cannot be dropped for convenience.
