# SIRIUS — Phase 2 Execution Runbook (v2)

**Goal:** fine-tune Qwen2.5-0.5B-Instruct into a local, CPU-only
security-auditing assistant, lifting the SIRIUS baseline from **0.753 →
0.860 (+14.2%)**, measured by the same 34-item suite.

**Plan source:** `SIRIUS_Phase2_Consultation_Output.md` (the original
merged plan) + this v2 runbook (the **post-mortem + three-reviewer
briefings** layer added after Pass 1 collapsed).

---

## What changed in this v2 runbook

Pass 1 of the original plan ran and **collapsed catastrophically**:

```
Train loss 3.60 → 0.09; eval loss 0.122 at epoch 3
PPL0 = 306.4 → PPL after = 2575.7 = +740.64%  →  GATE FAILED
```

Three independent reviewers (Beam, VL, anonymous) supplied a second wave
of levers. This runbook is the synthesized v2: Pass 1 is preserved as
historical, Pass 2 was running at briefing time, **Pass 3 is the new
primary**, and a new script `09_eval_gate.py` adds the inference-time
adapter scaling sweep (the free "retention dial" that can rescue a
"failed" run without retraining).

| | v1 plan (original) | v2 runbook (this doc) |
|---|---|---|
| PPL gate metric | ±2% on security dev loss | dual: security loss + general wikitext PPL |
| PPL gate threshold | ±2% (too strict) | PPL/PPL0 < 1.30 (+0.26 nats) |
| PPL unit | percent | **nats** (percentages lie) |
| Quantization | 4-bit NF4 | **bf16** for training (0.5B doesn't need 4-bit) |
| LoRA modules | all 7 | 4 (attention only) |
| LoRA layers | all 24 | 4–20 (skip first/last 2) |
| r / alpha | 16 / 32 (α=2r) | 8 / 8 (α=r, 1× effective LR) |
| rsLoRA | no | yes |
| Loss masking | none | completion-only (-100 on prompt) |
| Anchor data | none | 10% wikitext, interleaved per-batch |
| Inference dial | none | adapter scaling s∈{1,0.5,0.25} |
| Early stopping metric | eval_loss (security) | eval_general_ppl (general) |
| New script | — | `09_eval_gate.py` (dual gate + scaling sweep) |

The four biggest levers, in priority order (per the three briefings):

1. **lr=3e-5 + 1 epoch + cosine + warmup 5%** — Pass 1's lr=1e-4 was full-finetune territory on a 0.5B.
2. **bf16 instead of 4-bit** — quant noise compounds forgetting on small models; 0.5B fits in bf16 on T4.
3. **Attention-only + layers 4–20 + r=8/α=8** — keep an untouched knowledge path; α=2r was silently 2× effective LR.
4. **10% wikitext anchor + dual eval gate** — the single highest-ROI forgetting brake, with the gate measured on a held-out general distribution.

---

## The pipeline at a glance (v2)

```
  [local]  04_sirius_baseline.py  →  baseline 0.753  (DONE)
           06_build_dataset.py    →  sirius_train.jsonl + sirius_dev.jsonl  (DONE)
                 │
                 ▼  upload to Colab
  [Colab]  07_train_colab.py --pass-name pass3
                 │  bf16, attention-only, layers 4-20, r=8/alpha=8,
                 │  lr 3e-5, cosine+warmup 5%, 1 epoch, completion-only loss,
                 │  10% wikitext anchor interleaved, dual eval + early-stop
                 │  on general PPL
                 │  GATE: PPL/PPL0 < 1.30 (+0.26 nats) on wikitext TEST
                 ▼
  [Colab]  09_eval_gate.py --merged ./sirius_merged_pass3 --adapter ./sirius_lora_adapter_pass3
                 │  Dual gate confirmation + adapter scaling sweep s∈{1,0.5,0.25}
                 │  Traces the task-vs-retention Pareto frontier for FREE.
                 │  Pick the lowest s that passes both gates.
                 ▼  pass (at some s)
  [Colab]  08_prune_quantize_colab.py --merged-dir ./sirius_merged_pass3
                 │  ShortGPT pass → drop bottom-3 → gate (3→1→0 rollback)
                 │  Quantize Q6_K (Q5_K_M fallback) → GGUF
                 ▼  download GGUF
  [local]  ollama create sirius-final -f Modelfile.sirius
           04_sirius_baseline.py --model sirius-final
                 │  GATE: each capability ≥ baseline − 0.02
                 │        V02–V06 mislabeling fixed
                 ▼  pass
           SHIP: sirius_final_Q6_K.gguf
```

If Pass 3 fails the gate at s=1.0 but passes at s=0.5 or s=0.25, **use
that s and skip retraining** — that is the entire point of script 09.

---

## Pass 1 post-mortem (the failure we are fixing)

### The numbers

```
PPL0  = 306.4   (on ChatML-formatted security dev items)
PPL_after = 2575.7   (+740%)
```

### Reframe: percentages lie (Beam)

Convert to log-loss (the quantity that actually drives training):

```
ln(306.4)   = 5.72 nats
ln(2575.7)  = 7.85 nats
Δ           = +2.13 nats
```

"+740%" looks apocalyptic, but in the natural unit it is a +2.1 nats
shift. Still severe, but a modest intervention (lower lr + a little
replay) should claw most of it back. **Calibrate the success bar:**
the v2 gate target is `PPL/PPL0 < 1.30` ≈ `+0.26 nats`, not "back to 306."

### What was PPL0=306 measured on? (Beam's key question)

A 0.5B model on raw wikitext sits around **20–40**. PPL0=306 implies a
hard/specialized eval — in our case, **ChatML-formatted security dev
items** (the v1 script measured PPL on the security dev set). That
distribution is narrow and noisy.

**v2 fix:** the gate now measures general PPL on `wikitext-2-raw-v1`
TEST split (raw text, no chat template), which matches the anchor data
distribution. This is the signal that actually tells you whether the
base LM was destroyed.

### Root cause (priority order)

1. **lr=1e-4 too hot** — full-fine-tune territory on a 0.5B. QLoRA safe band is 2e-5 to 5e-5.
2. **3 epochs** — 5K narrow items saturate in ~1 epoch at r=8–16.
3. **7 modules full LoRA coverage** — no untouched path through the network.
4. **alpha=2r** — Pass 1 had alpha=32 at r=16, so `α/r=2` was silently running 2× effective LR on every layer.
5. **No anchor data** — nothing held the base distribution during update.
6. **4-bit NF4 quant noise** — compounds forgetting on small models.
7. **No completion-only masking** — model also memorized the prompt format, causing extra representation drift.

The module-shrink (Pass 1 → 2 → 3) addresses #3 only. **lr, epochs,
alpha, anchor, quant, masking** are the bigger levers, and they are all
in the v2 Pass 3 config.

---

## Step-by-step (v2)

### Step 0 — Freeze the baseline (already done)

```bash
python 04_sirius_baseline.py --model qwen2.5:0.5b-instruct-q8_0
```
Expected overall: **0.753**.

### Step 1 — Build the dataset (already done)

```bash
python 06_build_dataset.py
```
Outputs `sirius_train.jsonl` (2,978 items) + `sirius_dev.jsonl` (100).

### Step 2 — Upload to Colab and run Pass 3

1. Open a **Colab T4 runtime**.
2. Upload `sirius_train.jsonl`, `sirius_dev.jsonl`, and `07_train_colab.py`.
3. Run the install cell the script prints:
   ```python
   !pip install -U transformers==4.46.0 peft==0.13.0 bitsandbytes==0.44.1 \
       datasets==3.1.0 accelerate==1.1.1 trl==0.12.0
   ```
4. Run Pass 3:
   ```python
   !python 07_train_colab.py --pass-name pass3 --skip-install-check
   ```
5. **Watch the dual gate.** The script prints:
   ```
   PPL0 (base, pre-training, wikitext test):  X.XXXX
        ln(PPL0) = Y.YYYY nats
        Gate target: PPL_after / PPL0 < 1.30 (i.e. Δln(PPL) < +0.262 nats)
   ...
   PPL after training:  Z.ZZZZ
   PPL ratio:  R.RRRR  (gate: < 1.30)
   Δln(PPL):   +N.NNNN nats
   ```

   The v2 gate **passes** if `PPL ratio < 1.30`. If it passes, download
   `./sirius_merged_pass3/` and `./sirius_lora_adapter_pass3/` and go to Step 3.

   If it **fails**, do NOT immediately retrain. Go to **Step 2b**.

### Step 2b — Dual-gate + adapter scaling sweep (run BEFORE retraining)

```python
!python 09_eval_gate.py --merged ./sirius_merged_pass3 \
                       --adapter ./sirius_lora_adapter_pass3 \
                       --tag pass3
```

This sweeps the LoRA scaling factor `s ∈ {1.0, 0.5, 0.25}`:

```
ΔW_eff = s · (alpha/r) · B A
```

At `s=0.5` the effective adapter delta is halved; at `s=0.25` it is
quartered. **This is free** — no retraining. The script reports which
`s` values pass BOTH gates:

- **security_loss < train_loss × 1.20** (the task fit is still good)
- **general_ppl_ratio < 1.30** (the base distribution is preserved)

It also reports advisory metrics: `KL(base‖tuned)` and token-level
top-1 accuracy on general text.

If any `s` passes: note the chosen `s`, proceed to Step 3 with the
merged model. (See "Serving at s < 1.0" below.)

If no `s` passes: **now** you retrain. Go to **Step 2c**.

### Step 2c — Escalation ladder (only if 2b fails at every s)

| Step | Change | Expected Δnats |
|---|---|---|
| **3b** | `anchor_ratio=0.20`, keep r=8, lr=3e-5, 1 epoch | −0.10 |
| **3c** | r=4, alpha=4, lr=2e-5, 1 epoch, 10% anchor | −0.15 |
| **3d** | r=64, alpha=16 (α/r=0.25), lr=1e-5, attention only | −0.20 |
| **3e** | partial unfreeze last 4 layers + LoRA elsewhere, lr=5e-6 | −0.25 |
| **4** | replay training (5K synthetic from base, 50/50 mix) | −0.35 |

Steps 3b–3d are config edits — pass the overrides inline, e.g.:

```python
# Edit PASSES[2] in 07_train_colab.py before running, or add a new pass:
!python 07_train_colab.py --pass-name pass3c  # after editing PASSES
```

Step 4 (synthetic replay) requires generating 5K security items from the
base model and mixing 50/50 with the real training set. This is the
heaviest intervention; only do it if 3b–3e all fail.

### Optional — 6-point grid (only if Pass 3 fails and you want clean ablation)

```python
!python 07_train_colab.py --grid --skip-install-check
```

Sweeps `lr ∈ {5e-5, 3e-5, 1e-5} × epochs ∈ {1, 2}` with all other Pass 3
settings held fixed. ~10 min × 6 = ~1h on T4. This isolates the lr/epoch
levers from the capacity levers (Beam's "you're changing too much at
once" point). Pick the lowest lr / fewest epochs config that passes.

### Serving at s < 1.0

If script 09 chose `s=0.5` or `s=0.25`, the merged model on disk is
still at `s=1.0`. To honor the chosen `s`:

- **Easiest:** serve base + adapter with PEFT at runtime (not via Ollama).
  Set `lora_alpha *= s` on every adapter layer before load.
- **Ollama path:** re-merge at the chosen `s`. Load base + adapter, scale
  `lora_alpha`, `merge_and_unload()`, save, then run script 08.

The runbook does NOT auto-apply this; pick one path and note it in the
train log.

### Step 3 — Prune + Quantize (still on Colab)

```python
!python 08_prune_quantize_colab.py --merged-dir ./sirius_merged_pass3
```

What it does (Part B2 + B4):
1. **ShortGPT importance pass** — `SI_l = 1 − E[cos(h_in, h_out)]` for each
   of the 24 blocks over 512 wikitext-2-raw samples. Ranks blocks
   **1–22** only (hard-excludes edges {0,1,22,23}).
2. **Drop bottom-3** (most near-identity). Gate:
   `PPL_pruned ≤ 1.02 × PPL0` AND `PPL_pruned ≤ 1.02 × PPL_merged_unpruned`.
   - Fail → try bottom-1 → then 0 blocks. Zero-block pruning is acceptable.
3. **Quantize** to Q6_K (primary) and Q5_K_M (fallback). Both exported as GGUF.
4. Writes `Modelfile.sirius` for Ollama.

If the chosen `s < 1.0`, the script prints a warning — the merged model
on disk is at `s=1.0`. Re-merge via the cool-down path before running
this step, or accept `s=1.0` for the pruned/quantized version.

### Step 4 — Accept locally

```bash
ollama create sirius-final -f Modelfile.sirius
python 04_sirius_baseline.py --model sirius-final
```

**Acceptance gate (Part B4):**
- Each capability mean ≥ baseline − 0.02
- **Mislabeling probe:** V02 → "hardcoded/secret", V06 → "TLS/MITM",
  V05 → "weak hash/salt". At least 4 of 5 V02–V06 must yield the
  canonical label.
- **CVE recall:** the 8 dependency_cve items must keep mean ≥ 0.855.

If the gate passes: **ship `sirius_final_Q6_K.gguf`**. If Q6_K fails
but Q5_K_M passes, ship Q5_K_M. If both fail, the cool-down path below
is cheaper than retraining:

### Cool-down path (only if Q6_K fails capability gate)

Per the second reviewer's Tier-3 suggestion: a 1-epoch cool-down on
wikitext at lr=1e-6, r=4, attention-only, often recovers general
fluency without losing the security gain. Edit `07_train_colab.py` to
add a `pass_cooldown` config and run on the merged model:

```python
# Pseudo-config (add to PASSES list):
dict(name="pass_cooldown", r=4, alpha=4, dropout=0.05, use_rslora=True,
     target_modules=["q_proj","k_proj","v_proj","o_proj"],
     layers_to_transform=list(range(4,20)),
     quantize_4bit=False, lr=1e-6, epochs=1, warmup_ratio=0.05,
     lr_scheduler="cosine", max_grad_norm=0.5, weight_decay=0.01,
     label_smoothing=0.1, completion_only_loss=True, anchor_ratio=1.0,
     per_device_train_batch_size=4, gradient_accumulation_steps=4,
     early_stopping_patience=2, eval_metric="eval_general_ppl",
     greater_is_better=False, note="COOL-DOWN: gentle anchor to base")
```

Load `./sirius_merged_pass3` as the base, attach the cool-down adapter,
train 1 epoch on wikitext only, merge, re-quantize, re-run script 04.

---

## Pass 4 — capability gate failure (Post-Pass-3 escalation)

Pass 3 of the v2 plan ran and **passed the dual PPL gate perfectly**
(general wikitext PPL within budget, security loss fine, knowledge
preserved). But the local 34-item capability gate FAILED:

```
sirius-final (Q6_K, Pass 3):  overall 0.689  vs baseline 0.753
  code_vuln:   0.700 → 0.350   (collapsed — V02/V05/V06 still "buffer overflow")
  web_config:  0.688 → 0.844   (improved — no competing prior)
  dependency:  0.875 → ~same
  load:        0.750 → 0.688   (mild regression)
```

The V02–V06 mislabeling probe still fails on ~4 of 5: hardcoded
secrets, `verify=False`, and `md5` still get labeled "buffer overflow".

### Diagnosis

**Pass 3 was under-fit, not over-fit.** The dual gate confirmed
knowledge was preserved (the +0.26-nat budget held), so the forgetting
brake worked. The failure is the opposite problem: the adapter was
**too weak** to override the base model's strong "buffer overflow" prior
on 3 specific archetypes.

Three root causes, in priority order:

1. **r=8 attention-only is capacity-starved for label rewriting.**
   r=8 / α=8 / 4 modules / layers 4-20 ≈ 1.2M trainable params. That is
   enough to *shift* the distribution (web_config +0.156) but not to
   *overwrite* a strong pretrained prior on specific tokens. Label
   rewriting needs more capacity in the MLP path (down_proj), because
   the token "buffer" → "hardcoded" swap is an MLP-level decision.

2. **1 epoch early-stopped on general PPL before code_vuln converged.**
   The Pass 3 early-stop watched `eval_general_ppl` with patience=2.
   General PPL plateaued at ~step 60; the stop fired there. But
   code_vuln loss was still descending — the model needed ~2 epochs to
   internalize the canonical labels. The stop was correct for the
   *retention* signal but premature for the *task* signal.

3. **label_smoothing=0.1 diluted the canonical labels.** Pass 3 added
   smoothing as a forgetting brake. But the canonical answers are
   sharp keyword strings ("hardcoded, secret in source") that the
   grader matches exactly. Smoothing 0.1 softened the very signal we
   were trying to amplify. The model was confidently wrong, not
   hedging — smoothing was solving a problem we didn't have.

### Step 2d — Free upward sweep FIRST (5 min, no retraining)

Before retraining, sweep the Pass 3 adapter UPWARD:

```python
!python 09_eval_gate.py --merged ./sirius_merged_pass3 \
                       --adapter ./sirius_lora_adapter_pass3 \
                       --tag pass3 \
                       --scales "2.0,1.5,1.0,0.5"
```

The default sweep (1.0, 0.5, 0.25) is a *retention* dial — for an
OVER-fit run. Pass 3 is the opposite — UNDER-fit. Sweeping UPWARD
(s=2.0, 1.5) amplifies the (already-good) adapter delta for free. If
s=2.0 brings code_vuln back without breaking the general PPL gate,
you've fixed the mislabeling in 5 minutes and you're done.

**Likely outcome:** s=2.0 amplifies both the good (web_config) and the
bad (still no override on "buffer overflow" prior — capacity is the
bottleneck, not scaling). My prior: ~25% this works, ~75% you need
Pass 4. Worth the 5 minutes regardless.

### Step 2e — Pass 4 (the actual fix)

Pass 4 adds capacity, runs longer, removes label smoothing, and adds
explicit contrastive data on the 3 problem archetypes.

**Local (data prep):**

```bash
python 06b_build_contrastive.py --factor 3
```

Produces `sirius_train_contrastive.jsonl` (33 items: 9 each of
hardcoded_secret / tls_verify_disabled / weak_hash + 6 real
buffer-overflow items as counter-examples so the model learns the
*boundary*, not just that "buffer overflow" is wrong).

Upload `sirius_train.jsonl`, `sirius_dev.jsonl`,
`sirius_train_contrastive.jsonl`, and the updated scripts to Colab.

**Colab (train):**

```python
!python 07_train_colab.py --pass-name pass4 --skip-install-check
```

Pass 4 config (auto-applied):

| Lever | Pass 3 | Pass 4 | Why |
|---|---|---|---|
| Modules | q,k,v,o | q,k,v,o,**down** | +down_proj for MLP-level label rewrite |
| r / alpha | 8 / 8 | **16 / 16** | 2× capacity (still α/r=1) |
| Epochs | 1 | **2** | Let code_vuln converge |
| Early stop | patience 2 on gen PPL | **composite: BOTH gen PPL AND sec loss must plateau** | Don't stop while task is still improving |
| min_delta | default (0) | **0.005** | 0.5% loss improvement counts as progress |
| label_smoothing | 0.1 | **0.0** | Don't dilute the canonical labels |
| Contrastive data | — | **33 explicit pairs** (auto-loaded from 06b output) | NOT-buffer-overflow boundary learning |

**After training, re-run the dual gate:**

```python
!python 09_eval_gate.py --merged ./sirius_merged_pass4 \
                       --adapter ./sirius_lora_adapter_pass4 \
                       --tag pass4
```

Pass 4 will likely land at the *high* end of the general PPL budget
(~1.25× PPL0) — that's fine, the budget is 1.30. If it breaches 1.30,
the composite early-stop should have caught it; if not, re-run with
`--scales "0.75,1.0"` to dial back slightly.

**Then prune + quantize + accept as usual:**

```python
!python 08_prune_quantize_colab.py --merged-dir ./sirius_merged_pass4
# download sirius_final_Q6_K.gguf + Modelfile.sirius
# local:
ollama create sirius-final -f Modelfile.sirius
python 04_sirius_baseline.py --model sirius-final
```

### Pass 4 expected outcome

| Capability | Pass 3 result | Pass 4 expected | Why |
|---|---:|---:|---|
| code_vuln | 0.350 | **0.820** | Contrastive pairs + down_proj + 2 epochs directly target V02/V05/V06 |
| web_config | 0.844 | 0.844 | No regression expected (already passing) |
| dependency | ~0.875 | ~0.875 | Unchanged |
| load | 0.688 | ~0.750 | More capacity restores the small regression |
| **OVERALL** | 0.689 | **~0.830** | Within acceptance gate |

### If Pass 4 still fails the capability gate

Two escalation paths, in order:

1. **Cool-down then re-accept.** If Pass 4 passes the dual gate but
   fails capability, run the cool-down path (1 epoch wikitext at
   lr=1e-6, r=4) to recover any lost fluency, then re-accept. Sometimes
   the cool-down itself sharpens the label boundary.

2. **Synthetic replay (Step 4 of the escalation ladder).** Generate 5K
   security items from the base model itself (self-distillation), mix
   50/50 with the real training set, retrain. This is the heaviest
   intervention; only if 1) and Pass 4 both fail.

---

## Pass 5 — LABEL-first data + MLP path + partial unfreeze (current plan)

**Trigger:** Pass 3d (r=64 attention-only, 2 epochs) passed the dual PPL
gate (0.9899) but failed acceptance: code_vuln 0.550, V02–V06 ~1/5.
Rank is NOT the bottleneck (8× capacity moved code_vuln +0.20). The
training signal is. Also: the 34-item eval has ±0.3 CI at n=8–10 — treat
single-capability deltas < ±0.25 as noise.

**Three levers, all staged in the kit:**

| Lever | What | Where |
|---|---|---|
| Data signal | LABEL-first rewrite (class = first line, highest-margin tokens) + original security corpus (structurally diverse snippets, matched safe hard negatives) + failing-archetype oversample ×3. 3358 items, 100% LABEL-first. | `12_build_corpus_data.py` → `sirius_train_pass5.jsonl`; corpus at `../sirius-security-corpus/` |
| Model path | +down_proj (label swaps are MLP-level) at r=16 α=16 rsLoRA, layers 4-20 | `07_train_colab.py` pass5 |
| Gradient path | Last 2 blocks unfrozen at lr 1e-6 (adapter stays 3e-5, `SplitLRTrainer`), composite early-stop | `07_train_colab.py` pass5 |

**Order — diagnose FIRST, free:**

```bash
python 13_dump_raw_outputs.py --model sirius-final --alt-num-predict 64
```

Classifies each of the 34 failures as WRONG_LABEL / TRUNCATED_SUSPECT /
GRADER_MISS / HEDGE / PASS. If truncation dominates on V03/V04/V06, part of
the "label habit" is a decoding artifact (re-run 04 with `--num-predict 96`);
if GRADER_MISS appears, fix 04's keyword groups before retraining.

**Then train:** `!python 07_train_colab.py --pass-name pass5` in Colab
(upload `sirius_train_pass5.jsonl` + `sirius_dev.jsonl` + `07`). Must see in
the log: `Unfroze last 2 base layers`, `[SplitLR] base_lr=1e-6`,
`Data: using sirius_train_pass5.jsonl — 3358 LABEL-first items`.

**Then:** 09 dual gate with `--scales "1.5,1.0,0.75,0.5"` → 08 export →
`ollama create sirius-pass5` → 04 full → re-dump raws. Full decision rules
and escalation if code_vuln still < 0.680: see `NEXT_PROMPT.md`.

---

## Pass 3 configuration (copy-paste reference)

| Lever | Value | Why |
|---|---|---|
| Quantization | bf16 (no 4-bit) | 0.5B doesn't need 4-bit; quant noise compounds forgetting |
| Modules | q_proj, k_proj, v_proj, o_proj | Attention only; MLP holds more factual knowledge |
| Layers | 4–20 (skip first/last 2) | Bottom = token/position priors; top = task heads |
| r | 8 | Smaller perturbation footprint |
| alpha | 8 | α/r = 1 (Pass 1's α=2r was silently 2× effective LR) |
| use_rslora | True | Rank-stabilized scaling |
| LoRA dropout | 0.05 | Breaks co-adaptation |
| lr | 3e-5 | QLoRA safe band on 0.5B |
| Epochs | 1 | 5K items saturate in 1 epoch |
| Warmup | 0.05 | Avoid early shock |
| LR schedule | cosine (full decay) | Smooth decay reduces end-of-training overshoot |
| Grad clip | 0.5 | Tighter than default; narrow data → spiky grads |
| Weight decay | 0.01 | ≈ L2-SP on adapters toward base |
| Label smoothing | 0.1 | Softens overconfidence on narrow distribution |
| Loss masking | completion-only (-100 on prompt) | Don't memorize prompt format |
| Anchor | 10% wikitext, interleaved | Distribution match = strongest anchor |
| Eval metric | eval_general_ppl (wikitext) | Catch forgetting before security loss saturates |
| Early stop patience | 2 | Stop if general PPL degrades for 2 eval steps |
| Seed | 42 | Run 2 seeds before declaring failure; ±10–15% wobble |

---

## Hard constraints (non-negotiable)

| Constraint | Value | Enforced by |
|---|---|---|
| Target deployment | 8 GB-RAM CPU laptop, Ollama | Modelfile + Q6_K size |
| Training env | Colab T4 free tier, 15 GB VRAM | bf16 (Pass 3) fits easily; 4-bit was only needed for 7B+ |
| LoRA rank | ≤ 16 (never 32) | Pass 3 uses r=8 |
| LoRA modules | Attention only (q,k,v,o) | `PASSES[2]` |
| LoRA layers | 4–20 only | `layers_to_transform` |
| `lm_head` | Frozen (unanimous) | not in target_modules |
| General PPL gate | PPL/PPL0 < 1.30 (+0.26 nats) | `09_eval_gate.py` |
| Security loss gate | < train_loss × 1.20 | `09_eval_gate.py` |
| Pruning | ShortGPT-gated, 0 allowed | `08_prune_quantize_colab.py` |
| Quantization | Q6_K primary, Q5_K_M fallback, never Q4_K_M | `08` export loop |
| Baseline prompts | Held out of training (decontamination) | `06` |
| System prompt | Identical at train and accept time | `06` uses `04`'s exact SYSTEM_PROMPT |

---

## Expected outcome (Part B5, unchanged)

| Capability | Baseline | Expected | Gain | Confidence |
|---|---:|---:|---:|---|
| code_vuln | 0.700 | 0.860 | +0.160 | medium-high |
| web_config | 0.688 | 0.810 | +0.122 | medium |
| dependency_cve | 0.875 | 0.910 | +0.035 | low |
| load_testing | 0.750 | 0.860 | +0.110 | medium |
| **OVERALL** | **0.753** | **0.860** | **+0.107 (+14.2%)** | medium |

The capability targets are unchanged from the original plan. What
changed is the **path** to get there: Pass 3 trades a stricter
forgetting budget for a tighter task fit, and the dual gate catches
failure modes the v1 single-metric gate could not.

---

## Files in this toolkit (Phase 2 v2)

| Script | Runs on | Purpose |
|---|---|---|
| `06_build_dataset.py` | local | Generate 4000-item decontaminated dataset |
| `07_train_colab.py` | Colab T4 | bf16 LoRA training, dual eval, de-escalation ladder, 6-point grid |
| `08_prune_quantize_colab.py` | Colab T4 | ShortGPT prune + Q6_K/Q5_K_M quantize + GGUF export |
| `09_eval_gate.py` | Colab T4 | **NEW.** Dual-gate confirmation + adapter scaling sweep |
| `sirius_train.jsonl` | — | Training data (2,978 items) |
| `sirius_dev.jsonl` | — | Dev holdout (100 items) |
| `sirius_dataset_manifest.json` | — | Provenance + grader coverage |

Plus the Phase 1 artifacts still in use:
- `04_sirius_baseline.py` — the acceptance gate (L04 bug fixed)
- `SIRIUS_Phase2_Consultation_Output.md` — the original plan
- `SIRIUS_Consultation_Brief.md/.pdf` — the brief that produced the plan

---

## If something goes wrong

| Symptom | Diagnosis | Fix |
|---|---|---|
| Pass 3 fails PPL gate at s=1.0 | LoRA still overshooting | Run `09_eval_gate.py`; check s=0.5 / s=0.25 |
| Pass 3 fails at every s | lr or epoch still too high | Run `--grid`; pick lowest lr/fewest epochs that passes |
| General PPL wobbles ±15% | Seed variance on 0.5B | Run 2 seeds (script 07 `--seed`); declare pass only if both pass |
| Adapter scaling doesn't change PPL | PEFT version doesn't honor runtime `lora_alpha` edits | Re-merge adapter at chosen `s` (see "Serving at s<1.0") |
| ShortGPT gate fails at 0 blocks | Merged model is already PPL-marginal | Ship merged-unpruned Q8_0; skip pruning |
| Q6_K fails capability gate | Quantization degraded MLP knowledge | Cool-down path (1 epoch wikitext, lr=1e-6, r=4); or fall back to Q5_K_M |
| V02 still says "buffer overflow" | Mislabel not overwritten | Increase code_vuln hard-core from 600 to 1000 items; add contrastive pairs |
| Dep_cve drops below 0.855 | Over-training regression | Reduce dep_cve items; verify general anchor is protecting PPL |

---

## What this runbook does NOT do

- **Does not run the training.** That happens on Colab; this sandbox has no
  T4. The scripts are ready to paste.
- **Does not auto-apply the chosen adapter scale s.** If `09_eval_gate.py`
  picks s < 1.0, you must re-merge (or serve with PEFT). The runbook
  explains both paths but does not perform the surgery.
- **Does not measure perplexity on the security dev set as the primary
  gate.** The v1 ±2% gate on security dev loss was the wrong signal —
  it measured task overfit, not retention. The v2 gate measures general
  wikitext PPL (retention) AND security loss (task fit), and only passes
  if both are within budget.
- **Does not decide Q5_K_M vs Q6_K a priori.** Both are exported by
  script 08 and the local 34-item run picks the winner.
