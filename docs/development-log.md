# SIRIUS Phase 2 — COMPLETE NEXT-SESSION HANDOFF

> Written when the session was stopped mid-Pass-5. This is the single source of
> truth for where we were, what is broken, and exactly how to resume.
> All paths local unless marked **Colab**.

---

## 1. Overall result so far (do not re-derive)

**The model has never passed the final 34-item acceptance gate.** Every attempt improved
one thing while breaking another. Retention (perplexity) is SOLVED; task fit on the
V02–V06 label habit is NOT.

| Pass | Config | PPL gate | Dual gate | 34-item acceptance |
|---|---|---|---|---|
| 1 | all-7, r16, α32, 4-bit, lr1e-4, 3ep | FAIL +740% | — | not run |
| 2 | 5 mod, r16, α32, 4-bit, lr1e-4, 3ep | FAIL +943% | — | rescued at s=0.5 in gate only |
| 3-old | 4 mod, r8, 4-bit, lr1e-4, 3ep | FAIL +555% | — | not run |
| **3** | attention q/k/v/o, layers4-20, r8 α8 rsLoRA, bf16, lr3e-5, 1ep, completion-only, 10% anchor | **PASS** 0.9915 | PASS s=1.0 | **FAIL** overall 0.689; code 0.350; web 0.844; dep 0.875; load 0.750 |
| **3d** | same but r64 α16, lr1e-5, 2ep | **PASS** 0.9899 | PASS s=1.0 | **FAIL** overall 0.724; code 0.550; web 0.594; dep 1.000; load 0.750 |

Baseline to beat: overall **0.753**; code_vuln **0.700**; web_config **0.688**;
dependency_cve **0.875**; load_testing **0.750**.

Verdict after 3d: **8× rank did not fix the label habit.** V02 still "buffer overflow",
V03/V04 still mislabeled despite keyword passes, V06 describes TLS then says "XSS".
Only V05 (MD5 "not secure") had the right canonical label.

---

## 2. Where we stopped — Pass 5 status (VERY IMPORTANT)

`NEXT_PROMPT.md` (local) defines the current plan. We were executing it:

**STEP 0 — DONE (local).**
- Ollama running, `sirius-final` model present.
- `python 13_dump_raw_outputs.py --model sirius-final --alt-num-predict 64` → wrote
  `raw_dump_sirius-final.md/.json`.
- Histogram primary budget (240): PASS=25, OTHER=8, **WRONG_LABEL=1**.
- At short budget (64): V03, V04 flip to `WRONG_LABEL(buffer overflow)`; V02 → TRUNCATED_SUSPECT.
- Decision: WRONG_LABEL(buffer overflow) confirmed → proceed to training (expected case).

**STEP 1 — Pass 5 training attempted, interrupted, /content wiped, re-staged, restarted, then STOPPED by user.**
- First run failed: script defaults to `sirius_train.jsonl`; fixed with `--train sirius_train_pass5.jsonl`.
- Required log lines verified: `Unfroze last 2 base layers (idx >= 22): 29.82M params`,
  `Data: using sirius_train_pass5.jsonl — 3358 LABEL-first items`, `[SplitLR] base_lr=1e-06 on 24 base params; adapter lr=3e-05 on 160 params`.
- That run trained to completion: PPL ratio **0.8934 (−10.66%)**, adapter `sirius_lora_adapter_pass5`,
  merged `sirius_merged_pass5`, log `sirius_train_log_pass5.json` — **ALL LOST** when the kernel
  was restarted to clear a hung gate script (restart wiped /content on this runtime).
- Re-uploaded everything and restarted training; user stopped the session during that second run.
  **No Pass 5 artifacts exist now.** Must retrain.

**STEP 2 — gate sweep: script was broken (see §4); fixed locally but not yet re-run successfully.**
**STEP 3 — never reached.**

---

## 3. Toolkit defects discovered + fixes already applied to local copies

1. `07_train_colab (3).py` — `get_parameter_names(model, [LayerNorm], ALL_LAYERNORM_LAYERS)`
   (3 args) fails on transformers 4.46 → SplitLR fell back and trained unfrozen layers at the
   wrong LR. **Fixed** locally: 2 args. Local file patched.
2. `09_eval_gate (2).py` — caches full-vocab log-softmax for 200×512 tokens (~60 GB) →
   OOM-killed kernel. **Fixed** in local `09_eval_gate_pass5.py`: store scalar target log-prob.
3. `09_eval_gate (2).py` — `_get_lora_layers` uses `while hasattr(base, "base_model")` which
   loops forever (HF property returns `self`). **Fixed** in local `09_eval_gate_pass5.py`:
   `base = model.base_model.model ... for module in base.modules()`.
4. bitsandbytes 0.44.1 has no CUDA-13 binary → install latest (`0.50.2` verified).
5. TRL SFTTrainer double-pads pre-tokenized labels → plain Trainer + DataCollatorForSeq2Seq
   (already in this script family).
6. PPL must be measured on wikitext-2-raw clean text, not ChatML dicts.
7. llama.cpp replaced Make with CMake → build `llama-quantize` via `cmake --build`, not `make`.
8. Dataset manifest has only 20 general-replay items (planned 500) — note only.
9. `04_sirius_baseline.py` item L04 is mathematically unpassable (`min_pass=2`, one keyword group).

---

## 4. Exact resume procedure (copy this into next session)

### A. Local — no work needed to re-derive
STEP 0 is already done; do not repeat unless you want a fresh dump.

### B. Colab (sign in, upload notebook `SIRIUS_Phase2_Colab.ipynb`, connect T4)
Install cell (cell 1) — use this, not the notebook default:
```
!pip install -q -U transformers==4.46.0 peft==0.13.0 datasets==3.1.0 accelerate==1.1.1 trl==0.12.0
!pip install -q -U bitsandbytes
!python -c "import bitsandbytes,torch; print('bnb',bitsandbytes.__version__,'cuda',torch.cuda.is_available())"
```
Upload (cell 2):
- `07_train_colab (3).py` (LOCAL PATCHED — SplitLR fix)
- `sirius_train_pass5.jsonl`, `sirius_dev.jsonl`
- `09_eval_gate_pass5.py` (LOCAL PATCHED — memory + infinite-loop fixes)
- `11_export_gguf.py`

Train (cell 3):
```
!python "/content/07_train_colab (3).py" --pass-name pass5 --train sirius_train_pass5.jsonl --skip-install-check
```
Expect: `Unfroze last 2 base layers ... 29.82M params`, `Data: using sirius_train_pass5.jsonl — 3358 LABEL-first items`,
`[SplitLR] base_lr=1e-06 on 24 base params; adapter lr=3e-05 on 160 params`.
PPL gate target ratio < 1.30.

Gate (cell 3 after training):
```
!python /content/09_eval_gate_pass5.py --merged /content/sirius_merged_pass5 \
   --adapter /content/sirius_lora_adapter_pass5 --dev /content/sirius_dev.jsonl \
   --tag pass5 --scales "1.5,1.0,0.75,0.5"
```

Export (cell 3 after gate):
```
!python /content/11_export_gguf.py --merged /content/sirius_merged_pass5 --base-name sirius_final
```

### C. Acceptance — simplest reliable path
Do **not** download the GGUFs via the browser (5 MB cap, 500 MB files). Instead install
Ollama **inside Colab** and run the acceptance there — this worked before:
```
!apt-get -qq update && apt-get -qq install -y zstd
!curl -fsSL https://ollama.com/install.sh | sh
!nohup ollama serve > /tmp/ollama.log 2>&1 &
!sleep 6
!sed -i 's/sirius_final_Q6_K.gguf/sirius_final_Q6_K.gguf/' /content/Modelfile.sirius
!ollama create sirius-pass5 -f /content/Modelfile.sirius
!python /content/04_sirius_baseline.py --model sirius-pass5 --full
!python /content/13_dump_raw_outputs.py --model sirius-pass5 --alt-num-predict 64
```
(Upload `04_sirius_baseline.py` and `13_dump_raw_outputs.py` into Colab first.)

### D. Acceptance criteria (unchanged)
- overall ≥ 0.753; code_vuln ≥ 0.680; web_config ≥ 0.668
- V02–V06: ≥ 4 of 5 correct canonical labels (use `TAXONOMY.md` as label authority)
- general PPL ratio < 1.30
- Treat single-capability deltas < ±0.25 as noise (n=8–10 per capability).

### E. If Pass 5 still fails — escalation ladder (do NOT skip ahead)
1. `--safe-repeat 8` in script 12 → rebuild → retrain (stronger restraint).
2. Unfreeze last 4 layers instead of 2 (`unfreeze_last_n_layers=4`), keep base lr 1e-6.
3. Expand eval to 100+ items before concluding from small deltas.

---

## 5. File inventory (local)

| File | Purpose |
|---|---|
| `SIRIUS_Phase2_Colab.ipynb` | 7-cell notebook used in Colab |
| `07_train_colab (3).py` | **patched** Pass 5 trainer (SplitLR fix) |
| `09_eval_gate_pass5.py` | **patched** dual gate + sweep (memory + loop fixes) |
| `11_export_gguf.py` | lean GGUF export (llama.cpp CMake, no llama-cpp-python) |
| `sirius_train_pass5.jsonl` (2.56 MB) | LABEL-first training data, 3358 items |
| `sirius_train_pass5_manifest.json` | manifest |
| `sirius_dev.jsonl` | 100 dev items |
| `TAXONOMY.md` | canonical LABEL phrases per archetype |
| `13_dump_raw_outputs.py` | raw dump + failure classifier |
| `raw_dump_sirius-final.md/.json` | STEP 0 results |
| `04_sirius_baseline.py` | 34-item acceptance suite |
| `SIRIUS_Telemetry_*.{json,md}`, `SIRIUS_Phase2_*.md` | earlier phases |
| `SIRIUS_Training_Handoff.zip` | archive of the above (may be stale — regenerate if needed) |

Google Drive (Fritz account) folder `sirius_pass3d` holds Pass 3d GGUFs + logs;
not needed for Pass 5.

---

## 6. Phases — where we are

- **Phase 1 — Diagnosis: COMPLETE.** Telemetry report produced.
- **Phase 2a — Consultation/merge plan: COMPLETE.** 3 seats + 4th merge.
- **Phase 2b — Retention fixes (Passes 1→3/3d): COMPLETE.** Perplexity solved, task fit not.
- **Phase 2c — Pass 5 (LABEL-first + hard negatives + SplitLR): IN PROGRESS.** Must retrain from scratch.
- **Phase 3 — Acceptance & ship: NOT STARTED.** No model has passed.
- **Phase 4 — Deployment hardening (larger eval, ±2% PPL re-verify after quant): NOT STARTED.**

**One-line status:** Retention solved; label habit unsolved; Pass 5 configured with the
right data and patched scripts, but its training artifacts were lost to a runtime restart —
retrain Pass 5 first thing next session, then run gate → export → in-Colab acceptance.
