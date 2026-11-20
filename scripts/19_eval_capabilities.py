#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SIRIUS Toolkit — Script 19: Evaluate the 9 security-lead capabilities
=====================================================================
Runs `lead_eval_items.json` (50 items: 5 per lead capability + 5 restraint
traps) against an Ollama model using the SAME scoring engine imported from
04_sirius_baseline.py — keyword-group scoring, directly comparable with
the 34-item suite and eval100.

Reports:
  - per-capability mean score + pass rate (9 capabilities)
  - RESTRAINT pass rate (the 5 traps: correct answer is "no finding" —
    the pass6 failure mode to watch is manufactured findings)
  - --compare vs a baseline report: McNemar exact paired test (same
    mechanism as 04b)

Usage:
    python 19_eval_capabilities.py --model sirius-pass6 --selftest
    python 19_eval_capabilities.py --model qwen2.5:0.5b-instruct-q8_0
    python 19_eval_capabilities.py --model sirius-pass6 \
        --compare lead_report_qwen2.5_0.5b-instruct-q8_0.json
"""
import json, os, sys, argparse, importlib.util, collections

HERE = os.path.dirname(os.path.abspath(__file__))
ITEMS_FILE = os.path.join(HERE, "..", "sirius-security-lead-corpus",
                          "lead_eval_items.json")


def load_baseline():
    spec = importlib.util.spec_from_file_location(
        "sirius04", os.path.join(HERE, "04_sirius_baseline.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sirius04"] = mod
    spec.loader.exec_module(mod)
    return mod


def load_04b():
    spec = importlib.util.spec_from_file_location(
        "sirius04b", os.path.join(HERE, "04b_run_eval100.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sirius04b"] = mod
    spec.loader.exec_module(mod)
    return mod


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="sirius-final")
    ap.add_argument("--host", default="http://localhost:11434")
    ap.add_argument("--num-predict", type=int, default=320)
    ap.add_argument("--timeout", type=int, default=180)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--compare", default=None)
    ap.add_argument("--out-prefix", default=None)
    args = ap.parse_args()

    mod = load_baseline()
    b04 = load_04b()
    data = json.load(open(ITEMS_FILE, encoding="utf-8"))
    items, system_prompt = data["items"], data["system_prompt"]

    if args.selftest:
        ok = 0
        for it in items:
            n_hit, n_groups, _ = mod.score_answer(it["reference"],
                                                  it["groups"])
            ok += (n_hit == n_groups)
        print(f"selftest: {ok}/{len(items)} references hit all groups")
        sys.exit(0 if ok == len(items) else 1)

    caps = collections.defaultdict(lambda: {"items": [], "scores": []})
    for it in items:
        try:
            d = mod.ollama_post(args.host, "/api/chat", {
                "model": args.model, "stream": False,
                "options": {"temperature": 0.2,
                            "num_predict": args.num_predict},
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": it["prompt"]}]},
                args.timeout)
            answer = d.get("message", {}).get("content", "")
        except Exception as e:
            answer = f"<<OLLAMA ERROR: {e}>>"
        hits, total, frac = mod.score_answer(answer, it["groups"])
        passed = hits >= it.get("min_pass", 1)
        c = caps[it["cap"]]
        c["items"].append({"id": it["id"], "score": round(frac, 3),
                           "hits": hits, "groups": total,
                           "passed": bool(passed), "answer": answer})
        c["scores"].append(frac)
        print(f"[{it['id']}] {'PASS' if passed else 'fail'} "
              f"({hits}/{total}, {frac:.2f})")

    caps_out, all_means = {}, []
    print()
    for cap in sorted(caps):
        d = caps[cap]
        mean = sum(d["scores"]) / len(d["scores"])
        prate = sum(1 for i in d["items"] if i["passed"]) / len(d["items"])
        caps_out[cap] = {"n_items": len(d["items"]),
                         "mean_score": round(mean, 3),
                         "pass_rate": round(prate, 3),
                         "items": d["items"]}
        all_means.append(mean)
        print(f"== {cap:<24} n={len(d['items'])} mean={mean:.3f} "
              f"pass={prate:.0%}")
    overall = sum(all_means) / len(all_means)
    print(f"\nLEAD OVERALL mean: {overall:.3f}")

    base = args.out_prefix or \
        f"lead_report_{args.model.replace(':', '_').replace('.', '_')}"
    report = {"model": args.model, "n_items": len(items),
              "capabilities": caps_out, "overall_mean": round(overall, 3)}
    with open(base + ".json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print(f"Wrote {base}.json")

    if args.compare:
        old = json.load(open(args.compare, encoding="utf-8"))
        old_by_id = {i["id"]: i for d in old.get("capabilities", {}).values()
                     for i in d.get("items", [])}
        new_by_id = {i["id"]: i for d in caps_out.values() for i in d["items"]}
        b = c = 0
        cap_pairs = collections.defaultdict(lambda: [0, 0])
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
        p = b04.mcnemar_exact(b, c)
        print(f"\n--- McNemar exact (vs {old.get('model')}) ---")
        print(f"discordant={b + c} regressed={b} improved={c} p={p:.4f}")
        if p < 0.05:
            print("SIGNIFICANT:", "improvement" if c > b else "regression")
        else:
            print("NOT significant (p>=0.05).")
        for cap, (rb, rc) in sorted(cap_pairs.items()):
            print(f"  {cap:<24} regressed={rb} improved={rc}")


if __name__ == "__main__":
    main()
