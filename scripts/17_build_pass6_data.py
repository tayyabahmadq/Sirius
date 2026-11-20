#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SIRIUS Toolkit — Script 17: Build the Phase 5 (security-lead) dataset
=====================================================================
Composes `sirius_train_pass6_lead.jsonl` — the pass6 knowledge-injection
mix that turns the auditor into the head of security across the SDLC:

  replay        sirius_train_pass5.jsonl (3358) — anti-forgetting
                (the pass5 gains live in these items' signal)
  knowledge     sirius_train_pass6_knowledge.jsonl (235, script 14)
                — auditor methodology (checklists, rubric, report format)
  lead-method   the 9 new playbooks' "Check inventory" sections →
                "what checks do you run for <capability>?" items
  lead-qa       lead_scenarios.json — 72 scenario Q&A + 10 restraint
                traps (answers follow the ROLE.md contract:
                recommendation → why/abuse → controls → first action)
  role          ROLE.md capability map + answer contract items

Decontamination gate: every NEW item (lead-*, role) is checked for
normalized 13-gram overlap (GPT-3 convention — catches true duplication
without nuking shared methodology vocabulary) against ALL eval material
(the 34-item suite, eval100, lead_eval_items). Any overlap → item dropped
and reported, so training never memorizes an eval phrasing. The wikitext
anchor is NOT embedded here — script 07 injects it via `anchor_ratio`
(10%).

Usage:
    python 17_build_pass6_data.py                 # build + verify
    python 17_build_pass6_data.py --stats-only    # distribution only
"""
import json, os, sys, re, glob, argparse, importlib.util, collections

HERE = os.path.dirname(os.path.abspath(__file__))
LEAD = os.path.join(HERE, "..", "sirius-security-lead-corpus")
SYSTEM_PROMPT = ("You are a security auditor assistant. Answer concisely, "
                 "technically, and name the exact issue.")

CAP_BY_STEM = {
    "threat_modeling": "threat_modeling",
    "secure_architecture": "secure_architecture",
    "secure_code_review": "secure_code_review",
    "api_security": "api_security",
    "ci_pipeline_security": "ci_pipeline_security",
    "container_k8s_security": "container_k8s_security",
    "secrets_management": "secrets_management",
    "incident_response": "incident_response",
    "logging_monitoring": "logging_monitoring",
}


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def norm_words(text):
    text = re.sub(r"[^a-z0-9\s]", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip().split()


def ngrams(text, n=13):
    w = norm_words(text)
    return {" ".join(w[i:i + n]) for i in range(len(w) - n + 1)}


def make_item(user, assistant, cap, archetype, source):
    return {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user.strip()},
            {"role": "assistant", "content": assistant.strip()},
        ],
        "meta": {
            "id": f"P6L-{source[:6].upper()}-{archetype[:14]}"
                  f"-{abs(hash(user)) % 100000:05d}",
            "cap": cap, "archetype": archetype,
            "safe": source in ("lead-trap",),
            "source": source,
        },
    }


def load_eval_ngram_set():
    """8-gram set over every eval prompt + reference + answer text."""
    grams = set()
    spec = importlib.util.spec_from_file_location(
        "sirius04", os.path.join(HERE, "04_sirius_baseline.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sirius04"] = mod
    spec.loader.exec_module(mod)
    for it in mod.ITEMS:
        grams |= ngrams(it.get("prompt", ""))
        grams |= ngrams(it.get("answer", "") or it.get("reference", ""))
    for path in ["eval100_items.json",
                 os.path.join(LEAD, "lead_eval_items.json")]:
        data = json.loads(read(path))
        for it in data["items"]:
            grams |= ngrams(it["prompt"])
            grams |= ngrams(it["reference"])
    return grams


def lead_method_items():
    """'Check inventory' section of each playbook → method QA."""
    items = []
    for path in sorted(glob.glob(os.path.join(LEAD, "*.md"))):
        stem = os.path.splitext(os.path.basename(path))[0]
        cap = CAP_BY_STEM.get(stem)
        if cap is None:  # ROLE.md handled separately
            continue
        text = read(path)
        sections, cur_title, cur_lines = [], None, []
        for line in text.splitlines():
            if line.startswith("## "):
                if cur_title is not None:
                    sections.append((cur_title, cur_lines))
                cur_title, cur_lines = line[3:].strip(), []
            elif cur_title is not None:
                cur_lines.append(line)
        if cur_title is not None:
            sections.append((cur_title, cur_lines))
        for title, lines in sections:
            if "check inventory" not in title.lower():
                continue
            body = "\n".join(lines).strip()
            if len(body) < 100:
                continue
            items.append(make_item(
                f"As head of security, what checks do you run for "
                f"{cap.replace('_', ' ')}? Give the inventory in order.",
                f"Run this inventory ({title}) — check every item against "
                f"the artifact:\n{body}",
                cap, "methodology", "lead-method"))
    return items


def lead_role_items():
    text = read(os.path.join(LEAD, "ROLE.md"))
    items = []
    cap_map = re.search(r"## Capability map.*?(?=\n## )", text, re.S)
    if cap_map:
        items.append(make_item(
            "You are SIRIUS, head of security. Which capability/playbook do "
            "you use at each SDLC stage?",
            cap_map.group(0).strip(), "methodology", "role", "lead-role"))
    contract = re.search(r"## Answer contract.*?(?=\n## )", text, re.S)
    if contract:
        items.append(make_item(
            "What is your answer contract as head of security?",
            contract.group(0).strip(), "methodology", "role", "lead-role"))
    return items


def lead_scenario_items():
    data = json.loads(read(os.path.join(LEAD, "lead_scenarios.json")))
    items = []
    for s in data["scenarios"]:
        items.append(make_item(s["q"], s["a"], s["cap"], "scenario",
                               "lead-qa"))
    for s in data["traps"]:
        items.append(make_item(s["q"], s["a"], s["cap"], "restraint",
                               "lead-trap"))
    return items


def load_jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stats-only", action="store_true")
    ap.add_argument("--out", default="sirius_train_pass6_lead.jsonl")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    import random
    random.seed(args.seed)

    replay = load_jsonl(os.path.join(HERE, "sirius_train_pass5.jsonl"))
    knowledge = load_jsonl(os.path.join(
        HERE, "sirius_train_pass6_knowledge.jsonl"))
    new_items = (lead_method_items() + lead_role_items()
                 + lead_scenario_items())

    # Decontamination vs all eval material
    eval_grams = load_eval_ngram_set()
    kept, dropped = [], []
    for it in new_items:
        text = " ".join(m["content"] for m in it["messages"])
        overlap = ngrams(text) & eval_grams
        if overlap:
            dropped.append((it["meta"]["id"], sorted(overlap)[:2]))
        else:
            kept.append(it)
    print("=" * 70)
    print("PHASE 5 (PASS6 LEAD) DATASET BUILD")
    print("=" * 70)
    print(f"replay (pass5):        {len(replay)}")
    print(f"knowledge (script 14): {len(knowledge)}")
    print(f"lead items authored:   {len(new_items)}")
    print(f"  decontamination dropped: {len(dropped)}")
    for i, (iid, g) in enumerate(dropped[:8]):
        print(f"    DROP {iid}: shares 13-gram(s) {g}")
    if len(dropped) > 8:
        print(f"    ... and {len(dropped) - 8} more")

    combined = replay + knowledge + kept
    random.shuffle(combined)

    by_src = collections.Counter(
        it.get("meta", {}).get("source", "replay") for it in combined)
    by_cap = collections.Counter(
        it.get("meta", {}).get("cap", "legacy") for it in combined)
    print(f"\nfinal mix: {len(combined)} items")
    print("\nBy source:")
    for s, n in by_src.most_common():
        print(f"  {s:<14} {n}")
    print("\nBy capability (new lead items):")
    for c, n in sorted(by_cap.items()):
        print(f"  {c:<26} {n}")
    print(f"\nwikitext anchor: injected by script 07 (anchor_ratio=0.10)")

    if args.stats_only:
        return

    with open(args.out, "w", encoding="utf-8") as f:
        for it in combined:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    manifest = {
        "total": len(combined),
        "replay_pass5": len(replay),
        "knowledge": len(knowledge),
        "lead_new": len(kept),
        "decontamination_dropped": len(dropped),
        "by_source": dict(by_src),
        "by_cap": dict(by_cap),
        "anchor": "script 07 anchor_ratio=0.10",
    }
    with open(args.out.replace(".jsonl", "_manifest.json"), "w",
              encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print(f"\nWrote {args.out} ({len(combined)} items) + manifest")
    print("Next: 18_reconstruct_merged_base.py → 07_train_colab.py "
          "--pass-name pass6 --base-model <merged dir>")


if __name__ == "__main__":
    main()
