#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build Option A ablation data variants R0-R3 from the Pass 5 corpus.

Frozen in docs/15-optionA-prereg.md. No CSE-derived text is used in training.
Rationales are templated from existing verified FUNCTION/RISK fields only.
"""
import hashlib, json, os, random, re, glob

SEED = 42
BASE = "data/sirius_train_pass5.jsonl"
OUT = "data/ablation"
DEV_PQ = os.path.join(os.environ.get("TEMP", "/tmp"), "cyberseceval",
                      "instruct_python.parquet")


def words(t):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", str(t).lower())).strip().split()


def grams(t, n=13):
    w = words(t)
    return {" ".join(w[i:i + n]) for i in range(max(0, len(w) - n + 1))}


def fields(answer):
    out = {}
    for key in ("LABEL", "FUNCTION", "RISK", "FIX"):
        m = re.search(rf"{key}\s*:\s*([^\n]+)", answer, re.I)
        out[key] = m.group(1).strip() if m else ""
    return out


def trim(text, maxw):
    w = text.split()
    return " ".join(w[:maxw]) + (" ..." if len(w) > maxw else "")


def reasoning(answer):
    f = fields(answer)
    label = trim(f["LABEL"] or "unclear", 8)
    mech = trim(f["FUNCTION"] or f["RISK"] or "security-relevant construct", 22)
    trig = trim(f["RISK"] or "no exploitable condition verified", 16)
    if "no vulnerability" in label.lower():
        mech = trim(f["FUNCTION"] or "controls are present", 22)
        trig = "no exploitable condition verified"
    return f"Mechanism: {mech}\nTrigger: {trig}\nLabel: {label}"


def ref_grams():
    ref = set()
    # suite34 + eval100 prompts
    import importlib.util
    spec = importlib.util.spec_from_file_location("m04", "scripts/04_sirius_baseline.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    for it in m.ITEMS:
        ref |= grams(it.get("prompt", ""))
    for f in ["data/eval100_items.json", "data/lead_eval_items_v2.json"]:
        if os.path.isfile(f):
            d = json.load(open(f, encoding="utf-8"))
            for it in d.get("items", []):
                ref |= grams(it.get("prompt", ""))
    # burned DEV prompts
    if os.path.isfile(DEV_PQ):
        import pandas as pd
        for _, r in pd.read_parquet(DEV_PQ).iterrows():
            ref |= grams(str(r["prompt"]))
    # frozen lockbox code/prompts
    if os.path.isfile("data/lockbox/items.jsonl"):
        for line in open("data/lockbox/items.jsonl", encoding="utf-8"):
            if line.strip():
                r = json.loads(line)
                ref |= grams(r["prompt"]) | grams(r["code"])
    return ref


def write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def main():
    os.makedirs(OUT, exist_ok=True)
    rows = [json.loads(l) for l in open(BASE, encoding="utf-8") if l.strip()]
    ref = ref_grams()
    report = {"source": BASE, "n": len(rows), "seed": SEED, "variants": {}}

    # R0 byte-identical
    h0 = write_jsonl(os.path.join(OUT, "R0_label_first.jsonl"), rows)
    report["variants"]["R0"] = {"format": "label_first", "negatives": "hard",
                                "sha256": h0, "n": len(rows)}

    # R1 reasoning-first (same items)
    r1 = []
    for r in rows:
        x = json.loads(json.dumps(r))
        x["messages"][2]["content"] = reasoning(r["messages"][2]["content"])
        x["meta"]["label_first"] = False
        x["meta"]["format"] = "reasoning_first"
        r1.append(x)
    h1 = write_jsonl(os.path.join(OUT, "R1_reason_first.jsonl"), r1)
    report["variants"]["R1"] = {"format": "reasoning_first", "negatives": "hard",
                                "sha256": h1, "n": len(r1)}

    # R2 mixed 50/50 by stable index
    r2 = [r1[i] if i % 2 else rows[i] for i in range(len(rows))]
    h2 = write_jsonl(os.path.join(OUT, "R2_mixed.jsonl"), r2)
    report["variants"]["R2"] = {"format": "mixed_50_50", "negatives": "hard",
                                "sha256": h2, "n": len(r2)}

    # R3 reasoning-first with random, label/length-matched negatives
    rng = random.Random(SEED)
    groups = {}
    for i, r in enumerate(rows):
        a = r["messages"][2]["content"]
        key = (str(r["meta"].get("safe", False)), len(a) // 120)
        groups.setdefault(key, []).append(i)
    swap = {}
    for key, idxs in groups.items():
        vals = [rows[i]["messages"][2]["content"] for i in idxs]
        rng.shuffle(vals)
        for i, v in zip(idxs, vals):
            swap[i] = v
    r3 = []
    for i, r in enumerate(rows):
        x = json.loads(json.dumps(r))
        x["messages"][2]["content"] = reasoning(swap[i])
        x["meta"]["label_first"] = False
        x["meta"]["format"] = "reasoning_first"
        x["meta"]["negatives"] = "random_matched"
        r3.append(x)
    h3 = write_jsonl(os.path.join(OUT, "R3_random_neg.jsonl"), r3)
    report["variants"]["R3"] = {"format": "reasoning_first",
                                "negatives": "random_label_length_matched",
                                "sha256": h3, "n": len(r3)}

    # contamination sweep
    for name in ["R0", "R1", "R2", "R3"]:
        f = {"R0": "R0_label_first.jsonl", "R1": "R1_reason_first.jsonl",
             "R2": "R2_mixed.jsonl", "R3": "R3_random_neg.jsonl"}[name]
        hits = 0
        for line in open(os.path.join(OUT, f), encoding="utf-8"):
            r = json.loads(line)
            txt = " ".join(m["content"] for m in r["messages"])
            hits += bool(grams(txt) & ref)
        report["variants"][name]["contamination_hits"] = hits
        print(name, "contamination hits", hits)

    # token budget delta (word proxy, frozen choice: same item count, log delta)
    def avg_words(path):
        tot = 0
        for line in open(path, encoding="utf-8"):
            r = json.loads(line)
            tot += len(words(r["messages"][2]["content"]))
        return round(tot / len(rows), 1)
    for name, f in [("R0", "R0_label_first.jsonl"), ("R1", "R1_reason_first.jsonl")]:
        report["variants"][name]["avg_completion_words"] = avg_words(os.path.join(OUT, f))

    json.dump(report, open(os.path.join(OUT, "manifest.json"), "w", encoding="utf-8"),
              indent=2)
    with open(os.path.join(OUT, "manifest.sha256"), "w", encoding="utf-8") as f:
        for k in sorted(report["variants"]):
            f.write(f"{report['variants'][k]['sha256']}  {k}\n")
    print("variants written:", ", ".join(sorted(report["variants"])))


if __name__ == "__main__":
    main()
