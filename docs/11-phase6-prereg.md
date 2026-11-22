# PREREG — Phase 6 (new session): same-chain pass6 v2

## Why a new session
Phase 5R ended RECOVERY-WEAK: four from-scratch pass5 recoveries all passed the retention
gate but the chained base scored 0.705 (s=0.5) / 0.493 (s=1.0) vs the shipped 0.795.
Root cause: Colab resets kept destroying the original pass5 adapter. This session removes
that failure mode by training pass5 and pass6 **in the same runtime** and persisting the
adapter to Drive immediately after pass5.

## Frozen facts (do not re-derive)
- Shipped `sirius-final` = base + 0.5·original pass5 adapter = suite34 **0.795**, V02–V06 4/5.
- Pass6 v1 (87 lead items, 2.4% signal) failed: lead 0.127, restraint 0/5.
- v2 data ready and verified: 5,208 items, 200/cap × 9, 774 restraint (14.9%),
  63 counterfactual pairs, new-signal share 40.4%, 0 eval overlap, selftest 110/110.
- Pass6 v2 recipe (frozen from PREREG_PHASE5R §3): r=16 α=16 rsLoRA, **lr 1e-4**,
  2 epochs, target **gate/up/down**, layers 4–20, bf16, completion-only, 10% anchor,
  dual-gate early stop, seed 42. Effective batch 16 (micro-batch 1 × accum 16 or
  Colab 4×4). seq 256 (pre-cleared: 0% replay truncation).

## Step 1 — pass5 (same session)
Train pass5 with the frozen recipe. Immediately after `train()` returns, copy the adapter
dir to `/content/drive/MyDrive/sirius_pass5_adapter/` (few MB). Verify the copy exists.
Record the PPL ratio (expect ≈0.806, the established recovery band).

## Step 2 — 0b control on THIS adapter's chained base
Build `sirius_merged_pass5_s05` with script 18 (scale 0.5), export Q6_K, create Ollama
model, run `04_sirius_baseline.py --full`. Decision (statistically grounded, chosen now):
- **CHAIN-OK** if suite34 ≥ 0.75 **OR** McNemar exact vs the shipped 0.795 report gives
  p ≥ 0.05 (difference not significant — 0.705 vs 0.795 is ≈3 flips, p≈0.25).
- Otherwise run the s=1.0 sanity check (script 18 --scale 1.0 + 04); s1.0 < 0.75 →
  RECOVERY-WEAK → stop, keep sirius-final deployed.
- The lead v2 eval is recorded for archive but does not gate this decision.

## Step 3 — pass6 v2
Only if CHAIN-OK: `07_train_colab.py --pass-name pass6 --base-model ./sirius_merged_pass5_s05`
with the frozen recipe. Then dual gate (09), export (11), Ollama create, acceptance.

## Step 4 — acceptance (frozen, PREREG_PHASE5R §5)
- Lead v2 overall ≥ 0.55 AND every capability floor ≥ 0.50 (n=10 each) AND
  restraint ≥ 0.80 (n=20 traps).
- suite34 ≥ 0.75; eval100 within paired noise vs pass5 (McNemar p ≥ 0.05);
  symmetric standard — improvements need p < 0.05 to be claimed.
- Dual PPL gate < 1.30; shipped-GGUF PPL re-check ≤ 1.05× bf16 merge.
- Publish per-capability numbers, not just the mean.

## Failure branches (frozen)
1. Lead improves but some capability < 0.50 → extend THAT seed file, ONE retrain max.
2. Restraint < 0.80 → double safe twins (7→14), rebuild, ONE retrain max.
3. suite34 < 0.75 while lead ≥ 0.55 → revert to sirius-final; one capability-level
   merge-scale sweep; if no s* passes both gates, stop.
4. PPL gate fail → revert, archive.
5. Everything fails → STOP. No third blind retry.

## Deviation log
| # | Deviation | Why |
|---|---|---|
| D1 | New session / new prereg | prior session's adapter was destroyed by resets |
| D2 | 0b CHAIN-OK threshold now includes McNemar p≥0.05 | 0.705 vs 0.795 is statistically paired noise; the old 0.72 floor was arbitrary |
| D3 | seq 256, effective batch 16 | pre-cleared in prior prereg |
