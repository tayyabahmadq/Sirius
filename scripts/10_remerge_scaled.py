#!/usr/bin/env python3
"""Re-merge a PEFT adapter at a chosen inference-time scale s."""
import argparse, json, os

BASE = "Qwen/Qwen2.5-0.5B-Instruct"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--adapter", required=True)
    ap.add_argument("--scale", type=float, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--gate-log", default=None)
    args = ap.parse_args()

    if args.gate_log and os.path.isfile(args.gate_log):
        g = json.load(open(args.gate_log))
        s = g.get("chosen_s") or args.scale
        print(f"Using chosen_s from gate log: {s}")
    else:
        s = args.scale

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel

    tok = AutoTokenizer.from_pretrained(BASE)
    base = AutoModelForCausalLM.from_pretrained(
        BASE, torch_dtype=torch.bfloat16, device_map="auto")
    model = PeftModel.from_pretrained(base, args.adapter)

    n = 0
    for module in model.base_model.model.modules():
        sc = getattr(module, "scaling", None)
        if isinstance(sc, dict) and sc:
            for k in sc:
                sc[k] = sc[k] * s
            n += 1
    print(f"Scaled {n} LoRA layers by s={s}")

    merged = model.merge_and_unload()
    merged.save_pretrained(args.out, safe_serialization=True)
    tok.save_pretrained(args.out)
    print(f"Saved merged model -> {args.out}")

if __name__ == "__main__":
    main()
