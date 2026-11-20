# SIRIUS — Phase-2 Consultation Output
## Three independent proposals, merged by a fourth seat against the telemetry

> Input brief: `SIRIUS_Consultation_Brief.md` (Phase 1.3).
> Ground truth used for every resolution: `SIRIUS_Telemetry_Report.md` / `.json`
> and the measured baseline artifacts in `sirius_reports\`.
> This is a **plan**, not a training result. No model was trained or pruned here.

---

## Part A — How the three seats voted

| Decision | Seat A — Conservative Capacity | Seat B — Data-Centric Remediator | Seat C — Deployment Pragmatist |
|---|---|---|---|
| LoRA | r=8, α=16, 4 modules (`o, gate, up, down`), 3.66 M | r=16, α=32, 5 modules (`q,k,v,o,down`), 4.37 M | r=16, α=32, all 7 modules, 8.80 M |
| `lm_head` | Freeze | Freeze | Freeze |
| Pruning | 0 blocks in pass 1; optional 1 verified block | 0 in acceptance run; ShortGPT bottom-3 as separate experiment | ShortGPT bottom-3, then gated; 0 allowed |
| Dataset | 2,400, replay 31% (600/450/250/350/750) | 4,000 (1800/800/400/600/400) | 4,000 (1400/1000/600/500/500) |
| Quantization | Q6_K (keep Q8_0 gold) | Q6_K | Q5_K_M primary, Q6_K fallback |
| Mislabeling cause | Data (hard negatives, prompt baked in) | Data first, format second, not reward | Data first, prompt-aligned, not reward |
| Expected overall | 0.834 [0.78–0.89] | 0.882 [0.79–0.98] | 0.866 [0.801–0.929] |

**Unanimous agreements (no merge needed):** `lm_head` stays frozen; r=32 is rejected; DPO/reward is rejected; pruning `[2,6,10]` as a blind default is rejected; a ShortGPT importance pass is required before any pruning; perplexity must be *measured* against a Q8_0 reference on wikitext-2 before any gate is meaningful; the exact 34 baseline prompts must be held out of training; the acceptance prompt/options must not change.

---

## Part B — The merged Phase-2 plan (final answer to the brief's 5 questions)

### B0. Binding facts from the telemetry (the tie-breakers)

- **Capacity is not the bottleneck.** `qwen2.5-coder:1.5b` (3× params) reaches only **0.972** quick-overall vs our Q8_0 target's **0.958** → +0.014 headroom. So r=32 is out.
- **Two distinct failure mechanisms.** (i) *Code-vuln mislabeling* is behavioral and output-proximal (V02 hardcoded key → "Buffer Overflow", V06 `verify=False` → "XSS", V05 MD5 → "buffer overflow"), fixable by changing what label the read-out selects. (ii) *Web-config / load-testing* gaps are missing keywords/examples (W06, W07, L06, L08). Both halves of the block must be reachable by the adapter.
- **Knowledge lives in MLP + embedding.** Of Q8_0's +175.8 MB over Q4_K_M, +117.3 MB is MLP and +51.1 MB is embedding; output_head and norms are identical. Q4_K_M scores 0.750 quick vs Q8_0's 0.958. Protect those tensors.
- **Score math:** script 04's `overall_mean` is the **unweighted mean of the four capability means**, so each capability contributes 25% regardless of item count.
- **Memory is not binding:** every quant from Q4_K_M (468.6 MB measured) to Q8_0 (644.4 MB) is far below 8 GB. The binding constraints are ±2% PPL and CVE recall.
- **Correction to the brief:** "~390 MB Q5_K_M" is inconsistent with the measured Q4_K_M = 468.6 MB — Q5_K_M must be *larger*. Treat all size figures as approximate; decide quant by measured fidelity, not MB.

---

### B1. LoRA config — answer to Q1

**Primary: r=16, α=32 (scale 2.0), dropout 0.05, all 7 modules** (`q_proj k_proj v_proj o_proj gate_proj up_proj down_proj`), bf16 adapter. **Freeze `lm_head`.**

Reconciled parameter count (from measured shapes):
- attention: q/o 28,672 each + k/v 16,384 each = **90,112/block**
- MLP: gate/up/down 92,160 each = **276,480/block**
- total **366,592/block × 24 = 8,798,208 params = +1.78% of the 494.03 M body** (+1.40% of 630.17 M stored).

**Why all 7 at r=16 rather than the smaller seats:** the failure spans both mechanisms — attention routing (`q/k/v/o`) governs "what does this code do" for the mislabeling fix, and MLP (`gate/up/down`, 87.7% of each block, holding the +117 MB of knowledge Q8 adds) supplies the missing web-config/CVE keywords. Full coverage is only 8.8 M params (1.78%) and fits T4 easily. r=16 is the *smallest* rank that can displace a high-confidence wrong label; r=32 is rejected by all three seats on the +0.014 ceiling evidence.

**Why `lm_head` frozen (unanimous):** in HF the head is tied to the embedding; the GGUF's "untied 136 M output head" is a llama.cpp conversion artifact (the brief's own telemetry shows the head is Q8_0 in both Q4 and Q8 files). Adapting it adds ~2.45 M params and reshuffles *all* vocabulary logits — pure PPL risk for no gain.

**Gated de-escalation ladder (this resolves A vs B vs C):** if the merged-unpruned candidate breaches the ±2% PPL gate or loses >0.02 on any capability, retrain (do not continue training) at **5 modules (`q,k,v,o,down`), r=16** (Seat B, 4.37 M — freezes 58.5% of the knowledge store); if it still fails, **4 modules (`o,gate,up,down`), r=8** (Seat A, 3.66 M). Never escalate to r=32.

**Training recipe:** QLoRA 4-bit NF4 + double quant, bf16 adapter, **lr 1e-4 cosine → 10%, warmup 3%**, **3 epochs with early stopping** on a held-out dev set (save best), per-device batch 4 × grad-accum 4 = **effective 16**, max_len **512**, `paged_adamw_8bit`, grad clip **0.3**, gradient checkpointing on. ~500–600 steps, well inside free T4 15 GB.

---

### B2. Pruning plan — answer to Q2

**No blind `[2,6,10]`. Pruning is a separate, gated experiment; zero-block pruning is an acceptable outcome.**

1. In pass 1, ship the **merged, unpruned** model. Measure the 34-item baseline and PPL. This is the primary deliverable — Q6_K/Q5_K_M already satisfy the 8 GB constraint, so pruning buys no deployment benefit.
2. **ShortGPT importance pass on Colab:** for each block compute `SI_l = 1 − E[cos(h_in^l, h_out^l)]` over **512 wikitext-2-raw samples (seq 512) + 200 held-out security prompts** (disjoint from the 34 baseline items). Rank blocks **1–22** only; hard-exclude edge blocks **{0, 1, 22, 23}**.
3. Candidate set = the **3 lowest-importance (most near-identity) blocks**, whatever their indices — not [2,6,10] unless the measurement happens to pick them.
4. **Rollback gate:** export at Q8_0 and require `PPL_pruned ≤ 1.02 × PPL_reference` **and** `≤ 1.02 × PPL_merged_unpruned`, and no capability mean drops >0.02 vs baseline. If it fails → try **bottom-1 block** → then **0 blocks**. Discard any failing pruned artifact.

Rationale: all 24 blocks have an identical 14,912,384-param budget, so the toolkit cannot rank them; removing 44.74 M params (−9.06% of body / 12.5% of layers) on an unmeasured guess is the single likeliest way to breach the ±2% gate.

---

### B3. Dataset mix and the mislabeling fix — answer to Q3

**Total 4,000 items** (reject the brief's arbitrary 5,000; 4,000 is where seats B and C converged, with A's corrective-core emphasis folded in):

| Capability | Items | Share | Focus |
|---|---:|---:|---|
| code_vuln | **1,500** | 37.5% | label-correction core + broad OWASP |
| web_config | **1,000** | 25% | W06 stack traces, W07 plain-HTTP admin, headers/cookies |
| load_testing | **600** | 15% | L06 rate-limit/backpressure, L08 upstream saturation/connection-pool |
| dependency_cve | **400** | 10% | D07 abandoned/unmaintained; correct pinning; typosquatting content |
| general replay | **500** | 12.5% | anchor general language / protect PPL |

**Diagnosis: DATA problem first, PROMPT format second, NOT a reward problem** (unanimous). The baseline system prompt already says "name the exact issue," yet the model emits confident wrong labels — a learned mapping error, not an instruction-following failure or preference misalignment. DPO/reward is rejected as disproportionate and PPL-risky on a 0.5 B model.

**code_vuln construction (1,500):**
- **600 label-correction hard core** — 5 archetypes × 40 distinct snippets × 3 prompt forms: (a) plain "name the exact vulnerability," (b) **CoT `FUNCTION → RISK → LABEL`**, (c) **contrastive pairs** (genuine C buffer-overflow snippet labeled "Buffer Overflow" placed beside the hardcoded-key snippet labeled "Hardcoded Credential Exposure") to break the surface-pattern shortcut.
- **400 broad OWASP items** with balanced correct labels (avoid collapse to 5 labels).
- **500 "what does this code do" items** training the intermediate reasoning step.

Targets must contain the **exact grader keyword strings verbatim** in the final `LABEL:` line (e.g. V02: "hardcoded / secret in source"; V06: "TLS / certificate verification disabled → MITM"; V05: both "MD5/weak hash" **and** "bcrypt/argon2/salt" because `min_pass=2`), because the SIRIUS grader is keyword-based. Do not let CoT bury the answer.

**Non-negotiable hygiene:** decontaminate — hold out the exact 34 baseline prompts and near-paraphrases (train on archetypes with *different* snippets); MinHash Jaccard ≥ 0.9 dedup; cap any single (archetype, label) at 250 items; reserve a 100-item label-correction dev set for early stopping. **Train with the exact acceptance system prompt and options** (temperature 0.2, num_predict 240) because the inference prompt cannot change at acceptance.

---

### B4. Final quantization and ±2% verification — answer to Q4

**Ship Q6_K as the deployed GGUF; keep a merged Q8_0 as the gold fidelity reference and Q5_K_M as a measured fallback. Never Q4_K_M.**

Resolution of the A/B (Q6_K) vs C/brief (Q5_K_M) split: memory is not binding, the ±2% PPL gate *is*, and the knowledge/CVE recall lives in the MLP and embedding tensors that low-bit formats degrade. Therefore choose fidelity. Q6_K keeps ~6 bits uniformly; all candidates are ~470–650 MB, trivial on 7.8 GB. Run an A/B of Q6_K vs Q5_K_M and keep Q6_K unless it measurably fails a gate.

**Verification protocol (Phase 2 must add this — the SIRIUS toolkit cannot measure PPL):**
1. **Measure the reference first.** PPL0 = wikitext-2-raw perplexity on the untouched Q8_0 (llama.cpp `perplexity`, ctx 512, identical tokenization). Every later check is relative to this number. Also record domain PPL on 200 security snippets.
2. **Gate every candidate** (merged-unpruned Q8_0 → pruned Q8_0 → Q6_K → Q5_K_M): `PPL ≤ 1.02 × PPL0`, and no capability mean drops >0.02 on the 34-item suite.
3. **CVE recall probe:** re-run scripts 04/05 on each GGUF in Ollama with identical Modelfile system prompt and options; require the 8 dependency_cve items to keep mean ≥ 0.875 − 0.02, plus a 20–30 item held-out CVE/config probe scored with a **content rubric** (the grader is demonstrably foolable — D06 "typosquatting = trademark" and D08 "use `latest` for stability" both scored 1.0 on wrong content).
4. **Mislabeling probe:** the 5 archetypes V02–V06 must yield ≥4 correct canonical labels.
5. **Rollback ladder:** Q6_pruned → Q6_unpruned → Q5_unpruned → Q8_unpruned → original Q8_0 baseline. Never ship a candidate that fails a gate.

---

### B5. Expected gain per capability — answer to Q5

Merged point estimates (between the conservative 0.834 and optimistic 0.882 seats), with **unweighted capability means** as script 04 scores them:

| Capability | Baseline | Expected after | Gain | Confidence band | Reasoning |
|---|---:|---:|---:|---:|---|
| code_vuln | 0.700 | **0.860** | **+0.160** | **0.78 – 0.93** | V02(0), V06(0), V05(0.5) are directly targeted by 600 corrections + 200 contrastive items; fixing those three flips ≈ +0.25 on a 10-item capability. Haircut for high-confidence wrong labels resisting full overwrite and for V03/V04 unmeasured mislabels. |
| web_config | 0.688 | **0.810** | **+0.122** | **0.72 – 0.88** | W06/W07 are missing-knowledge 0.0 items; examples supply the keywords. Bounded because Q8_0 already scores 1.00 on the 3-item quick set — this is a short tail, not a broad deficit. |
| dependency_cve | 0.875 | **0.910** | **+0.035** | **0.875 – 0.95** | Saturated (target, coder, and Q4 default all 1.00 quick; base's matched delta was already +0.667). Only D07 is a real fail; grader false-positives make measured movement unreliable. Main risk is regression, hence only 400 items. |
| load_testing | 0.750 | **0.860** | **+0.110** | **0.78 – 0.93** | L06/L08 are 0.0 keyword-completeness gaps directly targeted. Bounded by the matched instruct−base delta of 0.00 — the behavior is already present, so this is output alignment, not new knowledge. L04's raw mean is already 1.0. |
| **OVERALL** | **0.753** | **0.860** | **+0.107 (+14.2%)** | **0.79 – 0.93** | Unweighted mean of the four capability means. ~1.8 points below the brief's 0.878 — an intentional, telemetry-grounded haircut on dep_cve headroom and quantization drift. |

**Honest confidence:** medium. Direction of the code-vuln fix is high-confidence; magnitude is not. The single largest uncertainty is whether high-confidence mislabels fully overwrite — hence the wide code_vuln band and the V02–V06 probe as an early gate.

---

## Part C — Execution order (what makes it shippable)

1. **Freeze baseline:** full 34-item script 04 on Q8_0 in Ollama → baseline JSON; measure PPL0 on wikitext-2-raw. Do this before any training.
2. **Build data:** 4,000 items, decontaminated, forced `FUNCTION/RISK/LABEL` format, 100-item dev holdout.
3. **Train:** Colab T4, QLoRA 4-bit NF4, r=16 all 7 modules, lr 1e-4, 3 epochs early-stopped, effective batch 16, seq 512.
4. **Merge unpruned → Q8_0 → gate** (PPL ≤1.02×, no cap drop >0.02). Fail → 5-module → 4-module r=8 ladder.
5. **ShortGPT pass → prune bottom-3 in 1–22 → gate** (3 → 1 → 0 rollback).
6. **Quantize Q6_K (Q5_K_M fallback) → gate** (PPL + 34-item + CVE probe + mislabeling probe).
7. **Final acceptance:** identical harness and options, same 34 items. Artifact ladder per B4.

---

## Part D — How each disagreement was resolved against telemetry

1. **r=8 vs r=16 vs all-modules:** kept r=16 and all 7 because the failures span attention (read-out) *and* MLP (knowledge); the +0.014 ceiling only rules out r=32, not coverage. Made smaller configs a **measured fallback**, not a taste call.
2. **Prune 0 vs 3:** merged as "0 in the acceptance run + mandatory ShortGPT pass with a 3→1→0 rollback gate." Memory isn't binding, so pruning must earn its place.
3. **2,400 vs 4,000 vs 5,000 items:** 4,000 — enough for a two-mechanism fix, avoids the arbitrary 5,000; skew to code_vuln (highest leverage) and cut dep_cve (saturated, grader-noisy); replay set at 12.5% to protect PPL.
4. **Q5_K_M vs Q6_K:** Q6_K primary because memory is not binding and the PPL/CVE gate is; Q5_K_M stays a measured fallback. Flagged the brief's inconsistent ~390 MB figure.
5. **0.834 vs 0.882 vs 0.866:** settle at **0.860** with capability-specific bands, haircut on dep_cve (grader-noise + saturation) and web_config (quick-set ceiling).
6. **Perplexity:** no one supplied a reference value; made measuring PPL0 the **first** execution step and every other number relative to it.

**Final one-line verdict:** r=16 / all-7 LoRA (8.80 M), **no blind pruning** (ShortGPT-gated, 0 allowed), 4,000-item decontaminated label-correction dataset, **Q6_K** deployment with measured Q5_K_M fallback, expected overall **0.753 → 0.860 (+14.2%)** — and ship nothing until PPL ≤ +2% and the 34-item gate both pass.
