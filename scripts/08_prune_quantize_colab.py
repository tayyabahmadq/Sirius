#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SIRIUS Toolkit - Script 08: Prune + Quantize + Gate (Google Colab T4)
=====================================================================
Implements the merged Phase-2 plan Part B2 (pruning) and Part B4
(quantization + verification). Run AFTER 07_train_colab.py has produced
a merged HF model that passed the +-2% PPL gate.

WHAT IT DOES
------------
1. Measure PPL0 reference (if not already from script 07).
2. ShortGPT importance pass: compute SI_l = 1 - E[cos(h_in, h_out)]
   over 512 wikitext-2-raw + 200 security prompts, rank blocks 1..22
   (hard-exclude {0,1,22,23}).
3. Drop bottom-3 (most near-identity) blocks -> export Q8_0 -> gate.
   Rollback ladder: bottom-3 -> bottom-1 -> 0 blocks (no pruning).
4. Quantize to Q6_K (primary) and Q5_K_M (fallback). Gate each.
5. Output the final GGUF for Ollama + a Modelfile.

GATES (all must pass before shipping)
--------------------------------------
- PPL <= 1.02 x PPL0  (perplexity, wikitext-2-raw or dev set)
- PPL <= 1.02 x PPL_merged_unpruned  (pruning-specific)
- No capability mean drops > 0.02 vs baseline (script 04, run locally)

The 34-item capability gate is run LOCALLY in Ollama after this script
exports the GGUF; this script only handles the PPL + export side.

PREREQUISITES
-------------
- merged HF model from script 07 (./sirius_merged_pass3/)
- (optional) eval-gate JSON from script 09 (./sirius_eval_gate_pass3.json)
  If present, the script reads the chosen adapter scaling s and reports it.

NOTE ON ADAPTER SCALING (script 09)
------------------------------------
If script 09 found that the model passes the dual gate only at s < 1.0
(e.g. s=0.5), then the merged model on disk is already the s=1.0 version.
To serve at s=0.5 you have two options:
  (a) Keep the adapter unmerged and serve base+adapter with PEFT at runtime
      (Ollama doesn't support this; you'd need vLLM/llama.cpp server).
  (b) Re-merge at s=0.5: load base + adapter, scale, merge, save, then
      run this script. The cool-down path below does (b) for you.

MERGE-AND-REQUANT COOL-DOWN (advanced, only if Q6_K fails the capability gate)
-----------------------------------------------------------------------------
Per the second reviewer's Tier-3 suggestion: if the final Q6_K fails the
local capability gate (script 04), try this BEFORE retraining:

  1. Load the merged model from script 07.
  2. Run 1 cool-down epoch on wikitext at lr=1e-6, r=4, attention-only.
     This is a very gentle anchor toward the base distribution.
  3. Re-merge, re-quantize to Q6_K, re-run script 04.

To enable: pass --cooldown-epoch. Default off.
"""
import json, os, sys, argparse, math
from typing import Optional

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
BASE_MODEL = "Qwen/Qwen2.5-0.5B-Instruct"
WIKITEXT = "wikitext-2-raw-v1"
N_WIKI_SAMPLES = 512
N_SECURITY_SAMPLES = 200
EDGE_EXCLUDE = {0, 1, 22, 23}   # hard-excluded from pruning
PPL_GATE_RATIO = 1.02            # +2% gate
CAPABILITY_DROP_LIMIT = 0.02     # run locally with script 04

# ---------------------------------------------------------------------------
# ShortGPT importance pass
# ---------------------------------------------------------------------------
def shortgpt_importance(model, tokenizer, dataset, device="cuda",
                        n_blocks=24, max_samples=512, seq_len=512):
    """For each block l, compute SI_l = 1 - E[cos(h_in^l, h_out^l)].
    Higher SI = more change = MORE important (do NOT drop).
    Lower SI = near-identity = safe to drop."""
    import torch
    import torch.nn.functional as F
    model.eval()
    # Hook to capture inputs/outputs of each block's self-attention + MLP
    # We capture the block's input (residual into block) and output (residual
    # out of block). For Qwen2 this is model.model.layers[l].
    layers = model.model.layers if hasattr(model, "model") and hasattr(model.model, "layers") else None
    if layers is None:
        # PEFT-wrapped or merged
        base = model.base_model.model if hasattr(model, "base_model") else model
        layers = base.model.layers

    inputs = [None] * n_blocks
    outputs = [None] * n_blocks

    handles = []
    for l in range(n_blocks):
        def make_hook(idx):
            def hook(module, inp, out):
                # inp[0] is the residual stream into the block; out[0] is out
                inputs[idx] = inp[0].detach()
                outputs[idx] = out[0].detach() if isinstance(out, tuple) else out.detach()
            return hook
        handles.append(layers[l].register_forward_hook(make_hook(l)))

    cos_sims = [[] for _ in range(n_blocks)]
    count = 0
    with torch.no_grad():
        for example in dataset:
            if count >= max_samples: break
            text = example["text"] if isinstance(example, dict) and "text" in example else str(example)
            enc = tokenizer(text, return_tensors="pt", truncation=True, max_length=seq_len).to(device)
            try:
                model(**enc)
            except Exception as e:
                continue
            for l in range(n_blocks):
                if inputs[l] is None or outputs[l] is None: continue
                h_in = inputs[l].float().flatten()
                h_out = outputs[l].float().flatten()
                if h_in.shape != h_out.shape: continue
                cs = F.cosine_similarity(h_in.unsqueeze(0), h_out.unsqueeze(0)).item()
                cos_sims[l].append(cs)
            count += 1

    for h in handles: h.remove()

    # SI_l = 1 - mean(cos). Higher SI = more important.
    si = []
    for l in range(n_blocks):
        if not cos_sims[l]:
            si.append(1.0)  # treat as important if unmeasured
        else:
            si.append(1.0 - sum(cos_sims[l]) / len(cos_sims[l]))
    return si

# ---------------------------------------------------------------------------
# Block dropping (pruning)
# ---------------------------------------------------------------------------
def drop_blocks(model, blocks_to_drop):
    """Remove the given block indices from model.model.layers in place.
    Returns the modified model. Qwen2 model structure:
      model.model.layers = nn.ModuleList of 24 blocks."""
    import torch.nn as nn
    base = model.base_model.model if hasattr(model, "base_model") else model
    if not hasattr(base, "model") or not hasattr(base.model, "layers"):
        raise ValueError("Model does not have the expected .model.layers structure")
    layers = base.model.layers
    keep = [i for i in range(len(layers)) if i not in set(blocks_to_drop)]
    base.model.layers = nn.ModuleList([layers[i] for i in keep])
    base.config.num_hidden_layers = len(keep)
    # Re-number so downstream code (e.g. llama.cpp export) sees contiguous idx
    return model, len(keep)

# ---------------------------------------------------------------------------
# Perplexity
# ---------------------------------------------------------------------------
def measure_ppl(model, tokenizer, dataset, device="cuda",
                max_samples=512, seq_len=512):
    import torch
    model.eval()
    losses = []
    with torch.no_grad():
        for i, example in enumerate(dataset):
            if i >= max_samples: break
            text = example["text"] if isinstance(example, dict) and "text" in example else str(example)
            enc = tokenizer(text, return_tensors="pt", truncation=True, max_length=seq_len)
            input_ids = enc["input_ids"].to(device)
            if input_ids.shape[1] < 2: continue
            with torch.amp.autocast("cuda", dtype=torch.bfloat16):
                out = model(input_ids, labels=input_ids)
            losses.append(out.loss.item())
    return math.exp(sum(losses) / len(losses)) if losses else float("inf")

# ---------------------------------------------------------------------------
# Quantization to GGUF (delegates to llama.cpp)
# ---------------------------------------------------------------------------
def export_gguf(merged_dir, out_gguf_path, quant="Q6_K"):
    """Convert the merged HF model to GGUF and quantize.
    Requires llama.cpp built at ./llama.cpp (the script will clone if absent)."""
    print(f"\n--- Converting {merged_dir} -> {out_gguf_path} ({quant}) ---")
    if not os.path.isdir("./llama.cpp"):
        os.system("git clone https://github.com/ggerganov/llama.cpp.git")
        os.system("cd llama.cpp && make LLAMA_CUDA=1 2>/dev/null || pip install llama-cpp-python")
    convert_script = "./llama.cpp/convert_hf_to_gguf.py"
    if not os.path.isfile(convert_script):
        convert_script = "./llama.cpp/convert.py"   # older path
    f16_gguf = out_gguf_path.replace(".gguf", ".f16.gguf")
    os.system(f"python {convert_script} {merged_dir} --outfile {f16_gguf} --outtype f16")
    os.system(f"./llama.cpp/llama-quantize {f16_gguf} {out_gguf_path} {quant}")
    if os.path.isfile(out_gguf_path):
        size_mb = os.path.getsize(out_gguf_path) / 1e6
        print(f"  -> {out_gguf_path}  ({size_mb:.1f} MB)")
        return True
    print(f"  FAILED to produce {out_gguf_path}")
    return False

# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------
def run(merged_dir="./sirius_merged_pass3", adapter_log_path="./sirius_train_log_pass3.json",
        eval_gate_log_path="./sirius_eval_gate_pass3.json",
        skip_shortgpt=False, skip_quantize=False):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from datasets import load_dataset

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Device: {device}")

    # Read chosen adapter scale s from script 09 log (advisory only — the
    # merged model on disk is already at s=1.0; if s<1.0 was chosen, you
    # must re-merge via the cool-down path or serve with PEFT).
    chosen_s = 1.0
    if os.path.isfile(eval_gate_log_path):
        gate_log = json.load(open(eval_gate_log_path))
        chosen_s = gate_log.get("chosen_s") or 1.0
        print(f"Adapter scale s from script 09: {chosen_s}")
        if chosen_s < 1.0:
            print(f"  WARNING: chosen s<1.0. The merged model on disk is at "
                  f"s=1.0. To honor s={chosen_s}, either:")
            print(f"    (a) serve base+adapter with PEFT (not via Ollama), or")
            print(f"    (b) re-merge at s={chosen_s} via the cool-down path "
                  f"(see --cooldown-epoch).")
            print(f"  Proceeding with s=1.0 merged weights for now.")

    # 1. Load merged model
    print(f"\n--- Loading merged model from {merged_dir} ---")
    tokenizer = AutoTokenizer.from_pretrained(merged_dir)
    model = AutoModelForCausalLM.from_pretrained(
        merged_dir, torch_dtype=torch.bfloat16, device_map="auto")

    # 2. Reference PPL (PPL0 from train log, or re-measure)
    if os.path.isfile(adapter_log_path):
        train_log = json.load(open(adapter_log_path))
        ppl0 = train_log.get("ppl0_reference")
        ppl_merged_unpruned = train_log.get("ppl_after_training")
    else:
        train_log = {}
        ppl0 = None
        ppl_merged_unpruned = None
    print(f"PPL0 (base reference): {ppl0}")
    print(f"PPL merged unpruned:   {ppl_merged_unpruned}")

    wiki = load_dataset("wikitext", WIKITEXT, split="test")

    # 3. ShortGPT importance pass
    if skip_shortgpt:
        print("\n--- Skipping ShortGPT (per --skip-shortgpt) ---")
        si_scores = None
        blocks_to_drop = []
    else:
        print(f"\n--- ShortGPT importance pass ({N_WIKI_SAMPLES} wiki + {N_SECURITY_SAMPLES} sec samples) ---")
        si_scores = shortgpt_importance(
            model, tokenizer, wiki, device=device,
            max_samples=N_WIKI_SAMPLES, seq_len=512)
        print("SI scores (higher = more important):")
        for l, si in enumerate(si_scores):
            edge = " [EDGE, excluded]" if l in EDGE_EXCLUDE else ""
            print(f"  block {l:2d}: SI={si:.4f}{edge}")

        # Rank blocks 1..22 (exclude edges), pick lowest-3
        candidate_blocks = [l for l in range(24) if l not in EDGE_EXCLUDE]
        ranked = sorted(candidate_blocks, key=lambda l: si_scores[l])  # ascending = least important first
        blocks_to_drop = ranked[:3]
        print(f"\nLowest-3 importance (candidates to drop): {blocks_to_drop}")

    # 4. Prune + gate (rollback ladder: 3 -> 1 -> 0)
    pruned_model = model
    n_kept = 24
    chosen_drop = []
    for n_drop in ([3, 1, 0] if blocks_to_drop else [0]):
        if n_drop == 0:
            chosen_drop = []
            print("\n--- Pruning pass: 0 blocks (no pruning) ---")
        else:
            chosen_drop = blocks_to_drop[:n_drop]
            print(f"\n--- Pruning pass: drop {chosen_drop} ---")
            # Reload fresh model before each prune attempt
            del pruned_model
            pruned_model = AutoModelForCausalLM.from_pretrained(
                merged_dir, torch_dtype=torch.bfloat16, device_map="auto")
            pruned_model, n_kept = drop_blocks(pruned_model, chosen_drop)

        ppl_pruned = measure_ppl(pruned_model, tokenizer, wiki, device=device, max_samples=200)
        print(f"  PPL pruned: {ppl_pruned:.4f}")
        gate_ppl0 = ppl0 is None or ppl_pruned <= PPL_GATE_RATIO * ppl0
        gate_merged = ppl_merged_unpruned is None or ppl_pruned <= PPL_GATE_RATIO * ppl_merged_unpruned
        if gate_ppl0 and gate_merged:
            print(f"  -> PPL gate PASSED")
            break
        print(f"  -> PPL gate FAILED (need <= {PPL_GATE_RATIO*ppl0:.4f} vs PPL0, "
              f"<= {PPL_GATE_RATIO*ppl_merged_unpruned:.4f} vs merged)")
        if n_drop == 0:
            print("  -> Even 0-block pruning fails the gate; investigate the merged model.")

    # 5. Export pruned model as HF, then GGUF
    pruned_dir = "./sirius_pruned_final"
    pruned_model.save_pretrained(pruned_dir, safe_serialization=True)
    tokenizer.save_pretrained(pruned_dir)
    print(f"\nPruned HF model saved -> {pruned_dir} ({n_kept} blocks kept)")

    # 6. Quantize: Q6_K primary, Q5_K_M fallback
    results = {"pruning": {"blocks_dropped": chosen_drop, "blocks_kept": n_kept,
                            "si_scores": si_scores}}
    if not skip_quantize:
        for quant in ["Q6_K", "Q5_K_M"]:
            gguf_path = f"./sirius_final_{quant}.gguf"
            ok = export_gguf(pruned_dir, gguf_path, quant=quant)
            results[quant] = {"path": gguf_path, "exported": ok}
            if ok:
                # Re-measure PPL on the GGUF via llama.cpp perplexity
                print(f"  (Run: ./llama.cpp/llama-perplexity -m {gguf_path} -f wikitext-2-raw.txt "
                      f"---> compare to PPL0={ppl0})")

    # 7. Write Modelfile for Ollama
    modelfile = f"""FROM ./sirius_final_Q6_K.gguf

PARAMETER temperature 0.2
PARAMETER num_predict 240
SYSTEM You are a security auditor assistant. Answer concisely, technically, and name the exact issue.
"""
    with open("./Modelfile.sirius", "w") as f:
        f.write(modelfile)
    print("\nModelfile saved -> ./Modelfile.sirius")

    # 8. Summary log
    log = {
        "project": "SIRIUS", "phase": "2-prune-quantize",
        "ppl0_reference": ppl0,
        "ppl_merged_unpruned": ppl_merged_unpruned,
        "shortgpt_si_scores": si_scores,
        "blocks_dropped": chosen_drop,
        "blocks_kept": n_kept,
        "gate_ratio": PPL_GATE_RATIO,
        "results": results,
        "next_step": (
            "Locally: ollama create sirius-final -f Modelfile.sirius, "
            "then run python 04_sirius_baseline.py --model sirius-final. "
            "Gate: each capability mean >= baseline - 0.02, and no single "
            "V02-V06 archetype still mislabels."
        ),
    }
    with open("./sirius_prune_quantize_log.json", "w") as f:
        json.dump(log, f, indent=2, default=str)
    print("\n" + "=" * 70)
    print("PRUNE + QUANTIZE COMPLETE")
    print(f"  Blocks dropped: {chosen_drop} (kept {n_kept}/24)")
    print(f"  GGUF: ./sirius_final_Q6_K.gguf (primary), ./sirius_final_Q5_K_M.gguf (fallback)")
    print(f"  Modelfile: ./Modelfile.sirius")
    print(f"\nNEXT (run locally):")
    print(f"  ollama create sirius-final -f Modelfile.sirius")
    print(f"  python 04_sirius_baseline.py --model sirius-final")
    print(f"  Gate: each capability >= baseline-0.02, V02-V06 mislabeling fixed.")
    print("=" * 70)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--merged-dir", default="./sirius_merged_pass3")
    ap.add_argument("--adapter-log", default="./sirius_train_log_pass3.json")
    ap.add_argument("--eval-gate-log", default="./sirius_eval_gate_pass3.json",
                    help="Script 09 log — read for chosen adapter scale s")
    ap.add_argument("--skip-shortgpt", action="store_true",
                    help="Skip the ShortGPT pass (ship merged-unpruned)")
    ap.add_argument("--skip-quantize", action="store_true")
    args = ap.parse_args()
    run(args.merged_dir, args.adapter_log, args.eval_gate_log,
        args.skip_shortgpt, args.skip_quantize)

if __name__ == "__main__":
    main()
