#!/usr/bin/env python3
"""
SIRIUS Toolkit - Script 04: Security Baseline Benchmark v0.1
=============================================================
Run a fixed suite of security-check prompts against a local Ollama model
and score the answers with transparent keyword heuristics.

This gives SIRIUS its "before" measurement: how good is the stock model at
  1. code vulnerability scanning
  2. web configuration / policy checks
  3. dependency & CVE awareness
  4. load & runtime testing

Every item is scored by checking whether the model's answer mentions the
expected technical concepts (keyword groups). It is a coarse but honest
signal - the SAME suite runs on EVERY candidate model, so the comparison
is meaningful even if the scoring is simple.

Usage
-----
    python 04_sirius_baseline.py                        # qwen2.5:0.5b, full suite
    python 04_sirius_baseline.py --quick                # 3 items per capability
    python 04_sirius_baseline.py --model qwen2.5:0.5b-base --raw
    python 04_sirius_baseline.py --host http://localhost:11434

Requires:  Ollama running locally. No extra Python packages (stdlib only).
"""

import argparse
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone

# ---------------------------------------------------------------- suite

SYSTEM_PROMPT = ("You are a security auditor assistant. Answer concisely, "
                 "technically, and name the exact issue.")

# Every item: id, capability, prompt, expected keyword groups (each group is a
# set of alternatives - hitting ANY one counts the group as covered).
ITEMS = [
    # ---------------- capability 1: code vulnerability scan ----------------
    dict(id="V01", cap="code_vuln_scan", groups=[
        ["sql injection", "parameterized", "prepared statement"],
        ["concat", "string formatting", "f-string", "interpolat"]], min_pass=1,
        prompt="Review this Python code for security issues and name the exact vulnerability:\n"
               "def login(user, pw):\n"
               "    q = \"SELECT * FROM users WHERE name='\" + user + \"' AND pw='\" + pw + \"'\"\n"
               "    return db.execute(q).fetchone()"),
    dict(id="V02", cap="code_vuln_scan", groups=[
        ["hardcoded", "hard-coded", "hard coded", "embedded credential", "secret in source"]], min_pass=1,
        prompt="Review this code for security issues and name the exact vulnerability:\n"
               "API_KEY = \"sk-live-9f2c7d88ab\"\n"
               "def call():\n    return requests.post(URL, headers={\"Authorization\": API_KEY})"),
    dict(id="V03", cap="code_vuln_scan", groups=[
        ["command injection", "shell injection", "os.system", "subprocess", "shell=True"]], min_pass=1,
        prompt="Review this Python code for security issues and name the exact vulnerability:\n"
               "import os\n"
               "def ping(host):\n"
               "    return os.system(f\"ping -c 1 {host}\")"),
    dict(id="V04", cap="code_vuln_scan", groups=[
        ["eval", "arbitrary code", "code execution", "code injection"]], min_pass=1,
        prompt="Review this Python code for security issues and name the exact vulnerability:\n"
               "def calc(expr):\n    return eval(expr)"),
    dict(id="V05", cap="code_vuln_scan", groups=[
        ["md5", "weak hash", "sha1", "unsalted"], ["bcrypt", "argon2", "scrypt", "salt"]], min_pass=2,
        prompt="Review this code for security issues and name the exact vulnerability:\n"
               "import hashlib\n"
               "def save_password(pw):\n    return hashlib.md5(pw.encode()).hexdigest()"),
    dict(id="V06", cap="code_vuln_scan", groups=[
        ["verify=false", "verify=false", "certificate", "tls", "ssl", "mitm", "man-in-the-middle"]], min_pass=1,
        prompt="Review this Python code for security issues and name the exact vulnerability:\n"
               "resp = requests.get(\"https://api.internal.corp/data\", verify=False)"),
    dict(id="V07", cap="code_vuln_scan", groups=[
        ["path traversal", "traversal", "../", "directory", "sanitize the path", "basename"]], min_pass=1,
        prompt="Review this Flask code for security issues and name the exact vulnerability:\n"
               "@app.route('/download/<name>')\n"
               "def download(name):\n"
               "    return send_file('/uploads/' + name)"),
    dict(id="V08", cap="code_vuln_scan", groups=[
        ["xss", "cross-site scripting", "innerHTML", "escape", "sanitiz"]], min_pass=1,
        prompt="Review this JavaScript code for security issues and name the exact vulnerability:\n"
               "document.getElementById('out').innerHTML = userComment;"),
    dict(id="V09", cap="code_vuln_scan", groups=[
        ["auth", "authorization", "access control", "unauthorized", "session"]], min_pass=1,
        prompt="Review this Flask code for security issues and name the exact vulnerability:\n"
               "@app.route('/admin/users')\n"
               "def list_users():\n"
               "    return jsonify(db.users.all())"),
    dict(id="V10", cap="code_vuln_scan", groups=[
        ["random", "predictable", "insecure"], ["secrets", "crypto", "os.urandom", "secure random"]], min_pass=2,
        prompt="Review this Python code for security issues and name the exact vulnerability:\n"
               "import random\n"
               "def new_session_token():\n    return str(random.random())"),

    # ------------- capability 2: web configuration / policy checks -------------
    dict(id="W01", cap="web_config_checks", groups=[
        ["strict-transport-security", "hsts"], ["content-security-policy", "csp"],
        ["x-frame-options", "frame-ancestors", "clickjacking"],
        ["x-content-type-options"]], min_pass=2,
        prompt="List the HTTP security response headers a production website should send, and what each one prevents."),
    dict(id="W02", cap="web_config_checks", groups=[
        ["httponly"], ["secure"], ["samesite", "csrf"]], min_pass=2,
        prompt="What flags should a session cookie have to be considered secure, and what attack does each flag stop?"),
    dict(id="W03", cap="web_config_checks", groups=[
        ["https", "redirect", "301", "308", "hsts"]], min_pass=1,
        prompt="A site serves the same content on http:// and https://. What is wrong and how do you fix it?"),
    dict(id="W04", cap="web_config_checks", groups=[
        ["content-security-policy", "csp"], ["script", "inline"], ["xss", "injection"]], min_pass=1,
        prompt="What is a Content-Security-Policy header and which attack class does it mitigate?"),
    dict(id="W05", cap="web_config_checks", groups=[
        ["directory listing", "index of", "autoindex", "file exposure", "enumeration"]], min_pass=1,
        prompt="A web server has directory listing enabled. Why is that a risk and what should be configured instead?"),
    dict(id="W06", cap="web_config_checks", groups=[
        ["stack trace", "information disclosure", "debug", "verbose error", "leak"]], min_pass=1,
        prompt="Production shows full stack traces to users on errors. What is the risk and the correct fix?"),
    dict(id="W07", cap="web_config_checks", groups=[
        ["https", "tls", "plaintext", "sniff", "intercept", "credentials"]], min_pass=1,
        prompt="An admin panel is reachable over plain http. Why is this dangerous even for internal networks?"),
    dict(id="W08", cap="web_config_checks", groups=[
        ["sensitive", "over-fetch", "hash", "field", "exposure", "leak", "response"]], min_pass=1,
        prompt="A public API endpoint returns user records including the password_hash field. What is the issue and the fix?"),

    # ---------------- capability 3: dependency & CVE awareness ----------------
    dict(id="D01", cap="dependency_cve", groups=[
        ["known vulnerabilities", "cve", "outdated", "patch", "update", "advisory"]], min_pass=1,
        prompt="Your project uses a library version released 3 years ago. What are the risks and what should you do?"),
    dict(id="D02", cap="dependency_cve", groups=[
        ["common vulnerabilities", "cve", "identifier", "id", "mitre", "database"]], min_pass=1,
        prompt="What is a CVE? Explain how CVE identifiers are used in vulnerability management."),
    dict(id="D03", cap="dependency_cve", groups=[
        ["pip-audit", "safety", "pip", "audit", "snyk", "dependabot"]], min_pass=1,
        prompt="How do you check a Python project's dependencies for known vulnerabilities? Name tools."),
    dict(id="D04", cap="dependency_cve", groups=[
        ["npm audit", "audit", "snyk", "dependabot", "npm"]], min_pass=1,
        prompt="How do you check a Node.js project's dependencies for known vulnerabilities? Name tools."),
    dict(id="D05", cap="dependency_cve", groups=[
        ["pin", "lock", "lockfile", "package-lock", "version", "exact"]], min_pass=1,
        prompt="Why should dependency versions be pinned or locked in a project? What file does this in npm?"),
    dict(id="D06", cap="dependency_cve", groups=[
        ["typosquat", "typo", "package name", "spoof", "malicious package", "registry"]], min_pass=1,
        prompt="What is typosquatting in package registries and how do you protect a project from it?"),
    dict(id="D07", cap="dependency_cve", groups=[
        ["abandoned", "unmaintained", "maintainer", "supply chain", "Bus factor", "no longer maintained"]], min_pass=1,
        prompt="What risks come from depending on an abandoned open-source package that no longer gets updates?"),
    dict(id="D08", cap="dependency_cve", groups=[
        ["digest", "tag", "latest", "pin", "image", "mutable"]], min_pass=1,
        prompt="Why is pulling container images with the 'latest' tag risky for builds? What should be used instead?"),

    # ---------------- capability 4: load & runtime testing ----------------
    dict(id="L01", cap="load_runtime", groups=[
        ["k6", "locust", "jmeter", "load test", "script"], ["vus", "virtual users", "concurrent", "iterations"]], min_pass=1,
        prompt="Write a short k6 load test script that hits https://example.com/api with 50 virtual users for 1 minute."),
    dict(id="L02", cap="load_runtime", groups=[
        ["percentile", "95", "p95", "latency"]], min_pass=1,
        prompt="In load test results, what does p95 latency mean and why is it more useful than the average?"),
    dict(id="L03", cap="load_runtime", groups=[
        ["requests per second", "rps", "throughput"], ["concurrent", "users", "sessions"]], min_pass=1,
        prompt="Explain the difference between requests per second (RPS) and concurrent users in a load test."),
    dict(id="L04", cap="load_runtime", groups=[
        ["logs", "metrics", "monitoring", "cpu", "memory", "database", "slow query"]], min_pass=2,
        prompt="An application becomes very slow right after a deployment. Walk through your first diagnostic checks."),
    dict(id="L05", cap="load_runtime", groups=[
        ["leak", "heap", "profile", "memory", "gc", "allocation"]], min_pass=1,
        prompt="A service's memory usage keeps growing until it restarts. What is the likely problem and how do you confirm it?"),
    dict(id="L06", cap="load_runtime", groups=[
        ["rate limit", "shed", "queue", "timeout", "backpressure", "throttle", "degrade"]], min_pass=1,
        prompt="Under heavy load, what techniques protect a web service from falling over completely?"),
    dict(id="L07", cap="load_runtime", groups=[
        ["canary", "gradual", "small", "rollout", "subset", "percentage"]], min_pass=1,
        prompt="What is a canary release and how does it reduce deployment risk?"),
    dict(id="L08", cap="load_runtime", groups=[
        ["timeout", "capacity", "connection pool", "upstream", "saturation", "overload", "threads"]], min_pass=1,
        prompt="During a load test your API starts returning 502/503 errors. List the most likely causes and how you would confirm each."),
]

CAP_TITLES = {
    "code_vuln_scan": "Code vulnerability scanning",
    "web_config_checks": "Web configuration & policy checks",
    "dependency_cve": "Dependency & CVE awareness",
    "load_runtime": "Load & runtime testing",
}


# ---------------------------------------------------------------- ollama api

def ollama_post(host, path, payload, timeout):
    req = urllib.request.Request(
        host.rstrip("/") + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def ollama_get(host, path, timeout=15):
    with urllib.request.urlopen(host.rstrip("/") + path, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def ask(model, prompt, args):
    """Send one prompt to Ollama, return the answer text."""
    opts = {"temperature": 0.2, "num_predict": args.num_predict}
    if args.raw:
        payload = {"model": model, "prompt": prompt, "raw": True,
                   "stream": False, "options": opts}
        data = ollama_post(args.host, "/api/generate", payload, args.timeout)
        return data.get("response", "")
    payload = {"model": model, "stream": False, "options": opts,
               "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": prompt}]}
    data = ollama_post(args.host, "/api/chat", payload, args.timeout)
    return data.get("message", {}).get("content", "")


# ------------------------------------------------------------------ scoring

def score_answer(answer, groups):
    """Return (hits, total_groups, score_fraction)."""
    text = answer.lower()
    hits = 0
    for alts in groups:
        if any(k.lower() in text for k in alts):
            hits += 1
    return hits, len(groups), hits / len(groups)


def run_suite(model, args):
    items = ITEMS
    if args.quick:
        by_cap = {}
        for it in ITEMS:
            by_cap.setdefault(it["cap"], []).append(it)
        items = [it for cap, lst in by_cap.items() for it in lst[:3]]

    results = {"meta": {
        "model": model, "host": args.host, "raw": args.raw,
        "quick": args.quick, "num_predict": args.num_predict,
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "suite_version": "SIRIUS Security Baseline v0.1",
    }, "capabilities": {}}

    for it in items:
        t0 = time.time()
        try:
            answer = ask(model, it["prompt"], args)
        except Exception as e:
            answer = ""
            print(f"  [{it['id']}] ERROR: {e}")
        hits, total, frac = score_answer(answer, it["groups"])
        passed = hits >= it["min_pass"]
        cap = results["capabilities"].setdefault(it["cap"], {"items": []})
        cap["items"].append({
            "id": it["id"], "hits": hits, "groups": total,
            "score": round(frac, 3), "passed": bool(passed),
            "seconds": round(time.time() - t0, 1),
            "answer": answer if args.full else answer[:400],
        })
        print(f"  [{it['id']}] {CAP_TITLES[it['cap']]}: {hits}/{total} "
              f"({'PASS' if passed else 'fail'}, {time.time() - t0:.1f}s)")

    # aggregate
    for cap, data in results["capabilities"].items():
        scores = [i["score"] for i in data["items"]]
        passes = [i["passed"] for i in data["items"]]
        data["mean_score"] = round(sum(scores) / len(scores), 3)
        data["pass_rate"] = round(sum(passes) / len(passes), 3)
        data["n_items"] = len(scores)
    all_scores = [d["mean_score"] for d in results["capabilities"].values()]
    results["overall_mean"] = round(sum(all_scores) / len(all_scores), 3) if all_scores else 0
    return results


def save_reports(results, args):
    os.makedirs(args.outdir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_model = args.model.replace(":", "_").replace("/", "_")
    json_path = os.path.join(args.outdir, f"baseline_{safe_model}_{stamp}.json")
    md_path = os.path.join(args.outdir, f"baseline_{safe_model}_{stamp}.md")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    m = results["meta"]
    L = [f"# SIRIUS Security Baseline - {m['model']}",
         "",
         f"- Suite: {m['suite_version']} | quick={m['quick']} | raw={m['raw']}",
         f"- Ran at: {m['ran_at']}",
         f"- Overall mean score: **{results['overall_mean']}** (0.0 - 1.0)",
         "",
         "| Capability | Items | Mean score | Pass rate |",
         "|---|---:|---:|---:|"]
    for cap, d in results["capabilities"].items():
        L.append(f"| {CAP_TITLES[cap]} | {d['n_items']} | {d['mean_score']} | {d['pass_rate']} |")
    L.append("")
    L.append("## Item detail")
    for cap, d in results["capabilities"].items():
        L.append(f"### {CAP_TITLES[cap]}")
        for i in d["items"]:
            L.append(f"- **{i['id']}** score {i['score']} ({'PASS' if i['passed'] else 'fail'}, {i['seconds']}s)")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print(f"\nReports written:\n  {json_path}\n  {md_path}")
    return json_path, md_path


def main():
    ap = argparse.ArgumentParser(
        description="Run the SIRIUS Security Baseline suite against a local Ollama model")
    ap.add_argument("--model", default="qwen2.5:0.5b", help="Ollama model tag")
    ap.add_argument("--host", default="http://localhost:11434", help="Ollama API base URL")
    ap.add_argument("--raw", action="store_true",
                    help="use /api/generate raw completion mode (for BASE models)")
    ap.add_argument("--quick", action="store_true", help="3 items per capability instead of all")
    ap.add_argument("--full", action="store_true", help="store full answers in JSON (not truncated)")
    ap.add_argument("--num-predict", type=int, default=240, help="max tokens per answer")
    ap.add_argument("--timeout", type=int, default=240, help="seconds per question")
    ap.add_argument("--outdir", default="sirius_reports", help="report output directory")
    args = ap.parse_args()

    try:
        tags = ollama_get(args.host, "/api/tags")
    except Exception as e:
        sys.exit(f"ERROR: cannot reach Ollama at {args.host} ({e}).\n"
                 "Is Ollama installed and running?  Try:  ollama serve")
    names = [m["name"] for m in tags.get("models", [])]
    print(f"Ollama OK. Installed models: {', '.join(names) or '(none)'}")
    if not any(n.startswith(args.model.split(":")[0]) for n in names):
        print(f"WARNING: {args.model} not in model list - the API call may fail;"
              " pull it first with:  ollama pull " + args.model)

    results = run_suite(args.model, args)
    print(f"\n===== SUMMARY ({args.model}) =====")
    for cap, d in results["capabilities"].items():
        print(f"  {CAP_TITLES[cap]:<36} mean {d['mean_score']:.3f}  pass {d['pass_rate']:.0%}")
    print(f"  {'OVERALL':<36} mean {results['overall_mean']:.3f}")
    save_reports(results, args)


if __name__ == "__main__":
    main()
