#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build the frozen confirmatory lockbox (Option A prereg docs/15-optionA-prereg.md).

Source: walledai/CyberSecEval instruct slices for javascript, java, cpp — disjoint by
language from the burned Python DEV set. 13-gram dedup against DEV + Pass 5 corpus.
Deterministic, seeded, n=400. Writes items, keyword maps, and SHA256 manifest.
"""
import hashlib, json, os, random, re, urllib.request

BASE = "https://huggingface.co/datasets/walledai/CyberSecEval/resolve/main/instruct"
LANGS = ["javascript", "java", "cpp"]
CACHE = os.path.join(os.environ.get("TEMP", "/tmp"), "cyberseceval")
OUT = "data/lockbox"
N = 400
SEED = 42
STOP = set("the and for this that with from use used using should not are was were "
           "can could may might into your their its when which has have had will "
           "being other than then them they you our out any all if or of to in on "
           "is it be as by at an a with but".split())


def words(t):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", str(t).lower())).strip().split()


def grams(t, n=13):
    w = words(t)
    return {" ".join(w[i:i + n]) for i in range(max(0, len(w) - n + 1))}


def sha(b):
    return hashlib.sha256(b).hexdigest()


def load_parquet(lang):
    path = os.path.join(CACHE, f"instruct_{lang}.parquet")
    if not os.path.isfile(path):
        urllib.request.urlretrieve(f"{BASE}/{lang}-00000-of-00001.parquet", path)
    import pandas as pd
    return pd.read_parquet(path)


def keywords(desc, cwe):
    toks = [w for w in words(desc) if len(w) >= 5 and w not in STOP]
    seen, out = set(), []
    for w in toks:
        if w not in seen:
            seen.add(w); out.append(w)
    return sorted(set([cwe.lower()] + out[:12]))


def main():
    os.makedirs(OUT, exist_ok=True)
    # Contamination reference: burned DEV + all Pass 5 training text.
    ref = set()
    dev = os.path.join(CACHE, "instruct_python.parquet")
    if os.path.isfile(dev):
        import pandas as pd
        for _, r in pd.read_parquet(dev).iterrows():
            ref |= grams(str(r["origin_code"]))
    for line in open("data/sirius_train_pass5.jsonl", encoding="utf-8"):
        if line.strip():
            m = json.loads(line)
            txt = " ".join(x["content"] for x in m["messages"]
                           if x.get("role") == "user")
            ref |= grams(txt)

    rows, kw = [], {}
    raw_total = 0
    for lang in LANGS:
        df = load_parquet(lang)
        raw_total += len(df)
        for i, r in df.iterrows():
            code = str(r["origin_code"]).strip()
            if grams(code) & ref:
                continue
            cwe = str(r["cwe_identifier"])
            d = str(r["pattern_desc"])
            kw.setdefault(f"{lang}:{cwe}", keywords(d, cwe))
            rows.append({"id": f"LB-{lang[:2].upper()}-{i:04d}", "lang": lang,
                         "cwe": cwe, "prompt": str(r["prompt"]),
                         "code": code, "desc": d})
    random.seed(SEED)
    random.shuffle(rows)
    # Stratified cap: round-robin over (lang, cwe) strata to n=N.
    strata = {}
    for r in rows:
        strata.setdefault((r["lang"], r["cwe"]), []).append(r)
    chosen, keys = [], sorted(strata)
    while len(chosen) < N and keys:
        for k in list(keys):
            if strata[k] and len(chosen) < N:
                chosen.append(strata[k].pop())
            if not strata[k]:
                keys.remove(k)

    ids = []
    with open(os.path.join(OUT, "items.jsonl"), "w", encoding="utf-8") as f:
        for r in chosen:
            blob = json.dumps(r, ensure_ascii=False, sort_keys=True).encode()
            ids.append({"id": r["id"], "sha256": sha(blob)})
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(os.path.join(OUT, "keyword_maps.json"), "w", encoding="utf-8") as f:
        json.dump(kw, f, indent=2, sort_keys=True)
    with open(os.path.join(OUT, "items.sha256"), "w", encoding="utf-8") as f:
        for x in sorted(ids, key=lambda z: z["id"]):
            f.write(f"{x['sha256']}  {x['id']}\n")
    manifest = {"source": "walledai/CyberSecEval instruct javascript/java/cpp",
                "n": len(chosen), "seed": SEED, "dedup": "13-gram vs DEV python + pass5 corpus",
                "raw_rows": raw_total,
                "post_dedup_rows": len(rows),
                "strata": sorted({f"{r['lang']}:{r['cwe']}" for r in chosen})}
    with open(os.path.join(OUT, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print("LOCKBOX n =", len(chosen), "->", OUT)


if __name__ == "__main__":
    main()
