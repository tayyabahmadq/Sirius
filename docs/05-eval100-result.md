# Phase 4a — Eval100 (104 held-out items) result

Command (after fixing a `--host` scheme bug in `04b_run_eval100.py`):

```bash
python 04b_run_eval100.py --model qwen2.5:0.5b-instruct-q8_0
python 04b_run_eval100.py --model sirius-final \
    --compare eval100_report_qwen2_5_0_5b-instruct-q8_0.json
```

Selftest: **104/104** reference answers hit all their own keyword groups (grader-aligned items).

| Capability | n | Baseline mean | sirius-final mean | Δ |
|---|---:|---:|---:|---:|
| code_vuln_scan | 46 | 0.543 | 0.522 | −0.021 |
| web_config_checks | 16 | 0.354 | 0.292 | −0.062 |
| dependency_cve | 12 | 0.125 | 0.125 | 0.000 |
| load_testing | 30 | 0.217 | 0.083 | −0.134 |
| **OVERALL** | **104** | **0.310** | **0.255** | −0.055 |

**McNemar exact paired test:** 30 discordant pairs (18 regressions, 12 improvements),
**p = 0.3616 → NOT significant**.

Per-item discordance: code 6/6, dependency 1/1, load 7/2, web 4/3.

## Decision

Per `NEXT_PROMPT (1).md` Phase 4a rules:
- p ≥ 0.05 → differences are paired noise → **ship, note it, done**.
- The second rule (load regression with p < 0.05) does not apply.
- The third rule (capability mean < baseline − 0.15 at n ≥ 12) is not triggered:
  load's −0.134 is short of −0.15.

**Conclusion: verdict stands — ship with the note.** On 104 novel held-out snippets both
models are weak and statistically indistinguishable. The 34-item suite's advantage for
sirius-final (0.795 vs 0.753) is not reproduced on this harder, unseen set; the honest
portfolio framing is "improves the fixed SIRIUS baseline; no significant difference on
novel held-out items", not "universal improvement".

## Artifacts
- `eval100_report_qwen2_5_0_5b-instruct-q8_0.json`
- `eval100_report_sirius-final.json`

## Fix applied
`04b_run_eval100.py --host` default was `localhost:11434`; `ollama_post()` requires the
scheme, so every request failed with `unknown url type: localhost` and produced an all-zero
report. Changed default to `http://localhost:11434`; re-ran both models.

## Caveat on dependency_cve
Both models score 0.125 on the 12 novel dependency/CVE items, versus 0.875 on the original
34-item suite. The "restored" dependency score is specific to the original item style;
canonical LABEL strings on unseen CVE phrasings remain a known weakness.
