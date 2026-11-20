#!/usr/bin/env python3
"""
SIRIUS Toolkit - Script 05: Cross-Model Comparison
==================================================
Run the SIRIUS Security Baseline (script 04) against a list of candidate
models, then aggregate the results into one comparison table.

This is the "cross-comparison with other AI models" step: it tells us where
Qwen2.5-0.5B stands versus other small models on the four security
capabilities, and gives us the reference scores the fine-tuned SIRIUS model
will have to beat.

Default roster (all small enough for an 8GB-RAM laptop):
    qwen2.5:0.5b          - our target base (instruct)
    qwen2.5:0.5b-base     - our target base (raw pretrain weights)
    qwen2.5-coder:0.5b    - code-specialized sibling
    smollm2:360m          - smaller competitor (HuggingFace)
    tinyllama:1.1b        - older 1.1B competitor
    deepseek-coder:1.3b   - code-specialized competitor
    gemma2:2b             - larger competitor (Google)

Usage
-----
    python 05_compare_models.py --quick          # fast pass (3 items/capability)
    python 05_compare_models.py --models qwen2.5:0.5b,smollm2:360m
    python 05_compare_models.py --no-pull        # do not download missing models

Requires:  Ollama running locally; script 04 in the same folder (imported).
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# model tag -> (raw mode?, description)
ROSTER = [
    ("qwen2.5:0.5b",        False, "Qwen2.5 0.5B Instruct (target base, instruct)"),
    ("qwen2.5:0.5b-base",   True,  "Qwen2.5 0.5B Base (target base, raw pretrain)"),
    ("qwen2.5-coder:0.5b",  False, "Qwen2.5-Coder 0.5B Instruct (code sibling)"),
    ("smollm2:360m",        False, "SmolLM2 360M Instruct (HuggingFace)"),
    ("tinyllama:1.1b",      False, "TinyLlama 1.1B Chat"),
    ("deepseek-coder:1.3b", False, "DeepSeek-Coder 1.3B Instruct"),
    ("gemma2:2b",           False, "Gemma 2 2B Instruct (Google, largest)"),
]

CAP_SHORT = {
    "code_vuln_scan": "CodeVuln",
    "web_config_checks": "WebConfig",
    "dependency_cve": "Deps/CVE",
    "load_runtime": "LoadTest",
}


def installed_models(host):
    from importlib import import_module
    b04 = import_module("04_sirius_baseline")
    return [m["name"] for m in b04.ollama_get(host, "/api/tags").get("models", [])]


def pull_model(tag):
    print(f"\n--- pulling {tag} (downloaded once, then cached) ---")
    r = subprocess.run(["ollama", "pull", tag])
    if r.returncode != 0:
        print(f"WARNING: pull failed for {tag}; skipping it.")
        return False
    return True


def main():
    ap = argparse.ArgumentParser(description="Compare candidate models on the SIRIUS Security Baseline")
    ap.add_argument("--host", default="http://localhost:11434")
    ap.add_argument("--quick", action="store_true", help="3 items per capability (faster)")
    ap.add_argument("--full", action="store_true", help="store full answers per model")
    ap.add_argument("--num-predict", type=int, default=240)
    ap.add_argument("--timeout", type=int, default=240)
    ap.add_argument("--models", default=None,
                    help="comma-separated model tags (default: full roster)")
    ap.add_argument("--no-pull", action="store_true", help="skip models that are not installed")
    ap.add_argument("--outdir", default="sirius_reports")
    args = ap.parse_args()

    import importlib
    b04 = importlib.import_module("04_sirius_baseline")

    have = installed_models(args.host)
    print(f"Ollama OK. Installed models: {', '.join(have) or '(none)'}")

    roster = ROSTER
    if args.models:
        keep = [t.strip() for t in args.models.split(",") if t.strip()]
        roster = [r for r in ROSTER if r[0] in keep] + \
                 [(t, False, "custom") for t in keep if not any(r[0] == t for r in ROSTER)]

    all_results = {}
    for tag, raw, desc in roster:
        installed = any(h == tag or h.startswith(tag) for h in have)
        if not installed:
            if args.no_pull:
                print(f"SKIP {tag} (not installed, --no-pull set)")
                continue
            if not pull_model(tag):
                continue
            have = installed_models(args.host)
        print(f"\n===== baseline: {tag} ({desc}) =====")
        ns = argparse.Namespace(
            model=tag, host=args.host, raw=raw, quick=args.quick, full=args.full,
            num_predict=args.num_predict, timeout=args.timeout, outdir=args.outdir)
        try:
            res = b04.run_suite(tag, ns)
        except SystemExit as e:
            print(e)
            continue
        except Exception as e:
            print(f"ERROR running {tag}: {e}")
            continue
        b04.save_reports(res, ns)
        all_results[tag] = res

    if not all_results:
        sys.exit("No model produced results - nothing to compare.")

    # ------------------------------------------------ aggregated comparison
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = os.path.join(args.outdir, f"comparison_{stamp}.json")
    md_path = os.path.join(args.outdir, f"comparison_{stamp}.md")
    os.makedirs(args.outdir, exist_ok=True)

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"generated_at": datetime.now(timezone.utc).isoformat(),
                   "quick": args.quick, "results": all_results}, f, indent=2)

    header = "| Model | " + " | ".join(CAP_SHORT[c] for c in CAP_SHORT) + " | Overall |"
    lines = ["# SIRIUS Cross-Model Comparison",
             "",
             f"- Generated: {stamp} | quick={args.quick}",
             "- Scores = mean keyword-group coverage, 0.0 to 1.0 (higher is better)",
             "",
             header,
             "|" + "---|" * (len(CAP_SHORT) + 2)]
    for tag, res in all_results.items():
        row = [tag]
        for cap in CAP_SHORT:
            d = res["capabilities"].get(cap)
            row.append(f"{d['mean_score']:.2f}" if d else "-")
        row.append(f"**{res['overall_mean']:.3f}**")
        lines.append("| " + " | ".join(row) + " |")
    lines += ["",
              "Interpretation notes:",
              "- Base models (raw mode) often ramble; their scores show raw knowledge, not instruction following.",
              "- These numbers are the 'before' snapshot. The fine-tuned SIRIUS model will be measured with the exact same suite.",
              ""]
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print("\n===== COMPARISON TABLE =====")
    print(f"{'model':<24}" + "".join(f"{CAP_SHORT[c]:>12}" for c in CAP_SHORT) + f"{'Overall':>10}")
    for tag, res in all_results.items():
        row = f"{tag:<24}"
        for cap in CAP_SHORT:
            d = res["capabilities"].get(cap)
            row += f"{d['mean_score']:.2f}"[:12].rjust(12) if d else "-".rjust(12)
        print(row + f"{res['overall_mean']:.3f}".rjust(10))
    print(f"\nReports written:\n  {json_path}\n  {md_path}")


if __name__ == "__main__":
    main()
