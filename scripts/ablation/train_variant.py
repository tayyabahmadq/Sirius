#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Wrapper: train one frozen Option A variant, snapshot config + git hash.

Usage: python scripts/ablation/train_variant.py R1
"""
import argparse, json, os, subprocess, sys, hashlib

VARIANTS = {
    "R0": "data/ablation/R0_label_first.jsonl",
    "R1": "data/ablation/R1_reason_first.jsonl",
    "R2": "data/ablation/R2_mixed.jsonl",
    "R3": "data/ablation/R3_random_neg.jsonl",
}
TRAINER = "scripts/07_train_colab.py"
RUNS = "reports/ablation"


def git(*args):
    return subprocess.check_output(["git", *args], text=True).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("variant", choices=sorted(VARIANTS))
    ap.add_argument("--repo", default=".")
    args = ap.parse_args()
    os.chdir(args.repo)
    data = VARIANTS[args.variant]
    outdir = os.path.join(RUNS, args.variant)
    os.makedirs(outdir, exist_ok=True)
    meta = {
        "variant": args.variant,
        "data": data,
        "data_sha256": hashlib.sha256(open(data, "rb").read()).hexdigest(),
        "git_commit": git("rev-parse", "HEAD"),
        "trainer_sha256": hashlib.sha256(open(TRAINER, "rb").read()).hexdigest(),
        "grader_sha256": open(os.path.join(RUNS, "grader.sha256")).read().strip()
        if os.path.isfile(os.path.join(RUNS, "grader.sha256")) else None,
        "command": f"python {TRAINER} --pass-name ablation --train {data} "
                   "--dev data/sirius_dev.jsonl --skip-install-check",
    }
    json.dump(meta, open(os.path.join(outdir, "config_snapshot.json"), "w"), indent=2)
    print(json.dumps(meta, indent=2), flush=True)
    cmd = ["python", TRAINER, "--pass-name", "ablation", "--train", data,
           "--dev", "data/sirius_dev.jsonl", "--skip-install-check"]
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1",
               PYTORCH_CUDA_ALLOC_CONF="expandable_segments:True")
    r = subprocess.run(cmd, env=env)
    json.dump({"returncode": r.returncode},
              open(os.path.join(outdir, "train_result.json"), "w"), indent=2)
    if r.returncode != 0:
        print(f"{args.variant} TRAIN FAILED rc={r.returncode} -- quarantine, no retweak",
              flush=True)
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
