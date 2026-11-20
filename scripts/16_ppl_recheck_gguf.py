#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SIRIUS Toolkit — Script 16: Phase 4 — post-quantization PPL re-check
====================================================================
Quantization changes the weights you actually deploy; the gate numbers
from 09_eval_gate.py were measured on the bf16 merge. This script
re-measures perplexity on the FINAL GGUF and compares it against the
bf16 reference PPL from the gate log.

Gate:  PPL(GGUF) / PPL(bf16 merge) <= 1.05
Rationale: Q6_K/Q5_K_M typically inflate PPL by 1–3%; a jump beyond ~5%
means the quantization (or the merge behind it) damaged the model and
the artifact must not ship. A failed check with a passing bf16 gate
usually means: re-quantize at the fallback level (Q5_K_M → Q6_K) or
re-merge before exporting.

Mechanism: llama.cpp's `llama-perplexity` binary (older builds: `main -p
perplexity` / `perplexity`) on a plain-text eval corpus. Ollama cannot be
used here — its API does not expose token log-likelihoods.

Corpus: by default uses wikitext-2 test via `datasets` (same source as
the gate), written to wikitext_test.txt once and reused.

Usage:
    python 16_ppl_recheck_gguf.py --gguf sirius_final_Q6_K.gguf \
        --llama-cpp-bin ./llama.cpp/build/bin/llama-perplexity \
        --reference-ppl 24.22

    # get the reference from the gate log automatically if the file exists:
    python 16_ppl_recheck_gguf.py --gguf ... --gate-log sirius_eval_gate_pass5.json
"""
import json, os, sys, math, argparse, subprocess, tempfile


def write_wikitext_test(path):
    try:
        from datasets import load_dataset
    except ImportError:
        print("pip install datasets  (or pass --data-file explicitly)")
        sys.exit(1)
    # FIX: legacy "wikitext" dataset alias now resolves to an invalid HF URI
    # with recent huggingface_hub; use the canonical namespaced repo.
    ds = load_dataset("Salesforce/wikitext", "wikitext-2-raw-v1", split="test")
    text = "".join(t for t in ds["text"] if t.strip())
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def extract_reference_ppl(gate_log):
    """Pull the bf16 merge PPL from a 09_eval_gate log if present."""
    try:
        with open(gate_log, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None
    # try common keys used by the gate script
    for key in ("merged_gen_ppl", "gen_ppl_merged", "ppl_merged",
                "merged_ppl", "gen_ppl"):
        for obj in (data, data.get("sweep", {}).get("1.0"),
                    data.get("results", {})):
            if isinstance(obj, dict) and obj.get(key):
                return float(obj[key])
    # search recursively for any 'ppl'-ish float key
    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if isinstance(v, (int, float)) and "ppl" in k.lower() \
                        and float(v) > 1:
                    return float(v)
                r = walk(v)
                if r:
                    return r
        elif isinstance(o, list):
            for v in o:
                r = walk(v)
                if r:
                    return r
        return None
    return walk(data)


def run_llama_ppl(binary, gguf, data_file, extra):
    cmd = [binary, "-m", gguf, "-f", data_file] + extra
    print("RUN:", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    out = proc.stdout + proc.stderr
    print(out[-2000:] if len(out) > 2000 else out)
    if proc.returncode != 0:
        return None, out
    import re
    for line in out.splitlines():
        # Older builds: "Perplexity: 24.47 +/- 0.12"
        if "Perplexity" in line and ":" in line:
            try:
                return float(line.split(":")[1].strip().split()[0]), out
            except (IndexError, ValueError):
                pass
        # Newer builds (llama.cpp b12xxx): "Final estimate: PPL = 14.7065 +/- 0.27128"
        m = re.search(r"PPL\s*=\s*([0-9]+\.?[0-9]*)", line)
        if m:
            try:
                return float(m.group(1)), out
            except ValueError:
                pass
    return None, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gguf", required=True)
    ap.add_argument("--llama-cpp-bin", default="llama-perplexity",
                    help="path to llama-perplexity (or 'perplexity') binary")
    ap.add_argument("--data-file", default=None,
                    help="plain-text eval corpus (default: wikitext-2 test)")
    ap.add_argument("--reference-ppl", type=float, default=None,
                    help="bf16 merge PPL from the gate log")
    ap.add_argument("--gate-log", default="sirius_eval_gate_pass5.json")
    ap.add_argument("--extra", nargs="*", default=["-ngl", "0"],
                    help="extra llama-perplexity args (CPU: -ngl 0 keeps "
                         "VRAM free; GPU: -ngl 99)")
    ap.add_argument("--max-ratio", type=float, default=1.05)
    args = ap.parse_args()

    if not os.path.isfile(args.gguf):
        print(f"ERROR: gguf not found: {args.gguf}")
        sys.exit(1)

    # 1. Eval corpus
    if args.data_file:
        data_file = args.data_file
    else:
        data_file = "wikitext_test.txt"
        if not os.path.isfile(data_file):
            print("Materializing wikitext-2 test corpus ...")
            write_wikitext_test(data_file)

    # 2. Reference PPL
    ref = args.reference_ppl or extract_reference_ppl(args.gate_log)
    if ref is None:
        print("WARNING: no bf16 reference PPL available — the ratio gate "
              "cannot run. Pass --reference-ppl <PPL from 09_eval_gate "
              "output at s=1.0> or --gate-log <path>.")
        ref = None

    # 3. Run llama-perplexity
    ppl, _ = run_llama_ppl(args.llama_cpp_bin, args.gguf, data_file,
                           args.extra)
    if ppl is None:
        print("\nFAILED to measure PPL. Common fixes:")
        print("  - build llama.cpp:  cmake -B build -DGGML_CUDA=OFF && "
              "cmake --build build -j --target llama-perplexity")
        print("  - point --llama-cpp-bin at build/bin/llama-perplexity")
        print("  - GPU offload:      --extra -ngl 99")
        print("  - corpus:           --data-file wikitext_test.txt")
        sys.exit(2)

    print("\n" + "=" * 64)
    print(f"GGUF PPL:            {ppl:.4f}")
    if ref is not None:
        ratio = ppl / ref
        print(f"bf16 reference PPL:  {ref:.4f}")
        print(f"quantization ratio:  {ratio:.4f}  (gate <= {args.max_ratio})")
        verdict = "PASS" if ratio <= args.max_ratio else "FAIL"
        print(f"PHASE 4 GATE:        {verdict}")
        if verdict == "FAIL":
            print("Remedy: re-quantize at the fallback level "
                  "(e.g. Q5_K_M -> Q6_K), or re-check the merge; do NOT "
                  "ship a quantized artifact whose PPL drifted beyond "
                  f"{args.max_ratio:.0%} of the bf16 gate.")
    else:
        print("No reference PPL — record the number above and compare "
              "manually (typical healthy Q6_K inflation: 1–3%).")

    out = {"gguf": args.gguf, "ppl_gguf": ppl, "ppl_reference": ref,
           "ratio": (ppl / ref) if ref else None,
           "gate": ("PASS" if ref and ppl / ref <= args.max_ratio else
                    "FAIL" if ref else "NO_REFERENCE"),
           "max_ratio": args.max_ratio, "corpus": data_file}
    base = os.path.splitext(os.path.basename(args.gguf))[0]
    with open(f"ppl_recheck_{base}.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(f"Wrote ppl_recheck_{base}.json")


if __name__ == "__main__":
    main()
