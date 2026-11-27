#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tier-3 confirmatory lockbox runner. Opens the frozen lockbox ONCE.

Requires --confirm and the exact winner tag chosen on DEV. No scale sweep, no
retries, no re-grading. See docs/15-optionA-prereg.md §5.
"""
import argparse, json, math, os, sys, time, urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import importlib.util
_spec = importlib.util.spec_from_file_location(
    "h", os.path.join(os.path.dirname(__file__), "..", "24_cyberseceval_derived.py"))
h = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(h)

LOCK = "data/lockbox"
STOCK = "qwen2.5:0.5b-instruct-q8_0"
SHIPPED = "sirius-final"


def mcnemar(a, b):
    """a = stock, b = candidate. Returns candidate-only, stock-only, two-sided p."""
    x = sum(1 for i in a if b[i] == 1 and a[i] == 0)
    y = sum(1 for i in a if a[i] == 1 and b[i] == 0)
    n = x + y
    p = min(1.0, 2 * sum(math.comb(n, k) for k in range(min(x, y) + 1)) / 2 ** n) if n else 1.0
    return x, y, p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--confirm", action="store_true",
                    help="required: declares the DEV trigger was met")
    ap.add_argument("--winner", required=True, help="Ollama tag of DEV winner at frozen scale")
    ap.add_argument("--out", default="results/lockbox_result.json")
    args = ap.parse_args()
    if not args.confirm:
        raise SystemExit("REFUSED: --confirm required (lockbox opens once, on one winner)")

    items = [json.loads(l) for l in open(os.path.join(LOCK, "items.jsonl"), encoding="utf-8")]
    kw = json.load(open(os.path.join(LOCK, "keyword_maps.json"), encoding="utf-8"))
    out = {"benchmark": "CyberSecEval-derived confirmatory lockbox",
           "n": len(items), "winner": args.winner,
           "declared_limits": ["single seed", "cross-language vs burned DEV",
                               "one McNemar, no retries"], "models": {}}
    for model in [STOCK, SHIPPED, args.winner]:
        res = []
        for i, r in enumerate(items):
            ans = h.ollama(model, h.PROMPT.format(code=r["code"]),
                           "http://localhost:11434", 120)
            keys = kw.get(f"{r['lang']}:{r['cwe']}", [r["cwe"].lower()])
            res.append({"i": i, "id": r["id"], "lang": r["lang"], "cwe": r["cwe"],
                        "answer": ans, "correct": int(any(k in ans.lower() for k in keys))})
            if (i + 1) % 50 == 0:
                print(f"  {model}: {i+1}/{len(items)}", flush=True)
        out["models"][model] = res
    stock = {x["i"]: x["correct"] for x in out["models"][STOCK]}
    win = {x["i"]: x["correct"] for x in out["models"][args.winner]}
    cw, sw, p = mcnemar(stock, win)
    out["mcnemar_vs_stock"] = {"candidate_only": cw, "stock_only": sw,
                               "n_discordant": cw + sw, "p_two_sided": p,
                               "pass": p < 0.05}
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    json.dump(out, open(args.out, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print(json.dumps(out["mcnemar_vs_stock"], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
