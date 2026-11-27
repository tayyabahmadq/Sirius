#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Format-agnostic label extractor + suite34 parity checker (Option A prereg §4).

The suite34 keyword-group scorer is kept byte-identical to 04_sirius_baseline.py.
The label extractor is used only for parse-rate gating; rationales are never
keyword-scored beyond the existing group scorer.
"""
import argparse, json, re, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import importlib.util
_spec = importlib.util.spec_from_file_location(
    "sirius04", os.path.join(HERE, "..", "04_sirius_baseline.py"))
m04 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m04)

LABEL_RE = re.compile(r"(?:^|\n)\s*(?:LABEL|Label|label)\s*:\s*([^\n]+)", re.I)


def extract_label(answer):
    """Return the canonical label string, or None if no explicit label is present."""
    matches = LABEL_RE.findall(answer or "")
    if matches:
        return matches[-1].strip().rstrip(".").lower()
    lines = [x.strip() for x in (answer or "").splitlines() if x.strip()]
    return lines[-1].lower() if lines else None


def grade_answer(answer, groups):
    """Byte-identical semantics to 04_sirius_baseline.score_answer."""
    text = (answer or "").lower()
    hits = sum(1 for alts in groups if any(k.lower() in text for k in alts))
    return hits, len(groups), hits / len(groups)


def canonical_label(answer, expected):
    lab = extract_label(answer)
    if lab is None:
        return None
    return lab if any(k in lab for k in expected) else lab


# 20 hand-checked cases per format. expected = substring of the canonical label.
UNIT = [
    ("LABEL: hardcoded secret in source FUNCTION: ...", "hardcoded", True),
    ("Label: command injection\nMechanism: shell metacharacters.", "command injection", True),
    ("label: sql injection\nTrigger: concatenated query.", "sql injection", True),
    ("LABEL: weak hash RISK: fast to crack", "weak hash", True),
    ("LABEL: verify=false / disabled TLS verification", "tls", True),
    ("LABEL: path traversal", "traversal", True),
    ("LABEL: xss", "xss", True),
    ("LABEL: code injection via eval", "eval", True),
    ("LABEL: missing access control", "access control", True),
    ("LABEL: insecure cookie flags", "cookie", True),
    ("LABEL: over-fetch in API", "over-fetch", True),
    ("LABEL: plain http on admin route", "http", True),
    ("LABEL: missing security headers", "headers", True),
    ("LABEL: http-to-https redirect issue", "redirect", True),
    ("LABEL: stack trace disclosure", "stack trace", True),
    ("LABEL: csp header missing", "csp", True),
    ("LABEL: directory listing enabled", "directory listing", True),
    ("LABEL: memory leak", "memory leak", True),
    ("LABEL: missing overload protection", "overload", True),
    ("LABEL: outdated library", "outdated", True),
    ("Mechanism: a live credential is embedded in source.\nTrigger: anyone with repo access reads it.\nLabel: hardcoded secret", "hardcoded", True),
    ("Mechanism: user input reaches a shell command.\nTrigger: semicolon in a parameter.\nLabel: command injection", "command injection", True),
    ("Mechanism: query text is concatenated from input.\nTrigger: quote in a field.\nLabel: sql injection", "sql injection", True),
    ("Mechanism: MD5 is a fast hash.\nTrigger: offline cracking of the dump.\nLabel: weak hash", "weak hash", True),
    ("Mechanism: TLS certificate checks are disabled.\nTrigger: network attacker on-path.\nLabel: disabled certificate verification", "certificate", True),
    ("Mechanism: a path is built from user input.\nTrigger: ../ escapes the root.\nLabel: path traversal", "traversal", True),
    ("Mechanism: user text is inserted as HTML.\nTrigger: script tag in a comment.\nLabel: xss", "xss", True),
    ("Mechanism: eval executes a string.\nTrigger: attacker-supplied payload.\nLabel: code injection", "code injection", True),
    ("Mechanism: object ownership is not checked.\nTrigger: another user's id.\nLabel: missing access control", "access control", True),
    ("Mechanism: cookie flags are absent.\nTrigger: script reads the cookie.\nLabel: insecure cookie flags", "cookie", True),
    ("Mechanism: the API returns the whole row.\nTrigger: a list request.\nLabel: over-fetch", "over-fetch", True),
    ("Mechanism: admin traffic is plaintext.\nTrigger: wifi interception.\nLabel: plain http", "http", True),
    ("Mechanism: no security headers are set.\nTrigger: a framed login page.\nLabel: missing security headers", "headers", True),
    ("Mechanism: redirect is not forced.\nTrigger: first request is http.\nLabel: http to https redirect", "redirect", True),
    ("Mechanism: an exception is rendered.\nTrigger: a bad parameter.\nLabel: stack trace disclosure", "stack trace", True),
    ("Mechanism: no CSP is present.\nTrigger: third-party script loads.\nLabel: csp header", "csp", True),
    ("Mechanism: the server lists a directory.\nTrigger: request to /uploads/.\nLabel: directory listing", "directory listing", True),
    ("Mechanism: buffers are never released.\nTrigger: sustained traffic.\nLabel: memory leak", "memory leak", True),
    ("Mechanism: no rate or load limit.\nTrigger: burst traffic.\nLabel: overload protection", "overload", True),
    ("Mechanism: a pinned version is old.\nTrigger: published CVE.\nLabel: outdated library", "outdated", True),
]


def unit_test():
    ok = 0
    for ans, exp, want in UNIT:
        lab = extract_label(ans)
        got = bool(lab and exp in lab)
        ok += (got == want)
        if got != want:
            print(f"UNIT FAIL exp={exp} got={lab!r} :: {ans[:70]}")
    print(f"unit: {ok}/{len(UNIT)} pass")
    return ok == len(UNIT)


def parity(report):
    data = json.load(open(report, encoding="utf-8"))
    items = {i["id"]: i for i in data["items"]}
    scores = []
    for it in m04.ITEMS:
        ans = items[it["id"]].get("np240", {}).get("output", "")
        _, _, frac = grade_answer(ans, it["groups"])
        scores.append(frac)
    caps = {}
    for it in m04.ITEMS:
        pass
    # reproduce unweighted mean of four capability means
    by = {}
    for it, sc in zip(m04.ITEMS, scores):
        by.setdefault(it["cap"], []).append(sc)
    overall = sum(sum(v) / len(v) for v in by.values()) / len(by)
    print("parity overall:", round(overall, 4), "(expected 0.795 ±1 item: 0.765-0.824)")
    return 0.765 <= overall <= 0.824


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--unit", action="store_true")
    ap.add_argument("--parity", metavar="REPORT_JSON")
    args = ap.parse_args()
    if args.unit:
        return 0 if unit_test() else 1
    if args.parity:
        return 0 if parity(args.parity) else 1
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
