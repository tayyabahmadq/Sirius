#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SIRIUS Toolkit — Script 19: Evaluate the 9 security-lead capabilities
=====================================================================
Runs the lead eval against an Ollama model using the SAME scoring engine
imported from 04_sirius_baseline.py — keyword-group scoring, directly
comparable with the 34-item suite and eval100.

  --items v1   lead_eval_items.json    (50 items: 5/cap + 5 traps)
  --items v2   lead_eval_items_v2.json (110 items: 10/cap stratified +
               20 restraint traps; disjoint from all training seeds —
               verified by 21's decontamination, do not weaken it)
  --stack      build the system prompt per item via sirius_cli's routing
               (ROLE contract + the ONE playbook for the item's cap +
               Restraint Rule). This is the serving stack. The Step-0c
               experiment is: `--model qwen2.5:0.5b-instruct-q8_0 --stack`
               vs sirius-final --stack — if stock+stack wins on lead,
               deploy role-split (stock for lead queries, sirius-final
               for diff/audit gates).

Reports:
  - per-capability mean + pass rate, with FLOORS at --items v2 (each of
    the 9 caps ≥ 0.50 at n=10; restraint ≥ 0.80 at n=20) — a mean can
    hide a zero; the floor makes it visible.
  - restraint trap pass rate (correct answer = "no finding" — the pass6
    failure mode is manufactured findings)
  - --compare vs a baseline report: McNemar exact paired test (04b)

Usage:
    python 19_eval_capabilities.py --model sirius-final --items v2
    python 19_eval_capabilities.py --model qwen2.5:0.5b-instruct-q8_0 \
        --items v2 --stack
    python 19_eval_capabilities.py --model sirius-pass6 --selftest
    python 19_eval_capabilities.py --model sirius-pass6 \
        --compare lead_report_qwen2.5_0.5b-instruct-q8_0.json
"""
import json, os, sys, argparse, importlib.util, collections

HERE = os.path.dirname(os.path.abspath(__file__))
LEAD = os.path.join(HERE, "..", "sirius-security-lead-corpus")
ITEMS_FILES = {
    "v1": os.path.join(LEAD, "lead_eval_items.json"),
    "v2": os.path.join(LEAD, "lead_eval_items_v2.json"),
}
# Floors at --items v2: per-capability minimum pass_rate (n=10 each) and
# restraint (n=20). A mean >= 0.55 with a zero capability is still a FAIL.
FLOORS_V2 = {cap: 0.50 for cap in [
    "threat_modeling", "secure_architecture", "secure_code_review",
    "api_security", "ci_pipeline_security", "container_k8s_security",
    "secrets_management", "incident_response", "logging_monitoring"]}
FLOORS_V2["restraint"] = 0.80


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
    ap.add_argument("--host", default="localhost:11434")
    ap.add_argument("--num-predict", type=int, default=320)
    ap.add_argument("--timeout", type=int, default=180)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--items", choices=["v1", "v2"], default="v1")
    ap.add_argument("--stack", action="store_true",
                    help="serving stack: routed prompt per item "
                         "(ROLE contract + the one matching playbook + "
                         "Restraint Rule + min_p decoding) — import "
                         "from sirius_cli")
    ap.add_argument("--compare", default=None)
    ap.add_argument("--out-prefix", default=None)
    args = ap.parse_args()

    mod = load_baseline()
    b04 = load_04b()
    items_file = ITEMS_FILES[args.items]
    data = json.load(open(items_file, encoding="utf-8"))
    items, system_prompt = data["items"], data["system_prompt"]

    if args.selftest:
        ok = 0
        for it in items:
            n_hit, n_groups, _ = mod.score_answer(it["reference"],
                                                  it["groups"])
            ok += (n_hit == n_groups)
        print(f"selftest[{args.items}]: {ok}/{len(items)} references hit "
              f"all groups")
        sys.exit(0 if ok == len(items) else 1)

    stack_fn = None
    if args.stack:
        sys.path.insert(0, HERE)
        from sirius_cli import build_routed_prompt
        # deterministic per-item routing: use the item's own capability
        stack_fn = lambda it: build_routed_prompt(  # noqa: E731
            it["prompt"], context=it["cap"] if it["cap"] != "restraint"
            else None)

    caps = collections.defaultdict(lambda: {"items": [], "scores": []})
    for it in items:
        try:
            sys_prompt = stack_fn(it) if stack_fn else system_prompt
            opts = {"temperature": 0.2, "num_predict": args.num_predict}
            if stack_fn:
                opts.update({"min_p": 0.05, "repeat_penalty": 1.1})
            d = mod.ollama_post(args.host, "/api/chat", {
                "model": args.model, "stream": False, "options": opts,
                "messages": [
                    {"role": "system", "content": sys_prompt},
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
    floors = FLOORS_V2 if args.items == "v2" else {}
    floor_fail = []
    print()
    for cap in sorted(caps):
        d = caps[cap]
        mean = sum(d["scores"]) / len(d["scores"])
        prate = sum(1 for i in d["items"] if i["passed"]) / len(d["items"])
        caps_out[cap] = {"n_items": len(d["items"]),
                         "mean_score": round(mean, 3),
                         "pass_rate": round(prate, 3),
                         "items": d["items"]}
        if cap != "restraint":
            all_means.append(mean)
        line = (f"== {cap:<24} n={len(d['items'])} mean={mean:.3f} "
                f"pass={prate:.0%}")
        if cap in floors:
            ok = prate >= floors[cap]
            if not ok:
                floor_fail.append(cap)
            line += f"  floor {floors[cap]:.0%}: {'OK' if ok else 'FAIL'}"
        print(line)
    overall = sum(all_means) / len(all_means)
    print(f"\nLEAD OVERALL mean: {overall:.3f}")
    if "restraint" in caps_out:
        r = caps_out["restraint"]
        print(f"RESTRAINT: {r['pass_rate']:.0%} "
              f"({sum(1 for i in r['items'] if i['passed'])}/"
              f"{len(r['items'])})")
    if args.items == "v2":
        print(f"FLOOR GATE: {'PASS' if not floor_fail else 'FAIL — ' + ', '.join(floor_fail)}")

    base = args.out_prefix or \
        f"lead_report_{args.model.replace(':', '_').replace('.', '_')}"
    report = {"model": args.model, "items": args.items,
              "stack": bool(args.stack), "n_items": len(items),
              "capabilities": caps_out, "overall_mean": round(overall, 3),
              "floor_fail": floor_fail}
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
