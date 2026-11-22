#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SIRIUS Toolkit - Script 07: Phase-2 Fine-Tuning (Google Colab T4)
==================================================================
Implements the merged Phase-2 plan AFTER the Pass 1 post-mortem and the
three-reviewer briefings (Beam / VL / anonymous second reviewer).

WHAT IT DOES
------------
1. Installs deps.
2. Loads Qwen2.5-0.5B-Instruct in bf16 (Pass 3) or 4-bit NF4 (Pass 1/2 historical).
3. Attaches LoRA per the chosen pass config.
4. Trains with completion-only loss masking, wikitext anchor interleaved,
   dual eval (security loss + general PPL), early stopping on general PPL.
5. Saves the adapter + merged HF model + a train log with PPL0/PPL_after
   in both ratio and nats.
6. Hands off to 09_eval_gate.py for the dual-gate confirmation + the
   inference-time adapter scaling sweep (s ∈ {1.0, 0.5, 0.25}).

PASSES (de-escalation ladder)
-----------------------------
- pass 1: all 7 modules, r=16, alpha=32, 4-bit NF4, lr 1e-4, 3 epochs
          [HISTORICAL — FAILED: +740% PPL, +2.13 nats catastrophic forgetting]
- pass 2: 5 modules (q,k,v,o,down), r=16, alpha=32, 4-bit NF4, lr 1e-4, 3 epochs
          [HISTORICAL — was running when briefings arrived]
- pass 3: 4 modules attention-only (q,k,v,o), r=8, alpha=8 (alpha/r=1),
          layers 4-20 (skip first/last 2), use_rslora=True, LoRA dropout 0.05,
          bf16 (no 4-bit quant noise), lr 3e-5, 1 epoch, cosine+warmup 5%,
          grad_clip 0.5, weight_decay 0.01 (≈L2-SP on adapters),
          label_smoothing 0.1, completion-only loss (-100 on prompt tokens),
          10% wikitext anchor interleaved per-batch, dual eval gate,
          early stopping patience 2 on general PPL.
          [NEW — synthesized from the three reviewer briefings]

KEY CHANGES VS. PASS 1 (the post-mortem)
----------------------------------------
| Lever              | Pass 1            | Pass 3                          |
|--------------------|-------------------|---------------------------------|
| Quantization       | 4-bit NF4         | bf16 (0.5B doesn't need 4-bit;  |
|                    |                   |   quant noise compounds forget.)|
| Modules            | all 7             | 4 (attention only — q,k,v,o)    |
| Layers             | all 24            | 4-20 (skip first/last 2)        |
| r / alpha          | 16 / 32 (α=2r)    | 8 / 8 (α=r, 1× effective LR)    |
| rsLoRA              | no                | yes                             |
| LoRA dropout       | 0.05              | 0.05                            |
| lr                 | 1e-4              | 3e-5                            |
| epochs             | 3                 | 1 (+ early stop patience 2)     |
| warmup             | 0.03              | 0.05                            |
| scheduler          | cosine→10%        | cosine (full decay)             |
| grad_clip          | 0.3               | 0.5                             |
| weight_decay       | 0.0               | 0.01 (≈L2-SP on adapters)        |
| label_smoothing    | 0.0               | 0.1                             |
| loss masking       | none              | completion-only (-100 on prompt)|
| anchor data        | none              | 10% wikitext, interleaved       |
| PPL gate metric    | dev loss (security)| dual: security loss + gen PPL  |
| PPL gate threshold | ±2% (too strict) | PPL/PPL0 < 1.30 (+0.26 nats)    |

GATE REFRAME (Beam's point — PPL percentages lie)
-------------------------------------------------
  Pass 1: PPL0=306.4 → PPL_after=2575.7 → "+740%"
  In nats: ln(306.4)=5.72, ln(2575.7)=7.85, Δ = +2.13 nats.
  Still severe, but a modest intervention should claw most of it back.
  Realistic Pass-3 target: PPL/PPL0 < 1.30 (+0.26 nats), not "back to 306."

  ALSO: PPL0=306 was measured on ChatML-formatted security dev items, NOT
  wikitext. A 0.5B on raw wikitext sits at ~20-40. The 306 number reflects
  the specialized eval distribution; the v2 gate measures general PPL on
  wikitext-2-raw test split (clean text, no chat template) so the signal
  matches the anchor data distribution.

INPUTS (upload to Colab first)
------------------------------
- sirius_train.jsonl   (from 06_build_dataset.py)
- sirius_dev.jsonl     (from 06_build_dataset.py)

OUTPUTS
-------
- sirius_lora_adapter_passN/   (PEFT adapter weights)
- sirius_merged_passN/         (merged full model, for 09 + 08)
- sirius_train_log_passN.json  (loss curve, PPL0, PPL_after, config, gate result)
"""
import json, os, sys, argparse, math

# ---------------------------------------------------------------------------
# CONFIGURATION BLOCK
# ---------------------------------------------------------------------------
BASE_MODEL = "Qwen/Qwen2.5-0.5B-Instruct"

# De-escalation ladder. Pass 3 is the NEW synthesized config.
PASSES = [
    # --- Pass 1: HISTORICAL, FAILED at +740% PPL (+2.13 nats). ---
    # Kept for reproducibility / verification runs only.
    dict(
        name="pass1",
        r=16, alpha=32, dropout=0.05, use_rslora=False,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
        layers_to_transform=None,
        quantize_4bit=True,
        lr=1e-4, epochs=3, warmup_ratio=0.03, lr_scheduler="cosine",
        lr_scheduler_kwargs={"num_cycles": 0.1},
        max_grad_norm=0.3, weight_decay=0.0, label_smoothing=0.0,
        completion_only_loss=False, anchor_ratio=0.0,
        per_device_train_batch_size=4, gradient_accumulation_steps=4,
        early_stopping_patience=1,
        eval_metric="eval_loss", greater_is_better=False,
        note="HISTORICAL. Pass 1 collapsed to +740% PPL. Do NOT re-run as primary.",
    ),
    # --- Pass 2: HISTORICAL, was running when briefings arrived. ---
    dict(
        name="pass2",
        r=16, alpha=32, dropout=0.05, use_rslora=False,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "down_proj"],
        layers_to_transform=None,
        quantize_4bit=True,
        lr=1e-4, epochs=3, warmup_ratio=0.03, lr_scheduler="cosine",
        lr_scheduler_kwargs={"num_cycles": 0.1},
        max_grad_norm=0.3, weight_decay=0.0, label_smoothing=0.0,
        completion_only_loss=False, anchor_ratio=0.0,
        per_device_train_batch_size=4, gradient_accumulation_steps=4,
        early_stopping_patience=1,
        eval_metric="eval_loss", greater_is_better=False,
        note="HISTORICAL. Pass 2 was running at briefing time. Result: see log.",
    ),
    # --- Pass 3: NEW, synthesized from the three reviewer briefings. ---
    dict(
        name="pass3",
        r=8, alpha=8, dropout=0.05, use_rslora=True,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],   # attention only
        layers_to_transform=list(range(4, 20)),                     # skip first/last 2
        quantize_4bit=False,                                       # bf16, no quant noise
        lr=3e-5, epochs=1, warmup_ratio=0.05, lr_scheduler="cosine",
        lr_scheduler_kwargs=None,
        max_grad_norm=0.5, weight_decay=0.01, label_smoothing=0.1,
        completion_only_loss=True, anchor_ratio=0.10,               # 10% wikitext anchor
        per_device_train_batch_size=4, gradient_accumulation_steps=4,
        early_stopping_patience=2,
        eval_metric="eval_general_ppl", greater_is_better=False,    # dual gate
        note="NEW — synthesized Pass 3. Run if Pass 2 fails the PPL gate.",
    ),
    # --- Pass 4: targeted fix for V02-V06 mislabeling after Pass 3. ---
    # Diagnosis: Pass 3 passed the dual PPL gate perfectly (knowledge
    # preserved) but failed the 34-item capability gate. Code_vuln
    # collapsed 0.700 → 0.350 because the r=8 / 1-epoch / attention-only
    # adapter was too weak to override the base model's strong
    # "buffer overflow" prior on hardcoded_secret / tls_verify_disabled
    # / weak_hash. web_config improved 0.688 → 0.844 (no competing prior).
    # Pass 4 adds capacity (+1 module, +r, +1 epoch) and removes the
    # label_smoothing that was diluting the sharp canonical labels.
    dict(
        name="pass4",
        r=16, alpha=16, dropout=0.05, use_rslora=True,             # alpha/r = 1 still
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "down_proj"],                              # +down_proj for label write
        layers_to_transform=list(range(4, 20)),
        quantize_4bit=False,
        lr=3e-5, epochs=2, warmup_ratio=0.05, lr_scheduler="cosine",
        lr_scheduler_kwargs=None,
        max_grad_norm=0.5, weight_decay=0.01,
        label_smoothing=0.0,                                       # OFF — labels are canonical, sharpen them
        completion_only_loss=True, anchor_ratio=0.10,
        per_device_train_batch_size=4, gradient_accumulation_steps=4,
        early_stopping_patience=3,                                  # let code_vuln converge
        early_stopping_min_delta=0.005,                            # 0.5% loss improvement counts as progress
        eval_metric="eval_general_ppl", greater_is_better=False,
        contrastive_archetypes=["hardcoded_secret",                # 3x upweight
                                "tls_verify_disabled",
                                "weak_hash"],
        contrastive_factor=3,
        note="Pass 4 — capacity boost + contrastive upweight on the 3 "
             "problem archetypes. Run after Pass 3 passed the dual gate "
             "but failed the capability gate.",
    ),
    # --- Pass 5: the three-lever fix after Pass 3d proved capacity ≠ fix. ---
    # Pass 3d (r=64 attention-only, 2 epochs) PASSED the dual PPL gate but
    # still failed the 34-item acceptance gate: code_vuln 0.550, V02-V06
    # ~1/5 correct. Conclusion: rank is not the bottleneck — the training
    # signal is. Pass 5 changes the signal three ways:
    #   1. DATA: LABEL-first unified dataset (script 12) — canonical class
    #      as the FIRST line of every answer (highest-margin tokens), plus
    #      the original security corpus with structurally diverse snippets
    #      and matched safe hard negatives (teaches restraint + kills the
    #      "everything is a buffer overflow" prior).
    #   2. PATH: +down_proj (MLP path) at r=16 — label swaps are MLP-level
    #      decisions; attention-only adapters cannot rewrite them.
    #   3. LAYERS: unfreeze the last 2 transformer blocks at a 30x smaller
    #      LR (1e-6) — direct gradient path to the output head's task
    #      representations without touching early factual layers.
    dict(
        name="pass5",
        r=16, alpha=16, dropout=0.05, use_rslora=True,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "down_proj"],
        layers_to_transform=list(range(4, 20)),
        quantize_4bit=False,
        lr=3e-5, epochs=2, warmup_ratio=0.05, lr_scheduler="cosine",
        lr_scheduler_kwargs=None,
        max_grad_norm=0.5, weight_decay=0.01,
        label_smoothing=0.0,
        completion_only_loss=True, anchor_ratio=0.10,
        per_device_train_batch_size=4, gradient_accumulation_steps=4,
        early_stopping_patience=3,
        early_stopping_min_delta=0.005,
        eval_metric="eval_general_ppl", greater_is_better=False,
        unfreeze_last_n_layers=2,          # layers 22,23 get real gradients
        unfreeze_base_lr=1e-6,             # 30x smaller than adapter LR
        train_data_file="sirius_train_pass5.jsonl",  # script-12 output
        composite_stop=True,               # BOTH gen PPL and sec loss must plateau
        note="Pass 5 — LABEL-first data + MLP path + last-2-layer unfreeze. "
             "Run script 12 first to build sirius_train_pass5.jsonl.",
    ),
    # --- Pass 6R (Phase 5R): knowledge injection, CORRECTED recipe. ---
    # The v1 recipe (r=8, lr 1e-5, 1 epoch, down_proj) starved the signal:
    # 2.4% new-signal share, 41:1 replay dominance, ~11 of ~460 steps
    # carried lead signal — it learned nothing (lead 0.127 vs target 0.55,
    # restraint 0/5). The v2 dataset (21_expand_lead_data.py) fixes the
    # data: 1800 lead2 counterfactual drills (200/cap, 63 pairs, 34%
    # restraint), 40% new-signal share. This recipe fixes the training:
    # knowledge lives in the FFN, so target gate/up/down; lr 1e-4 gives the
    # new signal room; r=16 + 2 epochs. Retention is protected by the 60/40
    # replay ratio + dual PPL gate, NOT by starving lr. The merge/chain
    # question (s=0.5 chained base vs resuming the pass5 adapter) is
    # decided by the Step-0b control eval BEFORE training — see NEXT_PROMPT
    # Part 4.
    dict(
        name="pass6",
        r=16, alpha=16, dropout=0.05, use_rslora=True,
        target_modules=["gate_proj", "up_proj", "down_proj"],
        layers_to_transform=list(range(4, 20)),
        quantize_4bit=False,
        lr=1e-4, epochs=2, warmup_ratio=0.05, lr_scheduler="cosine",
        lr_scheduler_kwargs=None,
        max_grad_norm=0.5, weight_decay=0.01,
        label_smoothing=0.0,
        completion_only_loss=True, anchor_ratio=0.10,
        per_device_train_batch_size=4, gradient_accumulation_steps=4,
        early_stopping_patience=3,
        early_stopping_min_delta=0.005,
        eval_metric="eval_general_ppl", greater_is_better=False,
        train_data_file="sirius_train_pass6_lead_v2.jsonl",  # script-21 output
        base_model=None,  # set via --base-model (script 18 output — see Step 0b)
        composite_stop=True,
        note="Phase 5R — corrected recipe on the v2 dataset. Run 21 (data) "
             "and the Step-0 controls first; 07_train_colab.py --pass-name "
             "pass6 --base-model <decided-by-Step-0b>",
    ),
]

# Anchor source: wikitext-2-raw matches the PPL eval distribution (Beam's rule).
ANCHOR_DATASET = "wikitext"
ANCHOR_CONFIG = "wikitext-2-raw-v1"

# Gate thresholds (Pass 3 dual gate).
# Old gate was ±2% on security dev loss — too strict for narrow data; manufactured
# the "catastrophic failure" signal. New gate is on general wikitext PPL.
GENERAL_PPL_MAX_RATIO = 1.30   # PPL_after / PPL0 < 1.30  (+0.26 nats)

# Install cell
INSTALL_CELL = """# === Colab install cell - run first ===
!pip install -U transformers==4.46.0 peft==0.13.0 bitsandbytes==0.44.1 \\
    datasets==3.1.0 accelerate==1.1.1 trl==0.12.0
!nvidia-smi  # confirm T4, 15 GB VRAM
"""

def print_install():
    print("=" * 70)
    print("SIRIUS Phase-2 Fine-Tuning - run this install cell first:")
    print("=" * 70)
    print(INSTALL_CELL)
    print("=" * 70)
    print()

# ---------------------------------------------------------------------------
# Data loading: ChatML jsonl + wikitext anchor
# ---------------------------------------------------------------------------
def load_chatml_dataset(train_path, dev_path):
    from datasets import Dataset
    def read_jsonl(p):
        rows = []
        with open(p, encoding="utf-8") as f:
            for line in f:
                rows.append(json.loads(line))
        return rows
    return (Dataset.from_list(read_jsonl(train_path)),
            Dataset.from_list(read_jsonl(dev_path)))

def load_anchor_dataset(cfg, security_n):
    """Load wikitext-2-raw and sample anchor_ratio × security_n items.
    Returned as a list of plain strings (continuation data, no chat template)."""
    from datasets import load_dataset
    if cfg["anchor_ratio"] <= 0:
        return []
    n_anchor = int(security_n * cfg["anchor_ratio"])
    ds = load_dataset(ANCHOR_DATASET, ANCHOR_CONFIG, split="train")
    texts = [t for t in ds["text"] if len(t.strip()) > 200]
    return texts[:n_anchor]

def load_general_eval_texts(n=200):
    """Held-out wikitext-2-raw TEST split for the general PPL gate.
    Distinct from the anchor (which uses the train split)."""
    from datasets import load_dataset
    ds = load_dataset(ANCHOR_DATASET, ANCHOR_CONFIG, split="test")
    return [t for t in ds["text"] if len(t.strip()) > 200][:n]

# ---------------------------------------------------------------------------
# Formatting: ChatML with completion-only loss masking
# ---------------------------------------------------------------------------
def format_with_completion_mask(example, tokenizer, max_len=512):
    """Tokenize the chat and mask the prompt portion (system + user + assistant
    role marker) with -100. Only the assistant's content + <|im_end|> contribute
    to loss. Qwen2.5 ChatML layout:
      <|im_start|>system\\n...\\n<|im_end|>\\n<|im_start|>user\\n...\\n<|im_end|>
      \\n<|im_start|>assistant\\n{completion}<|im_end|>
    """
    messages = example["messages"]
    if len(messages) < 2 or messages[-1]["role"] != "assistant":
        # Fallback: full-text loss (no masking) for malformed items
        text = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=False)
        enc = tokenizer(text, truncation=True, max_length=max_len, padding=False)
        return {**enc, "labels": enc["input_ids"].copy()}
    prompt_msgs = messages[:-1]
    completion = messages[-1]["content"]
    prompt_text = tokenizer.apply_chat_template(
        prompt_msgs, tokenize=False, add_generation_prompt=True)
    full_text = prompt_text + completion + "<|im_end|>"
    enc = tokenizer(full_text, truncation=True, max_length=max_len, padding=False)
    prompt_enc = tokenizer(prompt_text, truncation=True, max_length=max_len,
                           padding=False)
    prompt_len = len(prompt_enc["input_ids"])
    labels = [-100] * prompt_len + enc["input_ids"][prompt_len:]
    labels = labels[:len(enc["input_ids"])]
    return {**enc, "labels": labels}

def format_full_text(example, tokenizer, max_len=512):
    """Full-text loss (no masking) — Pass 1/2 historical behavior."""
    text = tokenizer.apply_chat_template(
        example["messages"], tokenize=False, add_generation_prompt=False)
    enc = tokenizer(text, truncation=True, max_length=max_len, padding=False)
    return {**enc, "labels": enc["input_ids"].copy()}

def format_anchor(text, tokenizer, max_len=512):
    """Anchor (wikitext) item: plain text, full-text loss (no masking)."""
    enc = tokenizer(text, truncation=True, max_length=max_len, padding=False)
    return {**enc, "labels": enc["input_ids"].copy()}

# ---------------------------------------------------------------------------
# Padding collator (consistent input_ids + labels padding)
# ---------------------------------------------------------------------------
def make_collator(tokenizer):
    pad_id = tokenizer.pad_token_id
    class Collator:
        def __call__(self, features):
            max_len = max(len(f["input_ids"]) for f in features)
            input_ids, attn, labels = [], [], []
            for f in features:
                ids = f["input_ids"]
                lab = f["labels"]
                pad_len = max_len - len(ids)
                input_ids.append(ids + [pad_id] * pad_len)
                attn.append([1] * len(ids) + [0] * pad_len)
                labels.append(lab + [-100] * pad_len)
            import torch
            return {
                "input_ids": torch.tensor(input_ids, dtype=torch.long),
                "attention_mask": torch.tensor(attn, dtype=torch.long),
                "labels": torch.tensor(labels, dtype=torch.long),
            }
    return Collator()

# ---------------------------------------------------------------------------
# Perplexity probe (on raw text, no chat template)
# ---------------------------------------------------------------------------
def measure_perplexity(model, tokenizer, texts, max_samples=200,
                       seq_len=512, device="cuda"):
    import torch
    model.eval()
    losses = []
    with torch.no_grad():
        for i, text in enumerate(texts):
            if i >= max_samples: break
            enc = tokenizer(text, return_tensors="pt", truncation=True,
                            max_length=seq_len)
            input_ids = enc["input_ids"].to(device)
            if input_ids.shape[1] < 2: continue
            with torch.amp.autocast("cuda", dtype=torch.bfloat16):
                out = model(input_ids, labels=input_ids)
            losses.append(out.loss.item())
    return math.exp(sum(losses) / len(losses)) if losses else float("inf")

# ---------------------------------------------------------------------------
# Dual-eval callback: logs eval_general_ppl at every eval step
# ---------------------------------------------------------------------------
def make_dual_eval_callback(tokenizer, general_eval_texts, device="cuda"):
    """Adds `eval_general_ppl` (wikitext, held-out) to the metrics dict at each
    eval step. With metric_for_best_model='eval_general_ppl', this drives
    early stopping on the GENERAL distribution — catches forgetting before
    the security loss signal saturates."""
    from transformers import TrainerCallback

    class DualEvalCallback(TrainerCallback):
        def on_evaluate(self, args, state, control, model=None,
                        metrics=None, **kwargs):
            if model is None or metrics is None: return
            try:
                base = (model.base_model.model
                        if hasattr(model, "base_model") else model)
                ppl = measure_perplexity(base, tokenizer, general_eval_texts,
                                         max_samples=100, device=device)
                metrics["eval_general_ppl"] = ppl
                print(f"  [dual eval] general PPL (wikitext): {ppl:.4f}")
            except Exception as e:
                print(f"  [dual eval] failed: {e}")

    return DualEvalCallback()

# ---------------------------------------------------------------------------
# Main training routine
# ---------------------------------------------------------------------------
def train(pass_name="pass3", train_path="sirius_train.jsonl",
          dev_path="sirius_dev.jsonl", skip_install_check=False, seed=42,
          base_model=None):
    if not skip_install_check:
        print_install()

    import torch
    from transformers import (AutoModelForCausalLM, AutoTokenizer,
                              TrainingArguments, EarlyStoppingCallback,
                              BitsAndBytesConfig, Trainer)
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from datasets import concatenate_datasets

    cfg = next((p for p in PASSES if p["name"] == pass_name), None)
    if cfg is None:
        print(f"Unknown pass: {pass_name}. Available: "
              f"{[p['name'] for p in PASSES]}")
        sys.exit(1)
    # Chained passes train on top of an earlier merge: --base-model points
    # at a merged HF dir (e.g. script 18's pass5 s=0.5 reconstruction).
    if base_model:
        cfg = dict(cfg)  # do not mutate the shared config dict
        cfg["base_model"] = base_model

    print(f"\n{'='*70}\nSIRIUS Phase-2 — {cfg['name'].upper()}\n{'='*70}")
    print(f"  modules: {cfg['target_modules']}")
    print(f"  r={cfg['r']}, alpha={cfg['alpha']} "
          f"(alpha/r = {cfg['alpha']/cfg['r']:.1f})")
    print(f"  layers_to_transform: {cfg['layers_to_transform']}")
    print(f"  use_rslora: {cfg['use_rslora']}")
    print(f"  quantize_4bit: {cfg['quantize_4bit']}  "
          f"({'NF4' if cfg['quantize_4bit'] else 'bf16 — no quant noise'})")
    print(f"  lr={cfg['lr']}, epochs={cfg['epochs']}, warmup={cfg['warmup_ratio']}")
    print(f"  scheduler={cfg['lr_scheduler']}, grad_clip={cfg['max_grad_norm']}")
    print(f"  weight_decay={cfg['weight_decay']}  (≈L2-SP on adapters)")
    print(f"  label_smoothing={cfg['label_smoothing']}")
    print(f"  completion_only_loss: {cfg['completion_only_loss']}")
    print(f"  anchor_ratio: {cfg['anchor_ratio']}  (wikitext, interleaved)")
    print(f"  early_stopping_patience: {cfg['early_stopping_patience']}")
    print(f"  eval_metric: {cfg['eval_metric']}  (dual gate)")
    print(f"  seed: {seed}")
    if cfg.get("note"): print(f"  NOTE: {cfg['note']}")
    print()

    # 1. Tokenizer
    tokenizer = AutoTokenizer.from_pretrained(
        cfg.get("base_model") or BASE_MODEL)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # 2. Load model — bf16 for Pass 3, 4-bit for Pass 1/2 historical
    if cfg["quantize_4bit"]:
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=torch.bfloat16,
        )
        model = AutoModelForCausalLM.from_pretrained(
            cfg.get("base_model") or BASE_MODEL,
            quantization_config=bnb_config,
            device_map="auto", torch_dtype=torch.bfloat16)
        model = prepare_model_for_kbit_training(
            model, use_gradient_checkpointing=True)
    else:
        # bf16 — no quantization noise. 0.5B = ~1GB, fits easily on T4.
        model = AutoModelForCausalLM.from_pretrained(
            cfg.get("base_model") or BASE_MODEL,
            torch_dtype=torch.bfloat16, device_map="auto")
        model.gradient_checkpointing_enable(
            gradient_checkpointing_kwargs={"use_reentrant": False})

    # 3. Attach LoRA
    lora_kwargs = dict(
        r=cfg["r"],
        lora_alpha=cfg["alpha"],
        lora_dropout=cfg["dropout"],
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=cfg["target_modules"],
    )
    if cfg["use_rslora"]:
        lora_kwargs["use_rslora"] = True
    if cfg["layers_to_transform"] is not None:
        lora_kwargs["layers_to_transform"] = cfg["layers_to_transform"]
    peft_config = LoraConfig(**lora_kwargs)
    model = get_peft_model(model, peft_config)

    # Pass 5: partial unfreeze of the last N transformer blocks. Gives a
    # direct gradient path to the task-head representations. LoRA params are
    # excluded from unfreezing so the LR split below classifies them as
    # adapter-side (fast LR), not base-side (slow LR).
    if cfg.get("unfreeze_last_n_layers"):
        n_unf = cfg["unfreeze_last_n_layers"]
        n_total = model.config.num_hidden_layers
        unfrozen = 0
        for pname, p in model.named_parameters():
            if "lora_" in pname:
                continue
            if ".layers." in pname:
                try:
                    idx = int(pname.split(".layers.")[1].split(".")[0])
                except (ValueError, IndexError):
                    continue
                if idx >= n_total - n_unf:
                    p.requires_grad = True
                    unfrozen += p.numel()
        model._n_unfrozen_from = n_total - n_unf
        print(f"Unfroze last {n_unf} base layers (idx >= {n_total - n_unf}): "
              f"{unfrozen/1e6:.2f}M params, will train at "
              f"lr={cfg.get('unfreeze_base_lr')} (adapter lr stays {cfg['lr']})")
    model.print_trainable_parameters()

    # 4. Data: security + optional anchor + optional contrastive upweight
    train_ds, dev_ds = load_chatml_dataset(train_path, dev_path)
    # Pass 5: the unified LABEL-first dataset from script 12 REPLACES the
    # legacy train set (it already contains the legacy data rewritten,
    # the corpus, and the oversample — do not apply contrastive logic again).
    if cfg.get("train_data_file") and os.path.isfile(cfg["train_data_file"]):
        from datasets import Dataset as _DS
        with open(cfg["train_data_file"], encoding="utf-8") as f:
            rows = [json.loads(l) for l in f if l.strip()]
        train_ds = _DS.from_list(rows)
        print(f"Data: using {cfg['train_data_file']} — {len(train_ds)} "
              f"LABEL-first items from script 12 (legacy+corpus+oversample).")
    anchor_texts = load_anchor_dataset(cfg, len(train_ds))
    if anchor_texts:
        print(f"Anchor: {len(anchor_texts)} wikitext items "
              f"({cfg['anchor_ratio']*100:.0f}% of {len(train_ds)} security)")

    # Pass 4: contrastive upweight. Prefer the explicit contrastive file
    # (06b_build_contrastive.py output) if present — it adds explicit
    # NOT-buffer-overflow contrast pairs that simple duplication cannot.
    # Fall back to in-script duplication of the 3 problem archetypes.
    contrastive_path = "sirius_train_contrastive.jsonl"
    if (cfg.get("contrastive_archetypes")
            and os.path.isfile(contrastive_path)):
        from datasets import Dataset, concatenate_datasets as _concat
        with open(contrastive_path, encoding="utf-8") as f:
            crows = [json.loads(line) for line in f]
        contrast_ds = Dataset.from_list(crows)
        train_ds = _concat([train_ds, contrast_ds]).shuffle(seed=seed)
        print(f"Contrastive: loaded {len(crows)} items from "
              f"{contrastive_path} (06b output). "
              f"Total security: {len(train_ds)}.")
    elif cfg.get("contrastive_archetypes") and cfg.get("contrastive_factor", 1) > 1:
        from datasets import Dataset, concatenate_datasets as _concat
        archs = set(cfg["contrastive_archetypes"])
        factor = cfg["contrastive_factor"]
        # Split the train set into upweighted vs not
        up_rows, other_rows = [], []
        for r in train_ds:
            arch = r.get("meta", {}).get("archetype", "")
            if arch in archs:
                up_rows.append(r)
            else:
                other_rows.append(r)
        # The upweighted set repeated (factor) times; the rest once
        up_ds = Dataset.from_list(up_rows * factor) if up_rows else None
        other_ds = Dataset.from_list(other_rows) if other_rows else None
        parts = [p for p in (other_ds, up_ds) if p is not None]
        train_ds = _concat(parts).shuffle(seed=seed)
        print(f"Contrastive upweight (fallback): {len(up_rows)} items × "
              f"{factor} = {len(up_rows)*factor}; {len(other_rows)} items × 1. "
              f"Total security: {len(train_ds)}. "
              f"(For explicit NOT-buffer-overflow pairs, run 06b_build_contrastive.py)")

    # 5. Tokenize
    max_len = 512
    fmt_sec = (format_with_completion_mask if cfg["completion_only_loss"]
               else format_full_text)

    def fmt_security(ex):
        return fmt_sec(ex, tokenizer, max_len)
    def fmt_anchor(ex):
        return format_anchor(ex["text"], tokenizer, max_len)

    train_tok = train_ds.map(fmt_security, remove_columns=train_ds.column_names)
    dev_tok = dev_ds.map(fmt_security, remove_columns=dev_ds.column_names)

    if anchor_texts:
        from datasets import Dataset
        anchor_ds = Dataset.from_list([{"text": t} for t in anchor_texts])
        anchor_tok = anchor_ds.map(fmt_anchor,
                                    remove_columns=anchor_ds.column_names)
        # Interleave at dataset level (shuffle after concat).
        # Beam's rule: match replay content to PPL eval distribution.
        # Both come from wikitext-2-raw, so the signal is clean.
        train_tok = concatenate_datasets(
            [train_tok, anchor_tok]).shuffle(seed=seed)
        print(f"Mixed train set: {len(train_tok)} items "
              f"({len(train_ds)} security + {len(anchor_ds)} anchor)")

    # 6. Held-out general eval (wikitext TEST split — distinct from anchor)
    general_eval_texts = load_general_eval_texts(n=200)

    # 7. Training arguments
    out_dir = f"./{cfg['name']}_out"
    training_args = TrainingArguments(
        output_dir=out_dir,
        num_train_epochs=cfg["epochs"],
        per_device_train_batch_size=cfg["per_device_train_batch_size"],
        per_device_eval_batch_size=8,
        gradient_accumulation_steps=cfg["gradient_accumulation_steps"],
        learning_rate=cfg["lr"],
        lr_scheduler_type=cfg["lr_scheduler"],
        lr_scheduler_kwargs=cfg.get("lr_scheduler_kwargs") or {},
        warmup_ratio=cfg["warmup_ratio"],
        max_grad_norm=cfg["max_grad_norm"],
        weight_decay=cfg["weight_decay"],
        label_smoothing_factor=cfg["label_smoothing"],
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        bf16=True,
        load_best_model_at_end=True,
        metric_for_best_model=cfg["eval_metric"],
        greater_is_better=cfg["greater_is_better"],
        save_strategy="steps",
        eval_strategy="steps",
        save_steps=50,
        eval_steps=50,
        save_total_limit=4,
        logging_steps=10,
        report_to="none",
        seed=seed,
        remove_unused_columns=False,
    )

    # 8. Trainer with dual eval + composite early stopping
    #
    # Pass 3 used a single-metric early stop on eval_general_ppl with
    # patience=2. That was correct for detecting forgetting, but it fired
    # before code_vuln had converged (the mislabeling report shows the
    # adapter was too weak, not that it had overfit). Pass 4 uses a
    # COMPOSITE stop: continue training as long as EITHER the general PPL
    # is improving OR the security loss is improving by > min_delta. Only
    # stop when BOTH have plateaued for `patience` consecutive evals.
    from transformers import TrainerCallback
    class CompositeDualStop(TrainerCallback):
        def __init__(self, patience=3, min_delta=0.005, lower_is_better=True):
            self.patience = patience
            self.min_delta = min_delta
            self.lower_is_better = lower_is_better
            self.best_gen = float("inf") if lower_is_better else -float("inf")
            self.best_sec = float("inf") if lower_is_better else -float("inf")
            self.gen_stall = 0
            self.sec_stall = 0
        def on_evaluate(self, args, state, control, model=None,
                        metrics=None, **kwargs):
            if metrics is None: return
            gen = metrics.get("eval_general_ppl")
            sec = metrics.get("eval_loss")
            if gen is not None:
                if self.lower_is_better:
                    improved = (self.best_gen - gen) > self.min_delta
                else:
                    improved = (gen - self.best_gen) > self.min_delta
                if improved:
                    self.best_gen = gen; self.gen_stall = 0
                else:
                    self.gen_stall += 1
            if sec is not None:
                if self.lower_is_better:
                    improved_s = (self.best_sec - sec) > self.min_delta
                else:
                    improved_s = (sec - self.best_sec) > self.min_delta
                if improved_s:
                    self.best_sec = sec; self.sec_stall = 0
                else:
                    self.sec_stall += 1
            print(f"  [composite stop] gen_stall={self.gen_stall} "
                  f"(best_gen={self.best_gen:.4f}, cur_gen={gen}), "
                  f"sec_stall={self.sec_stall} "
                  f"(best_sec={self.best_sec:.4f}, cur_sec={sec})")
            # Stop only when BOTH have stalled for `patience`
            if (self.gen_stall >= self.patience
                    and self.sec_stall >= self.patience):
                print(f"  [composite stop] BOTH metrics stalled for "
                      f"{self.patience} evals — stopping.")
                control.should_training_stop = True

    callbacks = [
        EarlyStoppingCallback(
            early_stopping_patience=cfg["early_stopping_patience"],
            early_stopping_threshold=cfg.get("early_stopping_min_delta", 0.0)),
        make_dual_eval_callback(tokenizer, general_eval_texts),
    ]
    # Pass 4: add the composite dual-stop on top of the HF one. The HF
    # EarlyStoppingCallback only watches the single metric_for_best_model;
    # the composite adds the "BOTH must stall" gate.
    if cfg.get("composite_stop"):
        callbacks.append(CompositeDualStop(
            patience=cfg["early_stopping_patience"],
            min_delta=cfg.get("early_stopping_min_delta", 0.005)))

    # Pass 5: two-LR optimizer. Unfrozen base layers train at
    # unfreeze_base_lr (1e-6); LoRA + everything else at cfg lr (3e-5).
    # Mirrors HF Trainer's own group construction (decay vs no-decay on
    # LayerNorm/bias) but doubles the buckets by base-vs-adapter.
    trainer_cls = Trainer
    if cfg.get("unfreeze_last_n_layers") and cfg.get("unfreeze_base_lr"):
        base_lr = cfg["unfreeze_base_lr"]
        class SplitLRTrainer(Trainer):
            def create_optimizer(self):
                try:
                    import torch as _torch
                    from transformers.pytorch_utils import ALL_LAYERNORM_LAYERS
                    from transformers.trainer_pt_utils import get_parameter_names
                    decay_names = set(get_parameter_names(
                        self.model, [_torch.nn.LayerNorm], ALL_LAYERNORM_LAYERS))
                except Exception as e:
                    print(f"  [SplitLR] import fallback ({e}) — using default optimizer")
                    return super().create_optimizer()
                unf_from = getattr(self.model, "_n_unfrozen_from", None)
                if unf_from is None:
                    return super().create_optimizer()
                g = {"base_decay": [], "base_nodecay": [],
                     "other_decay": [], "other_nodecay": []}
                for pname, p in self.model.named_parameters():
                    if not p.requires_grad:
                        continue
                    is_base = False
                    if "lora_" not in pname and ".layers." in pname:
                        try:
                            idx = int(pname.split(".layers.")[1].split(".")[0])
                        except (ValueError, IndexError):
                            idx = -1
                        is_base = idx >= unf_from
                    bucket = "base" if is_base else "other"
                    wdb = "decay" if pname in decay_names else "nodecay"
                    g[f"{bucket}_{wdb}"].append(p)
                import torch as _torch
                param_groups = [
                    {"params": g["base_nodecay"], "weight_decay": 0.0,
                     "lr": base_lr},
                    {"params": g["base_decay"],
                     "weight_decay": self.args.weight_decay, "lr": base_lr},
                    {"params": g["other_nodecay"], "weight_decay": 0.0,
                     "lr": self.args.learning_rate},
                    {"params": g["other_decay"],
                     "weight_decay": self.args.weight_decay,
                     "lr": self.args.learning_rate},
                ]
                print(f"  [SplitLR] base_lr={base_lr} on "
                      f"{len(g['base_decay'])+len(g['base_nodecay'])} base "
                      f"params; adapter lr={self.args.learning_rate} on "
                      f"{len(g['other_decay'])+len(g['other_nodecay'])} params")
                self.optimizer = _torch.optim.AdamW(
                    param_groups, lr=self.args.learning_rate,
                    betas=(self.args.adam_beta1, self.args.adam_beta2),
                    eps=self.args.adam_epsilon)
                return self.optimizer
        trainer_cls = SplitLRTrainer

    trainer = trainer_cls(
        model=model,
        args=training_args,
        train_dataset=train_tok,
        eval_dataset=dev_tok,
        processing_class=tokenizer,
        data_collator=make_collator(tokenizer),
        callbacks=callbacks,
    )

    # 9. Measure PPL0 on the base model BEFORE training
    #    (adapter is initialized with B=0, so this is the true base PPL)
    print("\n--- Measuring PPL0 (reference, on wikitext TEST split) ---")
    base_for_ppl = (model.base_model.model if hasattr(model, "base_model")
                    else model)
    ppl0 = measure_perplexity(base_for_ppl, tokenizer,
                              general_eval_texts, max_samples=200)
    print(f"PPL0 (base, pre-training, wikitext test): {ppl0:.4f}")
    print(f"     ln(PPL0) = {math.log(ppl0):.4f} nats")
    print(f"     Gate target: PPL_after / PPL0 < {GENERAL_PPL_MAX_RATIO} "
          f"(i.e. Δln(PPL) < {math.log(GENERAL_PPL_MAX_RATIO):.4f} nats)")
    print(f"     NOTE: PPL0 is on raw wikitext (typical 0.5B range ~20-40).")
    print(f"     Pass 1's 306 was on ChatML-formatted security dev items —")
    print(f"     a specialized eval, NOT a comparable signal.")

    # 10. Train
    print("\n--- Starting training ---")
    train_result = trainer.train()
    print(f"\nTraining done. Final train loss: {train_result.training_loss:.4f}")

    # 11. Measure PPL after training (on the SAME wikitext test split)
    print("\n--- Measuring PPL after training (wikitext test) ---")
    ppl_after = measure_perplexity(base_for_ppl, tokenizer,
                                   general_eval_texts, max_samples=200)
    ppl_ratio = ppl_after / ppl0
    ppl_delta_nats = math.log(ppl_after) - math.log(ppl0)
    print(f"PPL after training: {ppl_after:.4f}")
    print(f"PPL ratio:  {ppl_ratio:.4f}  (gate: < {GENERAL_PPL_MAX_RATIO})")
    print(f"Δln(PPL):   {ppl_delta_nats:+.4f} nats")
    print(f"Δ PPL (%):  {(ppl_ratio-1)*100:+.2f}%")

    # 12. Save adapter
    adapter_dir = f"./sirius_lora_adapter_{cfg['name']}"
    model.save_pretrained(adapter_dir)
    tokenizer.save_pretrained(adapter_dir)
    print(f"\nAdapter saved -> {adapter_dir}")

    # 13. Merge adapter into base (for script 09 gate + script 08 quant)
    print("\n--- Merging adapter into base ---")
    merged_dir = f"./sirius_merged_{cfg['name']}"
    merged = model.merge_and_unload()
    merged.save_pretrained(merged_dir, safe_serialization=True)
    tokenizer.save_pretrained(merged_dir)
    print(f"Merged model saved -> {merged_dir}")

    # 14. Log
    gate_passed = ppl_ratio < GENERAL_PPL_MAX_RATIO
    log = {
        "pass": cfg["name"],
        "config": {k: v for k, v in cfg.items()
                   if k not in ("lr_scheduler_kwargs",)},
        "seed": seed,
        "ppl0_reference": ppl0,
        "ppl0_nats": math.log(ppl0),
        "ppl_after_training": ppl_after,
        "ppl_after_nats": math.log(ppl_after),
        "ppl_ratio": ppl_ratio,
        "ppl_delta_nats": ppl_delta_nats,
        "ppl_delta_pct": (ppl_ratio - 1) * 100,
        "gate_threshold_ratio": GENERAL_PPL_MAX_RATIO,
        "gate_threshold_nats": math.log(GENERAL_PPL_MAX_RATIO),
        "gate_passed": gate_passed,
        "train_loss": train_result.training_loss,
        "train_samples_security": len(train_ds),
        "train_samples_anchor": len(anchor_texts) if anchor_texts else 0,
        "train_samples_total": len(train_tok),
        "dev_samples": len(dev_ds),
        "adapter_dir": adapter_dir,
        "merged_dir": merged_dir,
        "next_step": (
            "PASS — run 09_eval_gate.py for the dual-gate confirmation + "
            "adapter scaling sweep (s∈{1.0,0.5,0.25}), then 08_prune_quantize_colab.py"
            if gate_passed else
            "FAIL — escalate per runbook §Pass 3 escalation ladder "
            "(3b: +20% anchor / 3c: r=4 / 3d: r=64 attention / "
            "3e: partial unfreeze / 4: synthetic replay). "
            "Or run --grid for the 6-point lr×epochs sweep."
        ),
    }
    log_path = f"./sirius_train_log_{cfg['name']}.json"
    with open(log_path, "w") as f:
        json.dump(log, f, indent=2, default=str)
    print(f"\nLog saved -> {log_path}")

    print("\n" + "=" * 70)
    if gate_passed:
        print(f"GATE PASSED (PPL ratio {ppl_ratio:.4f} < {GENERAL_PPL_MAX_RATIO})")
        print(f"  Δ = {ppl_delta_nats:+.4f} nats  "
              f"({(ppl_ratio-1)*100:+.2f}%)")
        print(f"Next: 09_eval_gate.py --adapter {adapter_dir} "
              f"--merged {merged_dir}")
        print(f"      (dual-gate + free adapter-scaling sweep "
              f"s∈{{1.0,0.5,0.25}} — no retraining)")
    else:
        print(f"GATE FAILED (PPL ratio {ppl_ratio:.4f} ≥ {GENERAL_PPL_MAX_RATIO})")
        print(f"  PPL0={ppl0:.2f}, PPL_after={ppl_after:.2f}, "
              f"Δ={ppl_delta_nats:+.3f} nats ({(ppl_ratio-1)*100:+.1f}%)")
        print(f"  REFRAME: 'X%' is misleading. In nats this is "
              f"{ppl_delta_nats:+.2f}.")
        print(f"  Pass-3 target was +{math.log(GENERAL_PPL_MAX_RATIO):.2f} nats.")
        print(f"  Escalation ladder (runbook §Pass 3 escalation):")
        print(f"    3b: anchor_ratio 0.20, r=8, lr=3e-5, 1 epoch")
        print(f"    3c: r=4, alpha=4, lr=2e-5, 1 epoch, 10% anchor")
        print(f"    3d: r=64, alpha=16, lr=1e-5, attention only (full-rank LoRA)")
        print(f"    3e: partial unfreeze last 4 layers + LoRA elsewhere, lr=5e-6")
        print(f"    4 : replay training (5K synthetic from base, 50/50 mix)")
        print(f"  OR: run --grid for the 6-point lr×epochs sweep (~1h T4).")
    print("=" * 70)
    return log

# ---------------------------------------------------------------------------
# 6-point grid sweep (optional, ~1h on T4)
# ---------------------------------------------------------------------------
GRID_LRS = [5e-5, 3e-5, 1e-5]
GRID_EPOCHS = [1, 2]

def run_grid(train_path="sirius_train.jsonl", dev_path="sirius_dev.jsonl",
             skip_install_check=False, seed=42):
    """Sweep lr ∈ {5e-5, 3e-5, 1e-5} × epochs ∈ {1, 2} with all other Pass 3
    settings held fixed. ~10 min × 6 = ~1h on T4. Recommended ONLY if Pass 3
    still fails the gate — isolates the lr/epoch levers from the capacity
    levers (per Beam's 'you're changing too much at once' point)."""
    print("=" * 70)
    print("SIRIUS 6-point grid: lr ∈ {5e-5, 3e-5, 1e-5} × epochs ∈ {1, 2}")
    print("All other settings = Pass 3 baseline. ~10 min × 6 = ~1h on T4.")
    print("=" * 70)
    results = []
    for lr in GRID_LRS:
        for ep in GRID_EPOCHS:
            tag = f"grid_lr{lr:g}_ep{ep}"
            print(f"\n\n=== Grid run: lr={lr}, epochs={ep} ({tag}) ===")
            # Inject grid config into PASSES
            base = next(p for p in PASSES if p["name"] == "pass3")
            grid_cfg = dict(base, name=tag, lr=lr, epochs=ep,
                            note=f"GRID: lr={lr}, epochs={ep}, other = Pass 3")
            PASSES.append(grid_cfg)
            log = train(tag, train_path, dev_path,
                        skip_install_check=True, seed=seed)
            results.append({
                "lr": lr, "epochs": ep, "tag": tag,
                "ppl0": log["ppl0_reference"],
                "ppl_after": log["ppl_after_training"],
                "ppl_ratio": log["ppl_ratio"],
                "ppl_delta_nats": log["ppl_delta_nats"],
                "gate_passed": log["gate_passed"],
                "train_loss": log["train_loss"],
            })

    print("\n" + "=" * 70)
    print("GRID SUMMARY")
    print("=" * 70)
    print(f"{'lr':<8} {'epochs':<8} {'PPL0':<8} {'PPL_after':<10} "
          f"{'ratio':<8} {'Δnats':<8} {'train_loss':<10} {'gate':<6}")
    for r in results:
        print(f"{r['lr']:<8g} {r['epochs']:<8} {r['ppl0']:<8.2f} "
              f"{r['ppl_after']:<10.2f} {r['ppl_ratio']:<8.4f} "
              f"{r['ppl_delta_nats']:<+8.3f} {r['train_loss']:<10.4f} "
              f"{'PASS' if r['gate_passed'] else 'FAIL':<6}")
    with open("./sirius_grid_summary.json", "w") as f:
        json.dump(results, f, indent=2)
    print("\nGrid summary saved -> ./sirius_grid_summary.json")
    print("Pick the lowest-lr / fewest-epoch config that passes the gate.")

# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pass-name", default="pass3",
                    help="pass1 (historical), pass2 (historical), pass3 (NEW)")
    ap.add_argument("--train", default="sirius_train.jsonl")
    ap.add_argument("--dev", default="sirius_dev.jsonl")
    ap.add_argument("--skip-install-check", action="store_true")
    ap.add_argument("--seed", type=int, default=42,
                    help="Random seed. Run 2 seeds before declaring a config "
                         "failed — PPL gates on 0.5B wobble ±10-15% across seeds.")
    ap.add_argument("--base-model", default=None,
                    help="HF dir to train on top of (chained passes). For "
                         "pass6: the pass5 s=0.5 merged dir from script 18.")
    ap.add_argument("--grid", action="store_true",
                    help="Run the 6-point grid (lr × epochs). ~1h on T4. "
                         "Use only if Pass 3 still fails the gate.")
    args = ap.parse_args()
    if args.grid:
        run_grid(args.train, args.dev, args.skip_install_check, args.seed)
    else:
        train(args.pass_name, args.train, args.dev,
              args.skip_install_check, args.seed, args.base_model)

if __name__ == "__main__":
    main()
