# Phase 4b — Post-quantization PPL re-check (local CPU)

## Why local
Colab GPU quota was exhausted; perplexity is a CPU measurement anyway. No local C++ toolchain
was available, so the official prebuilt Windows CPU llama.cpp binary (`b12584`,
`llama-perplexity.exe`) was downloaded into `.tools/` (git-ignored) and used directly.

## Method
- Tool: `llama-perplexity.exe` (llama.cpp b12584, CPU, `-ngl 0`)
- Corpus: 200,000 chars of wikitext-2-raw **test** split (held out; 93 chunks × 512 tokens),
  identical for both models
- Models: the shipped `sirius_final_Q6_K.gguf` (Pass 5 adapter at s=0.5) and the original
  `Qwen2.5-0.5B-Instruct Q8_0.gguf` baseline

## Measured results

| Model | PPL | Std err |
|---|---:|---:|
| Base Q8_0 GGUF | 15.6762 | ±0.295 |
| **Shipped final Q6_K GGUF** | **14.7065** | ±0.271 |

**Like-for-like ratio (final / base) = 14.7065 / 15.6762 = 0.938** → gate ≤ 1.05 → **PASS**.

The shipped quantized artifact has *lower* perplexity than the unmodified base on this
corpus — quantization did not damage the model; the fine-tune improved language modeling.

## Important caveat about the script's raw output
The first run printed `PHASE 4 GATE: FAIL` because `--reference-ppl` was accidentally set to
the *final* model's PPL (14.7065) while measuring the *base* (15.6762), inverting the ratio to
1.0659. That is a reference-argument mistake, **not** a model failure. Two script issues were
also fixed and committed to the repo:
1. `write_wikitext_test()`: legacy `wikitext` dataset alias → canonical `Salesforce/wikitext`.
2. PPL parsing: newer llama.cpp prints `Final estimate: PPL = 14.7065 +/- 0.27128` instead of
   `Perplexity: 24.47`; the parser now handles both.

The original gate reference (24.22) came from a different measurement method (script 07's
averaged per-sample losses over 200 short samples) and is **not comparable** to
`llama-perplexity`'s document-level estimate. Comparing GGUF to GGUF with one tool and one
corpus is the valid check, and it passes.

## Verdict
PHASE 4b: **PASS** — safe to ship the Q6_K artifact. No re-quantization needed.

Artifacts: `ppl_recheck_log.txt`, `ppl_base_log.txt`,
`ppl_recheck_Qwen2.5-0.5B-Instruct Q8_0.json` (local, outside the repo).
