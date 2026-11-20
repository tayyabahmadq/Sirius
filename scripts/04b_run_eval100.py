#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SIRIUS Toolkit — Script 04b: Run the 104-item expanded acceptance eval
======================================================================
Runs eval100_items.json (built by script 15) against an Ollama model,
using the SAME ask()/score_answer() engine imported from
04_sirius_baseline.py — so keyword-group semantics are identical to the
34-item suite and results are directly comparable.

Modes:
  --selftest        grade each item's reference answer against its own
                    groups (no Ollama needed) — must be 104/104.
  default           run the model on all items, write
                    eval100_report_<model>.json / .md (04-style aggregates).
  --compare R.json  after running, compute the McNemar exact paired test
                    between this run and a previous report on the same
                    items, plus per-capability paired deltas.

Paired statistics are the reason this eval exists: at n=8–10 the 34-item
CI is ±0.3; with n=46/30/16/12 per capability and McNemar counting only
discordant pairs, "load_testing −0.062" can be settled as noise or real.

Usage:
    python 04b_run_eval100.py --model qwen2.5:0.5b-instruct-q8_0
    python 04b_run_eval100.py --model sirius-final
    python 04b_run_eval100.py --model sirius-final \
        --compare eval100_report_qwen2.5_0.5b-instruct-q8_0.json
"""
import json, os, sys, argparse, math, importlib.util, collections

HERE = os.path.dirname(os.path.abspath(__file__))
ITEMS_FILE = os.path.join(HERE, "eval100_items.json")


def load_baseline_module():
    path = os.path.join(HERE, "04_sirius_baseline.py")
    spec = importlib.util.spec_from_file_location("sirius04", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sirius04"] = mod
    spec.loader.exec_module(mod)
    return mod


def mcnemar_exact(b, c):
    """Two-sided exact binomial McNemar p-value."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    cdf = sum(math.comb(n, i) for i in range(0, k + 1)) / (2 ** n)
    return min(1.0, 2 * cdf)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="sirius-final")
    ap.add_argument("--host", default="http://localhost:11434")
    ap.add_argument("--num-predict", type=int, default=240)
    ap.add_argument("--timeout", type=int, default=180)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--compare", default=None,
                    help="previous eval100 report json to pair against")
    args = ap.parse_args()

    mod = load_baseline_module()
    with open(ITEMS_FILE, encoding="utf-8") as f:
        data = json.load(f)
    items = data["items"]
    system_prompt = data["system_prompt"]

    if args.selftest:
        ok = 0
        for it in items:
            n_hit, n_groups, _ = mod.score_answer(it["reference"],
                                                  it["groups"])
            ok += (n_hit == n_groups)
        print(f"selftest: {ok}/{len(items)} references hit all groups")
        sys.exit(0 if ok == len(items) else 1)

    ask_args = argparse.Namespace(host=args.host, timeout=args.timeout,
                                  raw=False, num_predict=args.num_predict)
    results = {"model": args.model, "n_items": len(items),
               "num_predict": args.num_predict,
               "capabilities": collections.defaultdict(
                   lambda: {"items": [], "scores": []})}
    for it in items:
        # Call Ollama directly (04's own ask() hardcodes 04's SYSTEM_PROMPT;
        # eval100 carries its own, identical-in-spirit prompt).
        try:
            payload = {"model": args.model, "stream": False,
                       "options": {"temperature": 0.2,
                                   "num_predict": args.num_predict},
                       "messages": [
                           {"role": "system", "content": system_prompt},
                           {"role": "user", "content": it["prompt"]}]}
            d = mod.ollama_post(args.host, "/api/chat", payload, args.timeout)
            answer = d.get("message", {}).get("content", "")
        except Exception as e:
            answer = f"<<OLLAMA ERROR: {e}>>"
        hits, total, frac = mod.score_answer(answer, it["groups"])
        passed = hits >= it.get("min_pass", 1)
        cap = results["capabilities"][it["cap"]]
        cap["items"].append({"id": it["id"], "score": round(frac, 3),
                             "hits": hits, "groups": total,
                             "passed": bool(passed), "answer": answer})
        cap["scores"].append(frac)
        print(f"[{it['id']}] {'PASS' if passed else 'fail'} "
              f"({hits}/{total} groups, {frac:.2f})")

    caps_out = {}
    all_means = []
    for cap, d in results["capabilities"].items():
        mean = sum(d["scores"]) / len(d["scores"])
        pass_rate = sum(1 for i in d["items"] if i["passed"]) / len(d["items"])
        caps_out[cap] = {"n_items": len(d["items"]),
                         "mean_score": round(mean, 3),
                         "pass_rate": round(pass_rate, 3),
                         "items": d["items"]}
        all_means.append(mean)
        print(f"\n== {cap}: n={len(d['items'])} mean={mean:.3f} "
              f"pass={pass_rate:.0%}")
    overall = sum(all_means) / len(all_means)
    print(f"\nOVERALL mean: {overall:.3f}")

    base = f"eval100_report_{args.model.replace(':', '_').replace('.', '_')}"
    report = {"model": args.model, "n_items": len(items),
              "num_predict": args.num_predict,
              "capabilities": caps_out, "overall_mean": round(overall, 3)}
    with open(base + ".json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print(f"Wrote {base}.json")

    if args.compare:
        with open(args.compare, encoding="utf-8") as f:
            old = json.load(f)
        old_by_id = {i["id"]: i for d in old.get("capabilities", {}).values()
                     for i in d.get("items", [])}
        b = c = 0  # b: old pass & new fail; c: old fail & new pass
        cap_pairs = collections.defaultdict(lambda: [0, 0])
        new_by_id = {i["id"]: i for d in caps_out.values() for i in d["items"]}
        for iid, o in old_by_id.items():
            n_ = new_by_id.get(iid)
            if n_ is None:
                continue
            cap = next(cc for cc, d in caps_out.items()
                       if any(i["id"] == iid for i in d["items"]))
            if o["passed"] and not n_["passed"]:
                b += 1
                cap_pairs[cap][0] += 1
            elif n_["passed"] and not o["passed"]:
                c += 1
                cap_pairs[cap][1] += 1
        n = b + c
        p = mcnemar_exact(b, c)
        print("\n--- McNemar exact paired test (same 104 items) ---")
        print(f"old({old.get('model')}): {b+c} discordant pairs | "
              f"regressed={b} improved={c} | p={p:.4f}")
        if p < 0.05:
            winner = "NEW" if c > b else "OLD"
            print(f"STATISTICALLY SIGNIFICANT: {winner} is better "
                  f"(p<0.05, {'improvement' if c > b else 'regression'})")
        else:
            print("NOT significant (p>=0.05): differences are within "
                  "paired noise — report the overlap honestly.")
        for cap, (rb, rc) in sorted(cap_pairs.items()):
            print(f"  {cap:<24} regressed={rb} improved={rc}")


if __name__ == "__main__":
    main()
