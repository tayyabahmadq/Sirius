#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tier-2 helper: merge an adapter at scale s, export Q6_K, create Ollama tag,
then run the frozen DEV harness. Scale is an inference dial only — no retraining.

Usage:
  python scripts/ablation/sweep_scale.py --variant R1 --scale 0.5
"""
import argparse, json, os, subprocess, sys

ROOT = os.path.abspath(".")
TOOLS = os.path.join(ROOT, ".tools", "llama-cpu", "llama-quantize.exe")


def sh(cmd, **kw):
    print("$", cmd, flush=True)
    r = subprocess.run(cmd, shell=True, cwd=ROOT, **kw)
    if r.returncode != 0:
        raise SystemExit(f"FAILED rc={r.returncode}: {cmd}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", required=True)
    ap.add_argument("--scale", type=float, required=True)
    ap.add_argument("--adapter", default=None)
    args = ap.parse_args()
    tag = f"sirius-{args.variant}-s{str(args.scale).replace('.','')}"
    adapter = args.adapter or os.path.join(ROOT, "artifacts", "ablation",
                                           f"{args.variant}_adapter")
    merged = os.path.join(ROOT, "artifacts", "ablation",
                          f"{args.variant}_merged_s{args.scale}")
    f16 = os.path.join(ROOT, "artifacts", "ablation", f"{tag}.f16.gguf")
    q6 = os.path.join(ROOT, "artifacts", "ablation", f"{tag}_Q6_K.gguf")
    os.makedirs(os.path.dirname(merged), exist_ok=True)

    if not os.path.isdir(merged):
        sh(f'python scripts/10_remerge_scaled.py --adapter "{adapter}" '
           f'--scale {args.scale} --out "{merged}"')
    if not os.path.isfile(f16):
        sh(f'python convert_hf_to_gguf.py "{merged}" --outfile "{f16}" --outtype f16')
    if not os.path.isfile(q6):
        sh(f'"{TOOLS}" "{f16}" "{q6}" Q6_K')

    mf = os.path.join(ROOT, "artifacts", "ablation", f"Modelfile.{tag}")
    with open(mf, "w", encoding="utf-8") as f:
        f.write(f"FROM {q6}\n\nPARAMETER temperature 0.2\n"
                "PARAMETER num_predict 240\n"
                "SYSTEM You are a security auditor assistant. Answer concisely, "
                "technically, and name the exact issue.\n")
    sh(f'ollama create {tag} -f "{mf}"')

    out = os.path.join(ROOT, "results", "ablation", f"{args.variant}_s{args.scale}.json")
    sh(f'python scripts/24_cyberseceval_derived.py --models {tag} --out "{out}" '
       '--no-control')
    data = json.load(open(out, encoding="utf-8"))
    print(json.dumps(data["models"][tag]["identification"], indent=2), flush=True)


if __name__ == "__main__":
    main()
