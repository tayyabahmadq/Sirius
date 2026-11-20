#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SIRIUS Toolkit — Script 18: Reconstruct a scaled merged base for chained passes
================================================================================
Phase 5 (pass6) must train ON TOP of the pass5 result, but Colab sessions
are ephemeral: the merged model dir rarely survives. This script rebuilds
it deterministically:

    base Qwen2.5-0.5B-Instruct  +  pass5 adapter  @  scale s  →  merged dir

It uses the SAME scaling mechanism as the gate script (09_eval_gate.py):
overwrite `scaling["default"]` on every LoRA layer — mutating lora_alpha
after init is a no-op in modern PEFT, because scaling is computed once
(alpha/r for plain LoRA, alpha/sqrt(r) for rsLoRA) and read from the dict
during forward.

Output: a plain HF model dir, ready for
    python 07_train_colab.py --pass-name pass6 --base-model <out-dir>

Usage (Colab):
    python 18_reconstruct_merged_base.py \
        --adapter-dir ./sirius_lora_pass5 \
        --scale 0.5 \
        --out ./sirius_merged_pass5_s05
"""
import os, sys, argparse


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-model", default="Qwen/Qwen2.5-0.5B-Instruct")
    ap.add_argument("--adapter-dir", required=True,
                    help="pass5 PEFT adapter dir (saved by 07)")
    ap.add_argument("--scale", type=float, default=0.5,
                    help="adapter scale for the merge (gate's winner; "
                         "s=0.5 shipped as sirius-final)")
    ap.add_argument("--out", default="./sirius_merged_pass5_s05")
    args = ap.parse_args()

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel

    print(f"Loading base: {args.base_model}")
    model = AutoModelForCausalLM.from_pretrained(
        args.base_model, torch_dtype=torch.bfloat16, device_map="cpu")
    tokenizer = AutoTokenizer.from_pretrained(args.base_model)

    print(f"Attaching adapter: {args.adapter_dir}")
    model = PeftModel.from_pretrained(model, args.adapter_dir)

    # Scale exactly like 09_eval_gate.set_adapter_scale: overwrite the
    # precomputed scaling dict (lora_alpha mutation is a no-op post-init).
    n = 0
    for name, mod in model.named_modules():
        scaling = getattr(mod, "scaling", None)
        if isinstance(scaling, dict) and "default" in scaling:
            orig = getattr(mod, "_orig_scaling_default",
                           scaling["default"])
            if not hasattr(mod, "_orig_scaling_default"):
                mod._orig_scaling_default = orig
            mod.scaling["default"] = orig * args.scale
            n += 1
        elif isinstance(scaling, (float, int)):
            orig = getattr(mod, "_orig_scaling_default", float(scaling))
            if not hasattr(mod, "_orig_scaling_default"):
                mod._orig_scaling_default = orig
            mod.scaling = orig * args.scale
            n += 1
    print(f"Scaled {n} LoRA layers by s={args.scale} "
          f"({'rs' if getattr(model.peft_config.get('default'), 'use_rslora', False) else ''}LoRA alpha/r preserved)")

    print("Merging (merge_and_unload) — this folds the adapter into the "
          "weights; nothing is trainable afterwards.")
    merged = model.merge_and_unload(safe_merge=True)
    merged.eval()

    os.makedirs(args.out, exist_ok=True)
    print(f"Saving merged model -> {args.out}")
    merged.save_pretrained(args.out)
    tokenizer.save_pretrained(args.out)
    with open(os.path.join(args.out, "MERGE_INFO.txt"), "w") as f:
        f.write(f"base={args.base_model}\nadapter={args.adapter_dir}\n"
                f"scale={args.scale}\n")
    print("Done. Next step:")
    print(f"  python 07_train_colab.py --pass-name pass6 "
          f"--base-model {args.out}")


if __name__ == "__main__":
    main()
