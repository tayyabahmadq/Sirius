#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SIRIUS Toolkit — Script 23: Step-0b control decision engine (pre-registered)
============================================================================
Applies PREREG_PHASE5R.md §1–§2 mechanically. Inputs are the two eval
reports of the BARE chained base (base + 0.5·recovered pass5 adapter, no
pass6 adapter) — produced by 04_sirius_baseline.py --full (suite34) and
19_eval_capabilities.py --items v2 (lead + traps) — plus the optional
recovery-gate ratios.

    python 23_zero_b_control.py \
        --suite-report sirius_reports/baseline_<bare-base>_<stamp>.json \
        --lead-report  lead_report_<bare-base>.json \
        [--sec-ratio 0.81] [--gen-ratio 0.94] \
        [--suite-report-s10 sirius_reports/baseline_<s10>_...json] \
        [--out zero_b_decision.json]

Branches (PREREG §2 — thresholds frozen before the local recovery ran):
  suite34(bare chained base) >= 0.75  -> CHAIN-OK   (train pass6 v2 here)
  suite34 <= 0.72                     -> CHAIN-HARM (s=1.0 check decides)
  0.72 < x < 0.75                     -> GRAY       (default s=1.0 base)

s=1.0 sanity check (CHAIN-HARM / GRAY):
  suite34(s1.0) >= 0.75 -> recovery fine at full strength, s=0.5
                           interaction is the problem -> BASE = s1.0 merge
  suite34(s1.0) <  0.75 -> RECOVERY-WEAK -> fix recovery (PREREG §4),
                           re-gate, redo 0b. No pass6 v2.

Recovery gate (PREREG §1): sec <= 0.85 OK; 0.85–0.95 WEAK-RECOVERY (flag,
s1.0 check mandatory); > 0.95 REJECT; gen > 1.05 REJECT.

--selftest synthesizes reports for every branch and asserts the labels.
"""
import json, argparse, sys, os

HERE = os.path.dirname(os.path.abspath(__file__))
PREREG = os.path.join(HERE, "PREREG_PHASE5R.md")

# ---- frozen thresholds (PREREG_PHASE5R.md §1–§2; do not edit here) ----
CHAIN_OK = 0.75          # suite34 >= this -> CHAIN-OK
CHAIN_HARM = 0.72        # suite34 <= this -> CHAIN-HARM
SEC_REJECT = 0.95        # recovery security ratio above -> reject
SEC_WEAK = 0.85          # recovery security ratio above -> flag weak
GEN_REJECT = 1.05        # recovery general ratio above -> reject


def load_report(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def classify_recovery(sec, gen):
    """Return (status, detail) per PREREG §1."""
    if sec is None or gen is None:
        return "UNSPECIFIED", "gate ratios not provided; PREREG §1 unverified"
    if sec > SEC_REJECT or gen > GEN_REJECT:
        return "REJECT", (f"sec={sec} gen={gen}: recovery damages the base; "
                          "fix per PREREG §4, re-gate, then redo 0b")
    if sec > SEC_WEAK:
        return "WEAK-RECOVERY", (f"sec={sec}: weaker than recovery #2 "
                                 "(0.8062 band); s=1.0 check mandatory")
    return "OK", f"sec={sec} gen={gen}: within PREREG §1 band"


def decide(suite34, suite34_s10, recovery_status):
    """Apply PREREG §2. Returns (branch, action, needs_s10)."""
    if recovery_status == "REJECT":
        return "RECOVERY-REJECT", ("fix recovery first (PREREG §4), "
                                   "re-gate, redo 0b"), False
    if suite34 >= CHAIN_OK:
        return "CHAIN-OK", ("base + 0.5·recovered adapter ≈ original "
                            "behavior; pass6 v2 trains on the s=0.5 "
                            "chained base (script 18 output)"), False
    if suite34 <= CHAIN_HARM:
        if suite34_s10 is None:
            return "CHAIN-HARM", ("INCOMPLETE: run 18 --scale 1.0 + "
                                  "04 --full, re-run 23 with "
                                  "--suite-report-s10"), True
        if suite34_s10 >= CHAIN_OK:
            return "CHAIN-HARM->S10-BASE", ("recovery fine at full "
                                            "strength; s=0.5 interaction "
                                            "is the problem; pass6 v2 "
                                            "trains on the s=1.0 merged "
                                            "base"), True
        return "RECOVERY-WEAK", ("even s=1.0 < 0.75: recovery #3 is "
                                 "behaviorally deficient; fix per PREREG "
                                 "§4, re-gate, redo 0b; NO pass6 v2"), True
    # gray zone
    if suite34_s10 is None:
        return "GRAY", ("INCOMPLETE: default action is the s=1.0 base; "
                        "run 18 --scale 1.0 + 04 --full, re-run 23 to "
                        "record the s1.0 number"), True
    if suite34_s10 >= CHAIN_OK:
        return "GRAY->S10-BASE", ("ambiguous zone; default s=1.0 base "
                                  "confirmed fine at full strength; "
                                  "pass6 v2 trains on s=1.0 merge"), True
    return "RECOVERY-WEAK", ("gray zone AND s=1.0 < 0.75: recovery "
                             "deficient; fix per PREREG §4, re-gate, "
                             "redo 0b"), True


def lead_summary(lead_report):
    caps = lead_report.get("capabilities", {})
    r = caps.get("restraint", {})
    return {
        "overall_mean": lead_report.get("overall_mean"),
        "floor_fail": lead_report.get("floor_fail", []),
        "restraint_pass_rate": r.get("pass_rate"),
        "restraint_n": r.get("n_items"),
    }


def selftest():
    ok = True

    def check(want, got_suite, got_s10=None, status="OK"):
        nonlocal ok
        branch, _, _ = decide(got_suite, got_s10, status)
        good = branch == want
        ok &= good
        print(f"  [{'ok' if good else 'DRIFT'}] suite={got_suite} "
              f"s10={got_s10} rec={status} -> {branch} (want {want})")

    print("PREREG §2 branches:")
    check("CHAIN-OK", 0.795)
    check("CHAIN-OK", 0.75)
    check("CHAIN-HARM", 0.67, None, "OK")
    check("CHAIN-HARM->S10-BASE", 0.67, 0.79)
    check("RECOVERY-WEAK", 0.67, 0.70)
    check("GRAY->S10-BASE", 0.73, 0.79)
    check("GRAY", 0.73, None)
    check("RECOVERY-WEAK", 0.73, 0.70)
    check("RECOVERY-REJECT", 0.795, None, "REJECT")
    check("CHAIN-OK", 0.79, None, "WEAK-RECOVERY")  # weak flag doesn't block CHAIN-OK
    print("SELFTEST", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite-report")
    ap.add_argument("--suite-report-s10", default=None)
    ap.add_argument("--lead-report")
    ap.add_argument("--sec-ratio", type=float, default=None)
    ap.add_argument("--gen-ratio", type=float, default=None)
    ap.add_argument("--out", default="zero_b_decision.json")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        sys.exit(selftest())
    if not args.suite_report:
        ap.error("--suite-report is required (or --selftest)")

    suite = load_report(args.suite_report)
    suite34 = suite["overall_mean"]
    suite_s10 = None
    if args.suite_report_s10:
        suite_s10 = load_report(args.suite_report_s10)["overall_mean"]

    status, detail = classify_recovery(args.sec_ratio, args.gen_ratio)
    branch, action, needs_s10 = decide(suite34, suite_s10, status)

    lead = lead_summary(load_report(args.lead_report)) if args.lead_report \
        else None

    print("=" * 70)
    print("STEP 0b CONTROL DECISION — PREREG_PHASE5R §2 (mechanical)")
    print("=" * 70)
    print(f"suite34 bare chained base : {suite34}")
    if suite_s10 is not None:
        print(f"suite34 s=1.0 merged      : {suite_s10}")
    print(f"recovery gate             : {status} ({detail})")
    if lead:
        print(f"lead v2 (recorded)        : overall {lead['overall_mean']}, "
              f"floor_fail={lead['floor_fail']}, restraint "
              f"{lead['restraint_pass_rate']} (n={lead['restraint_n']})")
    print(f"\nBRANCH: {branch}")
    print(f"ACTION: {action}")
    if needs_s10 and suite_s10 is None:
        print("\nNOTE: s=1.0 sanity check still outstanding (see ACTION).")

    out = {
        "prereg": "PREREG_PHASE5R.md §1–§2",
        "thresholds": {"chain_ok": CHAIN_OK, "chain_harm": CHAIN_HARM,
                       "sec_reject": SEC_REJECT, "sec_weak": SEC_WEAK,
                       "gen_reject": GEN_REJECT},
        "suite34_bare_chained_base": suite34,
        "suite34_s10_merged": suite_s10,
        "recovery_gate": {"status": status, "detail": detail,
                          "sec_ratio": args.sec_ratio,
                          "gen_ratio": args.gen_ratio},
        "lead_v2_recorded": lead,
        "branch": branch,
        "action": action,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"\nWrote {args.out} (append this to docs and §7 of the prereg)")


if __name__ == "__main__":
    main()
