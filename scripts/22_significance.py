#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SIRIUS Toolkit — Script 22: Significance checks for small-n eval deltas
========================================================================
Phase 5 post-mortem rule: apply the honesty standard SYMMETRICALLY. We
refused to claim wins from noise (McNemar p=0.219/0.289 on the lead eval);
loss claims get the same treatment. Doc 07 says pass6 "lost ~0.12 of the
pass5 suite score" — on 34 items that is net 4 flips, and exact McNemar
cannot reject the null at any plausible split. The suite delta is
directionally lower, NOT significant; the cause is unresolved until the
chained-base control runs (NEXT_PROMPT Part 4, Step 0b).

Subcommands:
  mcnemar B C          two-sided exact McNemar p (B = baseline-only passes,
                       C = model-only passes; discordant pairs only)
  wilson K N           Wilson score interval for a proportion
  selftest             recompute the doc-07 numbers; exits nonzero on drift

Usage:
    python 22_significance.py mcnemar 4 0
    python 22_significance.py wilson 6 50
    python 22_significance.py selftest

Doc-07 reference values (verified against the report tables):
  lead eval, 50 items:  pass5 0.107 (5.35/50 ≈ 6 items) vs pass6 0.127
  (≈ 6.35 items) — overlapping Wilson CIs; stock 0.200.
  suite34:  0.795 → 0.673 ≈ net 4 flips (0.122 × 34 = 4.15)
  exact McNemar: (4,0) p=0.125  (5,1) p=0.219  (6,2) p=0.289
"""
import math
import argparse


def mcnemar_exact(b, c):
    """Two-sided exact binomial McNemar p-value (matches 04b)."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    cdf = sum(math.comb(n, i) for i in range(0, k + 1)) / (2 ** n)
    return min(1.0, 2 * cdf)


def wilson(k, n, z=1.96):
    """Wilson score interval for k successes in n trials."""
    if n == 0:
        return 0.0, 0.0, 1.0
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return p, max(0.0, center - half), min(1.0, center + half)


def selftest():
    ok = True

    def check(label, got, want, tol=1e-9):
        nonlocal ok
        good = abs(got - want) <= tol
        ok &= good
        print(f"  [{'ok' if good else 'DRIFT'}] {label}: got {got:.6f} "
              f"want {want:.6f}")

    print("doc-07 suite34 regression, exact McNemar on discordant flips:")
    check("(4,0) p", mcnemar_exact(4, 0), 0.125)
    check("(5,1) p", mcnemar_exact(5, 1), 0.21875)
    check("(6,2) p", mcnemar_exact(6, 2), 0.2890625)
    print("lead eval 50 items, Wilson 95% CI (item-level, min_pass counts):")
    # 0.107 mean ≈ 5.35/50 items; 0.127 ≈ 6.35; stock 0.200 = 10/50.
    for k, lo, hi in [(5, 0.043, 0.214), (6, 0.056, 0.238),
                      (10, 0.112, 0.330)]:
        p, wlo, whi = wilson(k, 50)
        print(f"  k={k:>2}: {wlo:.3f}–{whi:.3f} "
              f"(reported band {lo:.3f}–{hi:.3f})")
        ok &= (abs(wlo - lo) < 0.01 and abs(whi - hi) < 0.01)
    # 04b cross-check: same mcnemar implementation
    import importlib.util, os, sys
    here = os.path.dirname(os.path.abspath(__file__))
    spec = importlib.util.spec_from_file_location(
        "s04b", os.path.join(here, "04b_run_eval100.py"))
    m = importlib.util.module_from_spec(spec)
    sys.modules["s04b"] = m
    spec.loader.exec_module(m)
    check("mcnemar matches 04b impl", mcnemar_exact(4, 0),
          m.mcnemar_exact(4, 0))
    print("\nSELFTEST", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_m = sub.add_parser("mcnemar", help="exact McNemar B C")
    p_m.add_argument("b", type=int)
    p_m.add_argument("c", type=int)
    p_w = sub.add_parser("wilson", help="Wilson CI K N")
    p_w.add_argument("k", type=int)
    p_w.add_argument("n", type=int)
    sub.add_parser("selftest")
    args = ap.parse_args()

    if args.cmd == "selftest":
        sys.exit(selftest())
    if args.cmd == "mcnemar":
        p = mcnemar_exact(args.b, args.c)
        print(f"McNemar exact (b={args.b} regressed, c={args.c} improved, "
              f"n={args.b + args.c} discordant): p = {p:.4f}")
        print("SIGNIFICANT at 0.05" if p < 0.05 else
              "NOT significant at 0.05 — do not claim the delta as real")
    elif args.cmd == "wilson":
        p, lo, hi = wilson(args.k, args.n)
        print(f"Wilson 95% CI: {args.k}/{args.n} = {p:.3f} "
              f"[{lo:.3f}, {hi:.3f}]")


if __name__ == "__main__":
    import sys
    main()
