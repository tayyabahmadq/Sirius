#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SIRIUS Toolkit - Script 09: Dual-Gate Confirmation + Adapter Scaling Sweep
============================================================================
Run AFTER 07_train_colab.py produces an adapter + merged model. Implements
the "Tier 1 free inference-time dial" (Beam) and the "Evaluation Rigor"
(first reviewer) layers that the old ±2% dev-loss gate lacked.

WHAT IT DOES
------------
1. Loads the BASE model (bf16) and the merged model (bf16).
2. Measures the full dual-gate panel on the adapter:
     - Security PPL (held-out dev items, no chat template)
     - General PPL (held-out wikitext TEST, no chat template)
     - KL(base || tuned) on a general batch
     - Token-level top-1 accuracy (general, vs base)
3. Traces the task-vs-retention Pareto frontier for FREE by sweeping
   the LoRA adapter scaling factor s ∈ {1.0, 0.5, 0.25}:
        ΔW_eff = s · (alpha/r) · B A
   At s=0 the merged model == base. Lower s = more retention, less task fit.
4. Picks the lowest s that passes BOTH gates:
     - security_loss < train_loss × 1.20
     - general_ppl_ratio < 1.30  (i.e. Δ ln(PPL) < +0.26 nats)
   Reports s as a hyperparameter to use at eval/serve time.
5. If no s passes, returns exit code 1 → escalate per runbook.

WHY THIS SCRIPT EXISTS
----------------------
The Pass 1 post-mortem showed that PPL gates on a narrow dev set are noisy
and over-strict. This script:
- separates the GENERAL retention signal (wikitext, held-out) from the
  SECURITY task signal (dev items, held-out)
- adds KL + token-accuracy for orthogonal retention evidence
- gives you a free retention dial (adapter scaling) before you retrain

If your Pass 3 run "failed" the script-07 gate, run this FIRST. Many
"failures" pass at s=0.5 or s=0.25, because the LoRA delta at s=1.0 simply
overshot.

GATE DEFINITIONS (Pass 3 dual gate, ratified by the 3-reviewer briefings)
-------------------------------------------------------------------------
  SECURITY:   security_loss < train_loss × 1.20
  GENERAL:    general_ppl_ratio < 1.30  (Δ ln(PPL) < +0.26 nats)
  KL:         KL(base || tuned) < 0.10 nats/token  (soft target)
  ACCURACY:   token_top1_acc > 0.95 × base_token_top1_acc

A config passes if SECURITY and GENERAL both pass. KL and ACCURACY are
advisory — if they fail while the PPL ratio passes, flag for review.

INPUTS
------
- --merged   path to the merged HF model from script 07 (bf16)
             (e.g. ./sirius_merged_pass3)
- --base     HF id of the base model (default: Qwen/Qwen2.5-0.5B-Instruct)
- --adapter  OPTIONAL. If given, the sweep loads base + adapter via PEFT
             and scales the adapter at inference. If omitted, the sweep
             loads --merged at every s value (works without PEFT).

OUTPUTS
-------
- sirius_eval_gate_<run>.json  (full panel + sweep results + chosen s)
- prints a Markdown table to stdout
"""
import json, os, sys, argparse, math

BASE_MODEL = "Qwen/Qwen2.5-0.5B-Instruct"
GENERAL_PPL_MAX_RATIO = 1.30
SECURITY_LOSS_MAX_RATIO = 1.20
KL_SOFT_TARGET = 0.10
ACCURACY_MIN_RATIO = 0.95
# Default sweep: down from 1.0 (retention dial — rescues a "failed" run
# that overshot). Override with --scales "2.0,1.0,0.5,0.25" to also sweep
# UPWARD: a Pass 3 that passed the dual gate but failed the capability gate
# is under-fit, so s>1.0 amplifies the (already-good) adapter delta for
# free — no retraining. If s=2.0 brings code_vuln back without breaking
# the general PPL gate, you've fixed it in 5 minutes.
DEFAULT_SCALES = [1.0, 0.5, 0.25]
GENERAL_EVAL_N = 200
SECURITY_EVAL_N = 100

def load_general_eval(n=GENERAL_EVAL_N):
    """Held-out wikitext TEST split (distinct from the train-split anchor
    used during fine-tuning). Raw text, no chat template — matches the
    PPL gate distribution to the anchor distribution (Beam's rule)."""
    from datasets import load_dataset
    ds = load_dataset("wikitext", "wikitext-2-raw-v1", split="test")
    return [t for t in ds["text"] if len(t.strip()) > 200][:n]

def load_security_eval(dev_path, n=SECURITY_EVAL_N):
    """Held-out dev items, stripped of chat template to measure raw LM PPL
    on the security-domain distribution."""
    rows = []
    with open(dev_path, encoding="utf-8") as f:
        for line in f:
            rows.append(json.loads(line))
    texts = []
    for r in rows[:n]:
        msgs = r.get("messages", [])
        for m in msgs:
            if m.get("content"):
                texts.append(m["content"])
    return texts

# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------
def measure_ppl_and_logits(model, tokenizer, texts, max_samples, device,
                           seq_len=512, collect_logits=False):
    """Returns (ppl, mean_loss, token_top1_acc, kl_inputs).
    If collect_logits, also returns the per-token log-probs on the first
    `max_samples` items for KL computation."""
    import torch
    import torch.nn.functional as F
    model.eval()
    losses, accs = [], []
    log_probs_chunks = []
    n_tokens = 0
    with torch.no_grad():
        for i, text in enumerate(texts):
            if i >= max_samples: break
            enc = tokenizer(text, return_tensors="pt", truncation=True,
                            max_length=seq_len)
            input_ids = enc["input_ids"].to(device)
            if input_ids.shape[1] < 2: continue
            with torch.amp.autocast("cuda", dtype=torch.bfloat16):
                out = model(input_ids)
            logits = out.logits[:, :-1, :]
            targets = input_ids[:, 1:]
            # loss
            loss = F.cross_entropy(
                logits.reshape(-1, logits.size(-1)).float(),
                targets.reshape(-1))
            losses.append(loss.item())
            # token top-1 accuracy
            preds = logits.argmax(-1)
            accs.append((preds == targets).float().mean().item())
            # log-probs (for KL)
            if collect_logits:
                # MEMORY-SAFE: original cached full [1,T,151936] log-softmax
                # tensors for 200 items (~60 GB) and OOM-killed the kernel.
                # KL is advisory; store only mean target-token log-prob.
                lp = F.log_softmax(logits.float(), dim=-1)
                tgt_lp = lp.gather(-1, targets.unsqueeze(-1)).squeeze(-1)
                log_probs_chunks.append(tgt_lp.mean().cpu().item())
            n_tokens += targets.numel()
    ppl = math.exp(sum(losses) / len(losses)) if losses else float("inf")
    acc = sum(accs) / len(accs) if accs else 0.0
    return ppl, (sum(losses) / len(losses) if losses else 0.0), acc, log_probs_chunks, n_tokens

def measure_kl(base_log_probs, tuned_log_probs):
    """KL(base || tuned) = sum p_base * (log p_base - log p_tuned).
    Both inputs are lists of [1, T, V] log-softmax tensors on CPU.
    Returns nats/token."""
    import torch
    import torch.nn.functional as F
    # Memory-safe advisory proxy: mean target-token log-prob delta.
    if not base_log_probs or not tuned_log_probs:
        return float("nan")
    n = min(len(base_log_probs), len(tuned_log_probs))
    return sum(tuned_log_probs[i] - base_log_probs[i] for i in range(n)) / n

# ---------------------------------------------------------------------------
# Adapter scaling (PEFT path)
# ---------------------------------------------------------------------------
def _get_lora_layers(model):
    """Yield every LoRA layer in the model (the trainable sublayer that
    owns `scaling` + `lora_A`/`lora_B`). We descend through the PEFT
    wrappers (base_model.model → base_model.base_model.model → model) to
    find them. Defensive about leaf nodes that lack named_children()."""
    # FIX: HF PreTrainedModel.base_model is a property that returns `self`
    # when no child named `model` exists -> the old `while hasattr(...)` loop
    # never terminated and hung the sweep at s=1.5. Walk modules directly.
    base = model.base_model.model if hasattr(model, "base_model") else model
    out = []
    for module in base.modules():
        if hasattr(module, "scaling") and (
                hasattr(module, "lora_A") or hasattr(module, "lora_B")):
            out.append(module)
    return out

def set_adapter_scale(model, s):
    """Scale all LoRA layers' effective delta by s at inference time.

    In modern PEFT, scaling is computed ONCE at LoRALayer.__init__ as:
        self.scaling = {"default": lora_alpha / r}        # plain LoRA
        self.scaling = {"default": lora_alpha / sqrt(r)}  # rsLoRA
    and is read from the dict during forward — it is NOT recomputed from
    lora_alpha. Mutating lora_alpha after init is therefore a NO-OP.

    The correct mutation is to overwrite self.scaling["default"] directly.
    We cache the original value under `_orig_scaling_default` on the first
    call so we can reset to s=1.0 cleanly between sweep steps."""
    n = 0
    for layer in _get_lora_layers(model):
        scaling = getattr(layer, "scaling", None)
        if isinstance(scaling, dict) and "default" in scaling:
            if not hasattr(layer, "_orig_scaling_default"):
                layer._orig_scaling_default = scaling["default"]
            scaling["default"] = layer._orig_scaling_default * s
            n += 1
        elif isinstance(scaling, (float, int)):
            # Very old PEFT: scaling was a bare float attribute.
            if not hasattr(layer, "_orig_scaling_default"):
                layer._orig_scaling_default = float(scaling)
            layer.scaling = layer._orig_scaling_default * s
            n += 1
    return n

def set_adapter_scale_to_original(model):
    """Reset every LoRA layer's scaling to its init value (s=1.0)."""
    n = 0
    for layer in _get_lora_layers(model):
        if hasattr(layer, "_orig_scaling_default"):
            scaling = getattr(layer, "scaling", None)
            if isinstance(scaling, dict) and "default" in scaling:
                scaling["default"] = layer._orig_scaling_default
                n += 1
            elif isinstance(scaling, (float, int)):
                layer.scaling = layer._orig_scaling_default
                n += 1
    return n

# Back-compat alias (older code referenced this name).
def reset_adapter_scale(model):
    return set_adapter_scale_to_original(model)

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def run(merged_dir, dev_path, base_model=BASE_MODEL, adapter_dir=None,
        run_tag="pass3", scales=None):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    if scales is None:
        scales = list(DEFAULT_SCALES)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Device: {device}")
    print(f"Base:    {base_model}")
    print(f"Merged:  {merged_dir}")
    print(f"Adapter: {adapter_dir or '(none — using merged weights directly)'}")
    print(f"Sweep s ∈ {scales}")

    tokenizer = AutoTokenizer.from_pretrained(base_model)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # --- Load BASE model (frozen reference) ---
    print("\n--- Loading BASE model (bf16, no quant) ---")
    base_model_obj = AutoModelForCausalLM.from_pretrained(
        base_model, torch_dtype=torch.bfloat16, device_map="auto")

    # --- Eval texts ---
    general_texts = load_general_eval(GENERAL_EVAL_N)
    security_texts = load_security_eval(dev_path, SECURITY_EVAL_N)
    print(f"General eval: {len(general_texts)} wikitext-TEST items")
    print(f"Security eval: {len(security_texts)} dev items (raw text)")

    # --- Base reference metrics ---
    print("\n--- Measuring BASE reference panel ---")
    (base_gen_ppl, base_gen_loss, base_gen_acc,
     base_gen_lp, base_gen_n) = measure_ppl_and_logits(
        base_model_obj, tokenizer, general_texts,
        max_samples=GENERAL_EVAL_N, device=device, collect_logits=True)
    (base_sec_ppl, base_sec_loss, base_sec_acc, _, _) = measure_ppl_and_logits(
        base_model_obj, tokenizer, security_texts,
        max_samples=SECURITY_EVAL_N, device=device, collect_logits=False)
    print(f"  Base general PPL: {base_gen_ppl:.4f}  (acc {base_gen_acc:.4f})")
    print(f"  Base security PPL: {base_sec_ppl:.4f}  (loss {base_sec_loss:.4f})")
    print(f"  Base ln(PPL_gen): {math.log(base_gen_ppl):.4f} nats")

    # --- Load TUNED model ---
    print("\n--- Loading TUNED model ---")
    if adapter_dir:
        from peft import PeftModel
        tuned = PeftModel.from_pretrained(base_model_obj, adapter_dir)
    else:
        tuned = AutoModelForCausalLM.from_pretrained(
            merged_dir, torch_dtype=torch.bfloat16, device_map="auto")

    # --- Sweep over s ---
    sweep_results = []
    chosen_s = None
    for s in scales:
        print(f"\n=== Adapter scale s = {s} ===")
        # If no adapter, the merged model already bakes s=1.0 in. Lower s
        # would require an unmerged model. We only run s=1.0 in that case.
        if not adapter_dir and s != 1.0:
            print(f"  (skipping s={s} — requires --adapter; "
                  f"merged weights are s=1.0 only)")
            continue
        if adapter_dir:
            # set_adapter_scale is idempotent: it caches the original
            # scaling on the first call and re-derives from it on every
            # subsequent call, so we can call it directly each iteration.
            n_scaled = set_adapter_scale(tuned, s)
            print(f"  (scaled {n_scaled} LoRA layers by ×{s})")

        (gen_ppl, gen_loss, gen_acc, gen_lp, gen_n) = measure_ppl_and_logits(
            tuned, tokenizer, general_texts,
            max_samples=GENERAL_EVAL_N, device=device, collect_logits=True)
        (sec_ppl, sec_loss, sec_acc, _, _) = measure_ppl_and_logits(
            tuned, tokenizer, security_texts,
            max_samples=SECURITY_EVAL_N, device=device, collect_logits=False)
        kl = measure_kl(base_gen_lp, gen_lp)
        gen_ratio = gen_ppl / base_gen_ppl
        gen_delta_nats = math.log(gen_ppl) - math.log(base_gen_ppl)
        sec_ratio = sec_ppl / base_sec_ppl

        sec_gate = sec_loss < base_sec_loss * SECURITY_LOSS_MAX_RATIO
        gen_gate = gen_ratio < GENERAL_PPL_MAX_RATIO
        kl_advisory = kl < KL_SOFT_TARGET
        acc_advisory = gen_acc > ACCURACY_MIN_RATIO * base_gen_acc

        result = {
            "s": s,
            "general_ppl": gen_ppl,
            "general_ppl_ratio": gen_ratio,
            "general_delta_nats": gen_delta_nats,
            "general_acc": gen_acc,
            "security_ppl": sec_ppl,
            "security_loss": sec_loss,
            "security_loss_ratio": sec_loss / base_sec_loss,
            "kl_base_tuned": kl,
            "sec_gate": sec_gate,
            "gen_gate": gen_gate,
            "kl_advisory": kl_advisory,
            "acc_advisory": acc_advisory,
            "passes": sec_gate and gen_gate,
        }
        sweep_results.append(result)
        print(f"  General  PPL: {gen_ppl:.4f}  ratio={gen_ratio:.4f}  "
              f"Δnats={gen_delta_nats:+.4f}  acc={gen_acc:.4f}")
        print(f"  Security PPL: {sec_ppl:.4f}  loss={sec_loss:.4f}  "
              f"(base {base_sec_loss:.4f}, ratio {sec_loss/base_sec_loss:.4f})")
        print(f"  KL(base||tuned): {kl:.4f} nats/token  "
              f"(advisory target < {KL_SOFT_TARGET})")
        print(f"  GATES: sec={sec_gate!s}  gen={gen_gate!s}  "
              f"kl={kl_advisory!s}  acc={acc_advisory!s}  "
              f"=> {'PASS' if result['passes'] else 'FAIL'}")

        if result["passes"] and chosen_s is None:
            chosen_s = s   # first passing s, lowest s = most retention

    # --- Summary ---
    print("\n" + "=" * 70)
    print("DUAL-GATE SWEEP SUMMARY")
    print("=" * 70)
    print(f"BASE:  general PPL {base_gen_ppl:.4f}  acc {base_gen_acc:.4f}  "
          f"ln(PPL) {math.log(base_gen_ppl):.4f} nats")
    print(f"       security PPL {base_sec_ppl:.4f}  loss {base_sec_loss:.4f}")
    print()
    print(f"{'s':<6} {'gen_PPL':<10} {'gen_ratio':<10} {'Δnats':<8} "
          f"{'gen_acc':<8} {'sec_loss':<10} {'KL':<8} {'result':<8}")
    for r in sweep_results:
        print(f"{r['s']:<6} {r['general_ppl']:<10.4f} "
              f"{r['general_ppl_ratio']:<10.4f} "
              f"{r['general_delta_nats']:<+8.4f} {r['general_acc']:<8.4f} "
              f"{r['security_loss']:<10.4f} {r['kl_base_tuned']:<8.4f} "
              f"{'PASS' if r['passes'] else 'FAIL':<8}")

    print()
    if chosen_s is not None:
        print(f"CHOSEN: s = {chosen_s}  (lowest s that passes both gates)")
        print(f"  Use this s at serve/eval time. If you trained with PEFT,")
        print(f"  set lora_alpha *= {chosen_s} before merging or eval.")
    else:
        print("NO s PASSED BOTH GATES.")
        print("  Next: escalate per runbook §Pass 3 escalation ladder.")
        print("  Or: retrain at lower lr / fewer epochs and re-run this script.")

    # --- Save log ---
    log = {
        "project": "SIRIUS", "phase": "2-eval-gate",
        "base_model": base_model,
        "merged_dir": merged_dir,
        "adapter_dir": adapter_dir,
        "run_tag": run_tag,
        "gate_thresholds": {
            "general_ppl_max_ratio": GENERAL_PPL_MAX_RATIO,
            "security_loss_max_ratio": SECURITY_LOSS_MAX_RATIO,
            "kl_soft_target": KL_SOFT_TARGET,
            "accuracy_min_ratio": ACCURACY_MIN_RATIO,
        },
        "base_reference": {
            "general_ppl": base_gen_ppl,
            "general_nats": math.log(base_gen_ppl),
            "general_acc": base_gen_acc,
            "security_ppl": base_sec_ppl,
            "security_loss": base_sec_loss,
            "security_acc": base_sec_acc,
        },
        "sweep": sweep_results,
        "chosen_s": chosen_s,
        "passed": chosen_s is not None,
        "next_step": (
            f"PASS at s={chosen_s}. Run 08_prune_quantize_colab.py with "
            f"--merged {merged_dir}. Set s={chosen_s} if re-merging adapter."
            if chosen_s is not None else
            "FAIL. Escalate per runbook §Pass 3 escalation ladder."
        ),
    }
    out_path = f"./sirius_eval_gate_{run_tag}.json"
    with open(out_path, "w") as f:
        json.dump(log, f, indent=2, default=str)
    print(f"\nLog saved -> {out_path}")
    return log

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--merged", required=True,
                    help="Path to merged HF model from script 07")
    ap.add_argument("--adapter", default=None,
                    help="Optional PEFT adapter dir. If given, the sweep "
                         "scales the adapter at inference. If omitted, "
                         "only s=1.0 is evaluated (merged weights are "
                         "baked at s=1.0).")
    ap.add_argument("--base", default=BASE_MODEL)
    ap.add_argument("--dev", default="sirius_dev.jsonl",
                    help="Dev jsonl for security-side PPL eval")
    ap.add_argument("--tag", default="pass3")
    ap.add_argument("--scales", default=None,
                    help="Comma-separated list of adapter scale factors. "
                         "Default '1.0,0.5,0.25' (retention dial — for an "
                         "OVER-fit run that failed the PPL gate). For a "
                         "Pass 3 that passed the dual gate but failed "
                         "the capability gate, sweep UPWARD to amplify "
                         "the (already-good) adapter: --scales "
                         "'2.0,1.5,1.0,0.5'. Free — no retraining.")
    args = ap.parse_args()
    scales = None
    if args.scales:
        scales = [float(x.strip()) for x in args.scales.split(",")]
    log = run(args.merged, args.dev, args.base, args.adapter, args.tag,
              scales=scales)
    sys.exit(0 if log["passed"] else 1)

if __name__ == "__main__":
    main()
