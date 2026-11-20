#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SIRIUS Toolkit — Script 13: Raw output dump & failure classification
====================================================================
Runs every acceptance item against the served Ollama model TWICE (once at
the acceptance num_predict, once at a short budget) and dumps the raw
generations with an automatic failure classification:

  (a) WRONG_LABEL  — answer names a known-wrong class (e.g. "buffer overflow"
                     on V02/V03/V04/V06) while missing the expected keywords.
  (b) TRUNCATED    — generation hit the token budget (eval_count >= num_predict)
                     and the LABEL: line is missing -> the template's tail got
                     cut; the "label habit" may be a decoding artifact.
  (c) GRADER_MISS  — the right class vocabulary IS present (judge by keywords)
                     but the grader groups still fail -> grader strictness bug.
  (d) HEDGE        — answer hedges/refuses ("might", "could be", "unclear")
                     without committing to a class.
  (e) PASS         — grader passed; note which groups hit.

Reads the item list directly from 04_sirius_baseline.py (single source of
truth — no duplicated item definitions).

Usage (local machine, Ollama running, model loaded):
    python 13_dump_raw_outputs.py --model sirius-final
    python 13_dump_raw_outputs.py --model sirius-final --alt-num-predict 64

Outputs:
    raw_dump_<model>.json       full machine-readable dump
    raw_dump_<model>.md         human-readable report with per-item verdicts
                                and the failure-mode histogram.

Interpretation guide:
  - If (b) TRUNCATED dominates on V06/V03/V04  -> the "label habit" is partly
    a decoding artifact. Fix: lower num_predict in 04 (default --num-predict),
    and/or shorten the answer template. No retraining needed for that share.
  - If (a) WRONG_LABEL dominates              -> real prior problem; pass5
    training (LABEL-first corpus) is the fix.
  - If (c) GRADER_MISS appears                -> fix 04's keyword groups, then
    re-score existing dumps; do not retrain on a broken metric.
"""
import json, os, sys, argparse, importlib.util, urllib.request, collections

def load_items_module(path):
    """Import 04_sirius_baseline.py regardless of its digit-leading filename."""
    spec = importlib.util.spec_from_file_location("sirius04", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sirius04"] = mod
    spec.loader.exec_module(mod)
    return mod

def ollama_post(host, path, payload, timeout):
    req = urllib.request.Request(
        f"http://{host}{path}", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=timeout))

def ask(host, model, system, prompt, num_predict, timeout, raw=False):
    opts = {"temperature": 0.2, "num_predict": num_predict}
    if raw:
        payload = {"model": model, "prompt": f"{system}\n\n{prompt}",
                   "raw": True, "stream": False, "options": opts}
        return ollama_post(host, "/api/generate", payload, timeout)
    payload = {"model": model, "stream": False, "options": opts,
               "messages": [{"role": "system", "content": system},
                            {"role": "user", "content": prompt}]}
    data = ollama_post(host, "/api/chat", payload, timeout)
    return data.get("message", {}).get("content", ""), data

def score(answer, groups):
    text = answer.lower()
    hits = [any(k.lower() in text for k in alts) for alts in groups]
    return hits, sum(hits), len(groups)

WRONG_CLASS_PHRASES = [
    "buffer overflow", "buffer overrun", "stack smashing", "xss",
    "cross-site scripting", "sql injection", "path traversal",
    "use-after-free", "format string",
]
HEDGES = ["might", "could be", "possibly", "unclear", "i'm not sure",
          "unable to", "cannot determine", "not sure"]

def classify(answer, hits, n_hit, n_groups, eval_count, num_predict):
    a = answer.lower()
    passed = n_hit >= max(1, n_groups - 1) if n_groups <= 2 else n_hit == n_groups
    # NOTE: acceptance logic in 04 is `n_hit >= min_pass`; we approximate with
    # the same threshold used by the suite (min_pass stored per item).
    truncated = (eval_count is not None and eval_count >= num_predict) or \
                ("LABEL" not in answer and len(a.split()) >= num_predict * 0.9)
    wrong = [p for p in WRONG_CLASS_PHRASES if p in a and p not in ("sql injection",)]
    if passed:
        return "PASS"
    if truncated:
        return "TRUNCATED_SUSPECT"
    if n_hit == n_groups and n_groups >= 1:
        return "GRADER_MISS"  # all groups hit but suite still fails (min_pass edge)
    if wrong and not any(h for h in hits):
        return f"WRONG_LABEL({wrong[0]})"
    if any(h in a for h in HEDGES):
        return "HEDGE"
    return "OTHER"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="sirius-final")
    ap.add_argument("--host", default="localhost:11434")
    ap.add_argument("--baseline-file", default="04_sirius_baseline.py")
    ap.add_argument("--num-predict", type=int, default=240)
    ap.add_argument("--alt-num-predict", type=int, default=None,
                    help="run a second pass at this budget (e.g. 64) to test "
                         "the truncation hypothesis")
    ap.add_argument("--timeout", type=int, default=180)
    ap.add_argument("--raw", action="store_true")
    args = ap.parse_args()

    mod = load_items_module(args.baseline_file)
    items = mod.ITEMS
    system = getattr(mod, "SYSTEM_PROMPT", "You are a security auditor assistant.")

    budgets = [args.num_predict] + ([args.alt_num_predict] if args.alt_num_predict else [])
    results = []
    for it in items:
        rec = {"id": it["id"], "cap": it["cap"], "min_pass": it.get("min_pass", 1)}
        prompt = it["prompt"]
        for np_ in budgets:
            try:
                if args.raw:
                    ans, meta = ask(args.host, args.model, system, prompt,
                                    np_, args.timeout, raw=True)
                else:
                    ans, meta = ask(args.host, args.model, system, prompt,
                                    np_, args.timeout)
                eval_count = meta.get("eval_count")
            except Exception as e:
                ans, eval_count = f"<<OLLAMA ERROR: {e}>>", None
            hits, n_hit, n_groups = score(ans, it["groups"])
            passed = n_hit >= it.get("min_pass", 1)
            rec[f"np{np_}"] = {
                "output": ans, "eval_count": eval_count,
                "hits": hits, "n_hit": n_hit, "n_groups": n_groups,
                "passed": passed,
                "verdict": classify(ans, hits, n_hit, n_groups,
                                    eval_count, np_),
            }
        results.append(rec)
        r1 = rec[f"np{budgets[0]}"]
        print(f"[{it['id']}] {'PASS' if r1['passed'] else 'FAIL'} "
              f"({r1['n_hit']}/{r1['n_groups']} groups) "
              f"verdict={r1['verdict']} eval_count={r1['eval_count']}")

    # Histogram + report
    hist = collections.Counter(r[f"np{budgets[0]}"]["verdict"].split("(")[0]
                               for r in results)
    print("\nFailure-mode histogram (primary budget):")
    for k, v in hist.most_common():
        print(f"  {k:<20} {v}")

    base = f"raw_dump_{args.model.replace(':', '_')}"
    with open(base + ".json", "w", encoding="utf-8") as f:
        json.dump({"model": args.model, "budgets": budgets,
                   "system_prompt": system, "items": results},
                  f, ensure_ascii=False, indent=2)

    md = ["# Raw output dump — " + args.model, ""]
    md.append(f"Budgets: {budgets} · verdict histogram: " +
              ", ".join(f"{k}={v}" for k, v in hist.most_common()))
    md.append("")
    for r in results:
        md.append(f"## {r['id']} ({r['cap']}, min_pass={r['min_pass']})")
        for b in budgets:
            d = r[f"np{b}"]
            md.append(f"- **np={b}** → {d['verdict']} "
                      f"({d['n_hit']}/{d['n_groups']}, eval_count={d['eval_count']})")
            md.append("  ```")
            md.append("  " + d["output"][:600].replace("\n", "\n  "))
            md.append("  ```")
        md.append("")
    with open(base + ".md", "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    print(f"\nWrote {base}.json and {base}.md")

if __name__ == "__main__":
    main()
