#!/usr/bin/env python3
"""Train one variant and immediately persist its adapter to the GitHub artifact branch.

Designed for Kaggle sessions that recycle: each variant is a single cell, and the
adapter is pushed before anything else can be lost. Idempotent via git branch check.
"""
import argparse, json, os, subprocess, sys

REPO = "https://github.com/tayyabahmadq/Sirius.git"


def sh(cmd):
    print("$", cmd, flush=True)
    r = subprocess.run(cmd, shell=True)
    if r.returncode != 0:
        raise SystemExit(f"FAILED rc={r.returncode}: {cmd}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("variant", choices=["R1", "R2", "R3"])
    ap.add_argument("--token", required=True)
    args = ap.parse_args()
    v = args.variant
    root = f"/kaggle/working/opt_{v}"
    sh(f"rm -rf {root} && git clone -q {REPO} {root}")
    sh(f"cd {root} && python scripts/ablation/train_variant.py {v}")
    sh(f"cd {root} && mkdir -p artifacts/ablation && "
       f"cp -r sirius_lora_adapter_pass5 artifacts/ablation/{v}_adapter && "
       f"cp sirius_train_log_pass5.json artifacts/ablation/{v}_train_log.json && "
       f"git checkout -q -b ablation-{v} && git add -f artifacts/ablation/{v}_adapter && "
       f"git add -A && git -c user.email=opt@kaggle.local -c user.name=OptionA "
       f"commit -q -m '{v} adapter + config' && "
       f"git push -q https://{args.token}@github.com/tayyabahmadq/Sirius.git ablation-{v} && "
       f"echo ADAPTER_SAVED_{v}")


if __name__ == "__main__":
    main()
