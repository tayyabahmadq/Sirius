#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SIRIUS Toolkit — Script 15: Build the 100+ item expanded acceptance eval
========================================================================
Assembles `eval100_items.json` from two authored data files of HELD-OUT
novel snippets (none appear in any training data — passing them requires
the concept, not template memorization):

  eval100_items_a.json   code_vuln_scan (46) + web_config_checks (16)
  eval100_items_b.json   dependency_cve (12) + load_testing (30)

Why: the 34-item acceptance suite has n=8–10 per capability → ±0.3 CI.
This set gives every capability n≥12 and load_testing n=30, cutting the
CI to ~±0.16 — enough to settle whether load_testing −0.062 is real noise
or a regression. The item format and keyword-group scoring are identical
to 04_sirius_baseline.py, so results are comparable.

Build-time selftest (no model needed): every item's `reference` answer must
hit ALL of its own keyword groups — guarantees each item is solvable and
grader-aligned. A failing item aborts the build.

Usage:
    python 15_build_eval_expanded.py            # write eval100_items.json
    python 15_build_eval_expanded.py --stats    # distribution only
"""
import json, os, sys, argparse, collections

PARTS = ["eval100_items_a.json", "eval100_items_b.json"]
OUT = "eval100_items.json"


def score(answer, groups):
    text = answer.lower()
    hits = 0
    for alts in groups:
        if any(k.lower() in text for k in alts):
            hits += 1
    return hits, len(groups)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stats", action="store_true")
    args = ap.parse_args()

    items, system_prompt = [], None
    for part in PARTS:
        if not os.path.isfile(part):
            print(f"ERROR: missing part file {part}")
            sys.exit(1)
        with open(part, encoding="utf-8") as f:
            data = json.load(f)
        if system_prompt is None:
            system_prompt = data.get("system_prompt")
        elif data.get("system_prompt") and \
                data["system_prompt"] != system_prompt:
            print(f"ERROR: system_prompt mismatch in {part}")
            sys.exit(1)
        items.extend(data["items"])

    # --- validation -----------------------------------------------------
    ids = [it["id"] for it in items]
    dup = [i for i, n in collections.Counter(ids).items() if n > 1]
    if dup:
        print(f"ERROR: duplicate item ids: {dup}")
        sys.exit(1)

    failures = []
    for it in items:
        if it["min_pass"] > len(it["groups"]):
            failures.append(f"{it['id']}: min_pass {it['min_pass']} > "
                            f"{len(it['groups'])} groups")
        n_hit, n_groups = score(it["reference"], it["groups"])
        if n_hit != n_groups:
            missing = [alts[0] for i, alts in enumerate(it["groups"])
                       if not any(k.lower() in it["reference"].lower()
                                  for k in alts)]
            failures.append(f"{it['id']}: reference hits {n_hit}/{n_groups}"
                            f" — missing {missing}")

    per_cap = collections.Counter(it["cap"] for it in items)
    print("=" * 70)
    print("EVAL100 BUILD")
    print("=" * 70)
    print(f"total items: {len(items)}")
    for cap, n in per_cap.most_common():
        print(f"  {cap:<24} {n}")
    print(f"\nselftest (reference must hit ALL groups): "
          f"{len(items) - len(failures)}/{len(items)} pass")

    if failures:
        print("\nSELFTEST FAILURES:")
        for f_ in failures:
            print(f"  {f_}")
        sys.exit(1)

    if args.stats:
        return

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"system_prompt": system_prompt, "items": items},
                  f, ensure_ascii=False, indent=1)
    print(f"\nWrote {OUT}")
    print("Run it with the model of your choice:")
    print("  python 04b_run_eval100.py --model sirius-final")
    print("  python 04b_run_eval100.py --model qwen2.5:0.5b-instruct-q8_0"
          "            # baseline on the same items")
    print("Then pair them:")
    print("  python 04b_run_eval100.py --model sirius-final "
          "--compare eval100_report_qwen2.5_0.5b-instruct-q8_0.json")


if __name__ == "__main__":
    main()
