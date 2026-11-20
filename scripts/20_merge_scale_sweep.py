#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SIRIUS Toolkit — Script 20: Merge-scale sweep at CAPABILITY level
=================================================================
09_eval_gate.py sweeps adapter scale against the PPL gates. This script
sweeps it against what actually ships: exported Ollama models at several
merge scales, scored on (a) the 9 lead capabilities, (b) the original
34-item suite, and (c) the eval100 load_testing items — so the scale
decision is made on capability + regression, not PPL alone.

For each --models entry it computes:
  lead_mean      mean over the 50 lead_eval items (9 capabilities)
  suite34_mean   mean over the original 34-item suite (regression guard)
  load100_mean   mean over the 30 eval100 load_testing items (the
                 Phase-4a concern, now at n=30)
  restraint      pass rate on the 5 lead traps (no manufactured findings)

Decision rule printed at the end: pick the LOWEST scale whose lead_mean
is within 0.02 of the best AND whose suite34/load100 means are not below
the s=0 baseline by more than 0.05 — same conservative logic that picked
s=0.5 for pass5.

Usage:
    python 20_merge_scale_sweep.py \
        --models qwen2.5:0.5b-instruct-q8_0,sirius-s6-s03,sirius-s6-s05,sirius-s6-s07 \
        --labels base,s=0.3,s=0.5,s=0.7
"""
import json, os, sys, argparse, importlib.util, collections

HERE = os.path.dirname(os.path.abspath(__file__))


def load_mod(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def ask(mod, model, host, timeout, num_predict, system, user):
    d = mod.ollama_post(host, "/api/chat", {
        "model": model, "stream": False,
        "options": {"temperature": 0.2, "num_predict": num_predict},
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}]}, timeout)
    return d.get("message", {}).get("content", "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", required=True,
                    help="comma-separated ollama model names, lowest scale "
                         "first (baseline first)")
    ap.add_argument("--labels", default=None,
                    help="comma-separated labels matching --models")
    ap.add_argument("--host", default="localhost:11434")
    ap.add_argument("--num-predict", type=int, default=320)
    ap.add_argument("--timeout", type=int, default=180)
    args = ap.parse_args()

    m04 = load_mod("sirius04", os.path.join(HERE, "04_sirius_baseline.py"))
    lead = json.load(open(os.path.join(
        HERE, "..", "sirius-security-lead-corpus",
        "lead_eval_items.json"), encoding="utf-8"))
    e100 = json.load(open(os.path.join(HERE, "eval100_items.json"),
                          encoding="utf-8"))
    load_items = [it for it in e100["items"] if it["cap"] == "load_testing"]

    # Normalize into a common item shape with per-set system prompts.
    sets = {
        "lead": [{"id": i["id"], "prompt": i["prompt"],
                  "groups": i["groups"], "min_pass": i.get("min_pass", 1),
                  "_system": lead["system_prompt"]}
                 for i in lead["items"]],
        "suite34": [{"id": i["id"], "prompt": i["prompt"],
                     "groups": i["groups"], "min_pass": i.get("min_pass", 1),
                     "_system": m04.SYSTEM_PROMPT}
                    for i in m04.ITEMS],
        "load100": [{"id": i["id"], "prompt": i["prompt"],
                     "groups": i["groups"], "min_pass": i.get("min_pass", 1),
                     "_system": e100["system_prompt"]}
                    for i in load_items],
    }

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    labels = [l.strip() for l in args.labels.split(",")] \
        if args.labels else models
    results = {}
    for model, label in zip(models, labels):
        print(f"\n{'='*66}\nMODEL: {model}  ({label})\n{'='*66}")
        res = {}
        for set_name, items in sets.items():
            scores, npass = [], 0
            for it in items:
                try:
                    a = ask(m04, model, args.host, args.timeout,
                            args.num_predict, it["_system"], it["prompt"])
                except Exception as e:
                    a = f"<<OLLAMA ERROR: {e}>>"
                hits, total, frac = m04.score_answer(a, it["groups"])
                scores.append(frac)
                npass += int(hits >= it["min_pass"])
                print(f"  [{set_name}:{it['id']}] {hits}/{total} "
                      f"({frac:.2f}) {'PASS' if hits >= it['min_pass'] else 'fail'}")
            res[set_name] = {"mean": round(sum(scores) / len(scores), 3),
                             "pass_rate": round(npass / len(items), 3),
                             "n": len(items)}
            print(f"  >> {set_name}: mean={res[set_name]['mean']} "
                  f"pass={res[set_name]['pass_rate']:.0%} "
                  f"(n={len(items)})")
        results[label] = {"model": model, **res}

    # Decision table
    print(f"\n{'='*66}\nSWEEP SUMMARY\n{'='*66}")
    hdr = f"{'scale':<10} {'lead':>6} {'suite34':>8} {'load100':>8}"
    print(hdr)
    for label, r in results.items():
        print(f"{label:<10} {r['lead']['mean']:>6.3f} "
              f"{r['suite34']['mean']:>8.3f} {r['load100']['mean']:>8.3f}")

    base = results[labels[0]]
    best_lead = max(r["lead"]["mean"] for r in results.values())
    pick = None
    for label in labels:
        r = results[label]
        if r["lead"]["mean"] >= best_lead - 0.02 and \
           r["suite34"]["mean"] >= base["suite34"]["mean"] - 0.05 and \
           r["load100"]["mean"] >= base["load100"]["mean"] - 0.05:
            pick = label
            break
    print(f"\nRECOMMENDED SCALE: {pick} "
          f"(highest lead mean within 0.02 of best {best_lead:.3f}, "
          f"no regression > 0.05 on suite34/load100)")
    if pick and pick != labels[0]:
        print(f"Ship: export {results[pick]['model']} via 08 → GGUF → "
              f"ollama create → 04/04b/16 acceptance re-run.")

    with open("merge_scale_sweep.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print("Wrote merge_scale_sweep.json")


if __name__ == "__main__":
    main()
