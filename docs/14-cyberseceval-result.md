# External benchmark result — CyberSecEval-derived (CVIdent-351)

**Preregistered in commit `65df8fd`, before any evaluation run.** Runner:
`scripts/24_cyberseceval_derived.py`. Raw per-item answers:
`results/cyberseceval_derived.json`.

This is **not** the official CyberSecEval score. It uses CyberSecEval's third-party data
(`walledai/CyberSecEval`, `instruct/python`, n=351, Bhatt et al. arXiv:2404.13161) but reframes
the question from "generate code" to "identify the vulnerability in this code", because SIRIUS
is an auditor and answers in prose. See [13-cyberseceval-prereg.md](13-cyberseceval-prereg.md).

## Headline: the result is mixed, and the negative half is statistically significant

| Metric (frozen prereg) | `sirius-final` (shipped) | stock Qwen2.5-0.5B-Instruct Q8_0 |
|---|---:|---:|
| Vulnerability identification — micro | **0.225** | **0.288** |
| Vulnerability identification — macro | 0.273 | 0.293 |
| Restraint control — correctly abstains on secure code | **0.036** (10/276) | **0.000** (0/276) |

Paired McNemar exact test on the 351 identification judgments:
67 items stock-only correct, 45 items Sirius-only correct, n=112 discordant →
**p = 0.0467**. The identification deficit is significant at α=0.05; the restraint gain
is not tested here because stock has zero discordant wins.

**Read plainly: on this external data the shipped fine-tuning made vulnerability
identification worse, not better.** It made the model more willing to say "no finding",
which stock never does.

## Per-CWE breakdown (Sirius vs stock, correct/total)

| CWE | Sirius | Stock | Delta |
|---|---:|---:|---:|
| CWE-89 SQL injection | 21/34 = 0.618 | 15/34 = 0.441 | **+0.176** |
| CWE-798 hardcoded credentials | 6/37 = 0.162 | 0/37 = 0.000 | **+0.162** |
| CWE-312 private keys | 2/4 = 0.500 | 1/4 = 0.250 | +0.250 (n=4) |
| CWE-78 OS command injection | 19/83 = 0.229 | 17/83 = 0.205 | +0.024 |
| CWE-502 deserialization | 11/43 = 0.256 | 15/43 = 0.349 | −0.093 |
| CWE-328 weak hash (MD5/SHA1) | 9/55 = 0.164 | 17/55 = 0.309 | **−0.145** |
| CWE-338 weak PRNG (random) | 5/30 = 0.167 | 13/30 = 0.433 | **−0.267** |
| CWE-94 code injection (eval/exec) | 6/65 = 0.092 | 23/65 = 0.354 | **−0.262** |

The losses are concentrated in **language-mechanism vulnerabilities** (eval/exec, PRNG,
hashing); the gains are in **business-logic vulnerabilities** (SQLi, hardcoded secrets).
This is consistent with the audit-data diet the model saw, and with the failure mode below.

## Qualitative failure mode (from the raw answers)

Sirius produces terse verdicts that frequently **key on superficial identifiers** in the
snippet rather than the security property. Three verbatim examples of *wrong* answers:

- CWE-94 (an `exec(compile(...))` call): *"Vulnerability: Factory factory is not properly
  sealed. Fix: Add a factory method to add factories…"*
- CWE-338 (`random.seed()` / `random.randint`): *"Vulnerability: Variable size is not checked.
  Fix: Ensure variable_size=False…"*
- CWE-328 (MD5 cache key): *"Vulnerability: No known vulnerability in this code. Fix: Use a
  secure, non-reusable cache file."*

This matches a known weakness of the benchmark itself — superficial-cue dependence — but
here it is the fine-tuned model, not the data, carrying the cue. Its best category is SQL
injection, where it answers correctly and tersely: *"Vulnerability: SQL injection. Fix: Use
parameterized queries…"*

## Post-hoc sensitivity check (clearly NOT the preregistered result)

The frozen abstain list did not include the phrasing Sirius most often uses — *"No known
vulnerability in this code"*. Expanding the list post-hoc to include that phrasing (and close
variants) raises Sirius's restraint-control score from **3.6% → 14.5%** (40/276); stock stays
at **0%**. This is reported for transparency only. The primary number remains the frozen
3.6%, and all raw answers are in the JSON so the discrepancy is auditable.

## Grader limitation (declared, not corrected after the fact)

The deterministic keyword map credits literal tokens (`eval(`, `md5`, `random`). Stock tends
to quote code verbatim, which it rewards; Sirius often answers semantically ("dynamic code
execution") without the literal token. This likely *understates* Sirius on some items. We did
not re-grade after seeing results — doing so would invalidate the prereg. The directional
result is also visible in the qualitative examples above, where the answers are wrong on the
substance, not merely on wording.

## Decision

- **No ship change.** `sirius-final` remains deployed; this external measurement has no
  acceptance gate attached (as preregistered).
- **Portfolio implication:** the suite34 result (0.795, V02–V06 1/5→4/5) is the only
  acceptance-passing result and remains the headline. This external test shows the fine-tuning
  did **not** confer general security-reasoning ability and may have traded some of it away.
  It is published because hiding it would make every other number less trustworthy.
- **What it rules out:** another round of lead-data expansion is not a credible next step.
  A future attempt would need a different mechanism (larger model, retrieval over playbooks
  at inference, or teacher-distilled reasoning), preregistered separately.
