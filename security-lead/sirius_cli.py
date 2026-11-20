#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sirius_cli.py — SIRIUS security gate CLI (deterministic, model-free core)
==========================================================================
The operational half of the security-lead role: a fast, deterministic
scanner that runs in CI on every PR, aligned 1:1 with the auditor
taxonomy (LABEL-first findings, same class names, same FIX vocabulary).
The tiny model (sirius-final / sirius-pass6) handles judgment calls via
`ask`; this scanner handles the syntactic classes with zero variance.

Subcommands:
  scan PATH [--format text|json|md] [--include-tests]   full scan
  gate PATH [--fail-on high|medium|low|any] [--changed-only]
        CI mode: exit 1 when findings at/above the threshold exist.
        --changed-only scans files changed vs git HEAD (PR gate).
  report PATH [--out FILE]     markdown report (auditor report format)
  ask "question"               ask the local SIRIUS model (Ollama)

Checks cover the syntactic auditor classes (hardcoded_secret,
sql_injection, command_injection, code_injection_eval,
unsafe_deserialization, ssrf, weak_hash, insecure_random,
tls_verify_disabled, path_traversal, xss, jwt_misuse, cors_misconfig,
secrets_in_logs, mass_assignment, container_latest_tag,
debug_stack_traces, privileged_container). Race conditions, design and
process issues are NOT syntactic — they belong to the lead playbooks and
diff review, and this tool says so instead of guessing.

Inline suppression: append `# sirius-ignore` (with reason if you like).
"""
import os, re, sys, json, argparse, subprocess, importlib.util
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
CODE_EXTS = {".py", ".js", ".ts", ".jsx", ".tsx"}
CONFIG_EXTS = {".yaml", ".yml", ".ini", ".cfg", ".env", ".toml"}
SKIP_DIRS = {".git", "node_modules", "venv", ".venv", "__pycache__",
             "dist", "build", ".tox", "site-packages", ".mypy_cache"}
SELF_EXCLUDE = {"sirius_cli.py"}  # this file's CHECKS table matches itself
MAX_FILE_BYTES = 1_000_000
MAX_FILES = 5000

# (check_id, severity, archetype label, regex, fix, applies_to)
CHECKS = [
    ("hardcoded_secret", "critical",
     "hardcoded secret — credential literal committed in source",
     re.compile(r"(?i)(password|passwd|secret|token|api[_-]?key|"
                r"access[_-]?key|auth[_-]?token|client[_-]?secret|"
                r"routing[_-]?key|_pass|pass_|pwd)\s*[=:]\s*"
                r"['\"]([^'\"]{6,})['\"]"),
     "Move to a secret manager / env injection; rotate the exposed value.",
     "code"),
    ("hardcoded_secret", "critical",
     "hardcoded secret — well-known credential token format in source",
     re.compile(r"(AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{20,}|"
                r"sk-[A-Za-z0-9]{20,}|sk_live_[A-Za-z0-9]{16,}|"
                r"xox[baprs]-[A-Za-z0-9-]{10,}|-----BEGIN (RSA )?PRIVATE KEY-----)"),
     "Revoke/rotate the credential immediately; source it from the "
     "environment.", "code"),
    ("sql_injection", "critical",
     "sql injection — query built by string interpolation/concatenation",
     re.compile(r"(execute|query|raw|rawQuery|executemany)\s*\(\s*"
                r"(f?['\"][^'\"]*(SELECT|INSERT|UPDATE|DELETE)[^'\"]*['\"]\s*[+%]"
                r"|f['\"][^'\"]*\{|['\"].*%\s*\w|\+\s*\w+\s*\+?[^)]*(FROM|WHERE|SELECT))",
                re.I),
     "Use a parameterized query with bound parameters; validate "
     "identifier allowlists for ORDER BY/column names.", "code"),
    ("sql_injection", "critical",
     "sql injection — query assigned from a concatenated template string",
     re.compile(r"(?i)\w+\s*=\s*(['\"]).*?(SELECT|INSERT|UPDATE|DELETE)"
                r".*?\1\s*[+%]"),
     "Use a parameterized query with bound parameters.", "code"),
    ("ssrf", "high",
     "ssrf — attacker-controlled URL/host captured from request data",
     re.compile(r"(?i)\w*(url|host|webhook|endpoint|link|target)\w*\s*=\s*"
                r"(request\.(args|json|form|values|GET|POST|data)[\[.]|"
                r"params\[|req\.(body|query|params)[\[.])"),
     "Allowlist hosts/schemes; resolve DNS and block private/link-local "
     "IPs before connecting.", "code"),
    ("ssrf", "high",
     "ssrf — outbound fetch whose URL/host comes from request data",
     re.compile(r"(requests|httpx|urlopen|fetch)\s*[\(.]\s*[^)]*"
                r"(request\.(args|json|form|values|GET|POST|body|query)|"
                r"params\[|req\.(body|query|params))", re.I),
     "Allowlist hosts/schemes; resolve DNS and block private/link-local "
     "IPs before connecting.", "code"),
    ("command_injection", "critical",
     "command injection — user-influenced string reaches a shell",
     re.compile(r"(os\.(system|popen)\s*\(|shell\s*=\s*True|"
                r"subprocess\.\w+\s*\(\s*f?['\"][^'\"]*[+%]\s*\w|"
                r"child_process\.exec\s*\()"),
     "subprocess with a LIST of arguments and shell=False; validate "
     "input against an allowlist.", "code"),
    ("code_injection_eval", "critical",
     "arbitrary code execution — eval/exec on program-controlled text",
     re.compile(r"(?<![.\w])(eval|exec)\s*\(|compile\s*\([^)]*['\"]<user>"),
     "Parse with a restricted AST/whitelist evaluator; never eval user "
     "text.", "code"),
    ("unsafe_deserialization", "critical",
     "unsafe deserialization — pickle/marshal/allow_pickle on untrusted bytes",
     re.compile(r"(pickle\.(loads?|Unpickler)|marshal\.loads?|"
                r"np\.load\([^)]*allow_pickle\s*=\s*True|"
                r"torch\.load\((?![^)]*weights_only\s*=\s*True))"),
     "Deserialize with json/yaml.safe_load; if binary state is required, "
     "restrict the unpickler and verify a signature.", "code"),
    ("yaml_unsafe_load", "high",
     "unsafe deserialization — yaml.load without a safe Loader is code execution",
     re.compile(r"yaml\.load\s*\((?![^)]*(SafeLoader|safe_load))"),
     "yaml.safe_load, or yaml.load(..., Loader=yaml.SafeLoader).",
     "code"),
    ("weak_hash", "high",
     "weak hash — md5/sha1/unsalted fast hash for security material",
     re.compile(r"hashlib\.(md5|sha1)\s*\(|hashlib\.new\s*\(\s*['\"](md5|sha1)"),
     "Use bcrypt/argon2/scrypt for passwords; HMAC-SHA256+pepper for "
     "token digests.", "code"),
    ("insecure_random", "high",
     "insecure predictable random — random module used for security material",
     re.compile(r"random\.(choice|randint|randrange|getrandbits|random)\s*\("
                r".*(token|key|otp|password|secret|salt|nonce|csrf|session|"
                r"api_key|reset)", re.I),
     "Use secrets.token_urlsafe/token_hex or os.urandom — crypto-grade "
     "randomness only.", "code"),
    ("tls_verify_disabled", "high",
     "tls verification disabled — mitm possible on this trust boundary",
     re.compile(r"(verify\s*=\s*False|ssl\s*=\s*False|CERT_NONE|"
                r"verify_certs\s*=\s*False|check_hostname\s*=\s*False|"
                r"rejectUnauthorized\s*[:=]\s*false|NODE_TLS_REJECT_UNAUTHORIZED)"),
     "Keep certificate verification on; trust an explicit CA bundle "
     "instead.", "code"),
    ("path_traversal", "high",
     "path traversal — request-controlled path component without containment",
     re.compile(r"((open|send_file|sendFile|readFile|createReadStream)"
                r"\s*\([^)]*(request\.(args|form|values|GET|POST|params)|"
                r"req\.(params|query|body)|os\.path\.join\([^)]*(request|req|"
                r"user)))", re.I),
     "Sanitize with basename and verify the resolved realpath stays "
     "inside the intended root.", "code"),
    ("xss", "medium",
     "cross-site scripting (xss) — unescaped user content inserted into HTML",
     re.compile(r"(innerHTML\s*=|dangerouslySetInnerHTML|document\.write\s*\("
                r"|insertAdjacentHTML\s*\(|\|\s*safe\b|v-html)"),
     "Render as text or sanitize with a real HTML sanitizer before "
     "insertion.", "code"),
    ("jwt_misuse", "critical",
     "jwt verification disabled/misconfigured — tokens can be forged",
     re.compile(r"(verify_signature['\"]?\s*:\s*False|"
                r"algorithms\s*=\s*\[[^\]]*['\"]none['\"]|"
                r"get_unverified_header\([^)]*\)\[)"
                ),
     "Verify signatures with the correct key and a pinned algorithm "
     "list; never accept 'none' or header-chosen algs.", "code"),
    ("cors_misconfig", "high",
     "permissive cors — wildcard/reflected origin with credentials",
     re.compile(r"(Access-Control-Allow-Origin['\"]?\s*[:,]\s*['\"]\*['\"]|"
                r"origin\s*:\s*(true|['\"]\*['\"])|"
                r"CORS_ALLOW_ALL_ORIGINS\s*=\s*True|"
                r"supports_credentials\s*=\s*True|"
                r"allow-origin.*request\.headers|"
                r"allow-origin.*\$http_origin|"
                r"Allow-Credentials['\"]?\s*[:,]\s*true)", re.I),
     "Allowlist origins server-side; credentials only for explicitly "
     "trusted first-party origins.", "code"),
    ("secrets_in_logs", "high",
     "secrets written to logs — credential material reaches log pipelines",
     re.compile(r"(print|logging|logger|log|console)\.?\w*\s*\([^)]*"
                r"(password|passwd|secret|token|api[_-]?key|authorization|"
                r"credential)", re.I),
     "Log identifiers and outcomes only; scrub credential fields at the "
     "logger boundary.", "code"),
    ("mass_assignment", "high",
     "mass assignment — whole request payload bound to a model",
     re.compile(r"(\w+\s*\(\s*\*\*request\.(json|data|form|values|POST|GET)"
                r"|\*\*req\.(body|query)|setattr\s*\(\s*\w+\s*,\s*(k|key|field)"
                r".*request)", re.I),
     "Bind an explicit field allowlist/schema; ignore unknown keys "
     "loudly.", "code"),
    ("container_latest_tag", "medium",
     "container image uses latest tag — mutable, non-reproducible builds",
     re.compile(r"(?i)^(FROM\s+\S+:latest|.*image:\s*\S+:latest\s*$)"),
     "Pin a version tag or digest (immutable, verifiable).", "config"),
    ("debug_stack_traces", "medium",
     "debug/stack traces exposed in production — information disclosure",
     re.compile(r"(?i)(APP_DEBUG\s*[=:]\s*true|DEBUG\s*=\s*True\b|"
                r"app\.run\(.*debug\s*=\s*True|debug\s*:\s*true)"),
     "DEBUG=False in prod; generic error pages; traces to server logs "
     "only.", "config"),
    ("privileged_container", "high",
     "privileged container — near-host power at runtime",
     re.compile(r"(?i)(privileged\s*:\s*true)"),
     "Set privileged:false; bake tools into the image; add only specific "
     "capabilities/devices if truly needed.", "config"),
    ("directory_listing", "medium",
     "directory listing enabled — tree enumeration exposed",
     re.compile(r"(?i)(autoindex\s+on|Options\s+\+?Indexes)"),
     "autoindex off / Options -Indexes; 403 on directory URIs.",
     "config"),
    ("plain_http_admin", "high",
     "admin/ops endpoint over plain http — credentials cross in cleartext",
     re.compile(r"(?i)['\"]?http://(admin|ops|internal|grafana|jenkins|"
                r"prometheus)[^'\"]*['\"]?"),
     "Serve admin surfaces over https with the internal CA; redirect "
     "http.", "code"),
]

IGNORE_RE = re.compile(r"#\s*sirius-ignore")

# Context helper for insecure_random: a bare random.* call is only a
# finding inside a function whose name says it produces security material
# (token/key/otp/...). Outside such functions, random.* is usually fine.
BARE_RANDOM_RX = re.compile(
    r"random\.(choice|randint|randrange|getrandbits|random|uniform)\s*\(")
SEC_FN_RX = re.compile(
    r"(?i)^\s*def\s+\w*(token|key|otp|password|passwd|secret|salt|nonce|"
    r"csrf|session|api_key|reset|otp)\w*\s*\(")
ANY_DEF_RX = re.compile(r"^\s*(def |class )")


def _in_security_fn(line, sec_fn):
    if SEC_FN_RX.match(line):
        return True
    if ANY_DEF_RX.match(line):
        return False
    return sec_fn


def iter_files(root, include_tests=False):
    if os.path.isfile(root):
        yield root
        return
    count = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames
                       if d not in SKIP_DIRS and not d.startswith(".")]
        for fn in sorted(filenames):
            ext = os.path.splitext(fn)[1].lower()
            base = fn.lower()
            is_config = ext in CONFIG_EXTS or base.startswith("dockerfile")
            if ext not in CODE_EXTS and not is_config:
                continue
            if not include_tests and (
                    "/test" in dirpath.replace("\\", "/").lower()
                    or base.startswith("test_")):
                continue
            p = os.path.join(dirpath, fn)
            if fn in SELF_EXCLUDE:
                continue
            try:
                if os.path.getsize(p) > MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            count += 1
            if count > MAX_FILES:
                print(f"WARN: file cap {MAX_FILES} reached; scan truncated",
                      file=sys.stderr)
                return
            yield p


def kind_for(path):
    base = os.path.basename(path).lower()
    ext = os.path.splitext(path)[1].lower()
    if ext in CONFIG_EXTS or base.startswith("dockerfile"):
        return "config"
    return "code"


def scan_path(root, include_tests=False):
    findings = []
    for path in iter_files(root, include_tests):
        kind = kind_for(path)
        try:
            lines = open(path, encoding="utf-8", errors="replace") \
                .read().splitlines()
        except OSError:
            continue
        sec_fn = False
        for i, line in enumerate(lines, 1):
            if IGNORE_RE.search(line):
                continue
            sec_fn = _in_security_fn(line, sec_fn)
            for cid, sev, label, rx, fix, applies in CHECKS:
                if applies == "config" and kind != "config":
                    continue  # container/nginx checks only on config files
                matched = rx.search(line)
                if cid == "insecure_random" and not matched and sec_fn:
                    matched = BARE_RANDOM_RX.search(line)
                if matched:
                    findings.append({
                        "file": path, "line": i, "check": cid,
                        "severity": sev, "label": label,
                        "snippet": line.strip()[:200], "fix": fix,
                    })
    findings.sort(key=lambda f: (SEVERITY_ORDER[f["severity"]], f["file"],
                                 f["line"]))
    return findings


def changed_files(root):
    try:
        out = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=root if os.path.isdir(root) else os.path.dirname(root),
            capture_output=True, text=True, check=True).stdout
        return [l.strip() for l in out.splitlines() if l.strip()]
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("WARN: not a git repo or git unavailable — full scan",
              file=sys.stderr)
        return None


def print_text(findings, root):
    if not findings:
        print("LABEL: no vulnerability found\n"
              "No syntactic auditor-class findings in the scanned files. "
              "This covers the checkable classes only — races, design and "
              "process issues need the lead playbooks / diff review.")
        return
    print(f"{len(findings)} finding(s):\n")
    for f in findings:
        print(f"[{f['severity'].upper()}] {f['file']}:{f['line']} "
              f"({f['check']})")
        print(f"  LABEL: {f['label']}")
        print(f"  SNIPPET: {f['snippet']}")
        print(f"  FIX: {f['fix']}\n")


def report_md(findings, root):
    by_sev = {}
    for f in findings:
        by_sev.setdefault(f["severity"], []).append(f)
    lines = ["# Security Scan — SIRIUS (deterministic gate)",
             "", f"Date: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
             f"Scope: `{root}` (syntactic classes only)",
             "",
             "## 1. Executive summary",
             ""]
    if not findings:
        lines.append("No syntactic auditor-class findings. Race conditions, "
                     "design and process concerns are outside scanner scope "
                     "and require the lead playbooks / diff review.")
    else:
        counts = ", ".join(
            f"{s}: {len(v)}" for s, v in
            sorted(by_sev.items(), key=lambda kv: SEVERITY_ORDER[kv[0]]))
        lines.append(f"{len(findings)} findings ({counts}). Most urgent: "
                     f"{by_sev[sorted(by_sev, key=lambda s: SEVERITY_ORDER[s])[0]][0]['label']}.")
        lines += ["", "## 3. Findings", ""]
        n = 0
        for sev in sorted(by_sev, key=lambda s: SEVERITY_ORDER[s]):
            for f in by_sev[sev]:
                n += 1
                lines += [f"### SIRIUS-{n} [{sev.upper()}] {f['check']}",
                          "", f"- **LABEL:** {f['label']}",
                          f"- **LOCATION:** `{f['file']}:{f['line']}`",
                          f"- **EVIDENCE:** `{f['snippet']}`",
                          f"- **FIX:** {f['fix']}", ""]
        lines += ["## 5. Remediation plan",
                  "",
                  "1. Criticals first (credentials: rotate immediately; "
                  "injection classes: parameterize/allowlist).",
                  "2. Config hardening (TLS, debug, containers).",
                  "3. Wire `sirius gate --changed-only --fail-on high` into "
                  "CI so this class never returns."]
    return "\n".join(lines) + "\n"


def read_text(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


# --- Dynamic context routing (small-model attention budget) -----------------
# A 0.5B model loses the core instruction when fed ROLE.md + 9 playbooks at
# once. Route the question to ONE playbook and inject only its check inventory.
PLAYBOOK_ROUTES = {
    "threat_modeling":        ("threat", "stride", "attack surface", "data flow", "trust boundary", "abuse case"),
    "secure_architecture":    ("architecture", "design review", "microservice", "service boundary", "topology"),
    "secure_code_review":     ("diff", "pull request", "code review", "commit", "patch", "snippet", "function"),
    "api_security":           ("api", "openapi", "endpoint", "rest", "graphql", "bola", "idor", "rest contract"),
    "ci_pipeline_security":   ("ci", "pipeline", "workflow", "runner", "github action", "build script", "deploy step"),
    "container_k8s_security": ("container", "dockerfile", "kubernetes", "k8s", "pod", "image", "helm"),
    "secrets_management":     ("secret", "credential", "api key", "token", "vault", "rotation", "env var"),
    "incident_response":      ("incident", "breach", "alert", "on-call", "containment", "forensics", "postmortem"),
    "logging_monitoring":     ("logging", "monitoring", "telemetry", "audit log", "siem", "alerting", "observability"),
}


def route_playbook(question):
    """Return the single most relevant playbook stem for a question."""
    q = question.lower()
    best, hits = None, 0
    for stem, keys in PLAYBOOK_ROUTES.items():
        n = sum(1 for k in keys if k in q)
        if n > hits:
            best, hits = stem, n
    return best or "secure_code_review"


def routed_system_prompt(question):
    """ROLE.md answer contract + ONE routed playbook's check inventory."""
    corpus = os.path.join(os.path.dirname(HERE), "sirius-security-lead-corpus")
    stem = route_playbook(question)
    role = ""
    role_path = os.path.join(corpus, "ROLE.md")
    if os.path.isfile(role_path):
        role = read_text(role_path)
        marker = "## Answer contract"
        if marker in role:
            role = role[role.index(marker):]
            stop = role.find("\n## ", 5)
            if stop > 0:
                role = role[:stop]
    pb_path = os.path.join(corpus, stem + ".md")
    playbook = read_text(pb_path) if os.path.isfile(pb_path) else ""
    start = playbook.find("## 2. Check inventory")
    if start >= 0:
        end = playbook.find("\n## ", start + 5)
        playbook = playbook[start:end if end > 0 else len(playbook)]
    system = ("You are SIRIUS, head of security. Follow this answer contract.\n\n"
              + role.strip() + "\n\n# Routed playbook\n" + playbook.strip())
    return system, stem


def cmd_ask(question, model, host, timeout):
    spec = importlib.util.spec_from_file_location(
        "sirius04", os.path.join(HERE, "04_sirius_baseline.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sirius04"] = mod
    spec.loader.exec_module(mod)
    system, stem = routed_system_prompt(question)
    print(f"[routed playbook: {stem}]", file=sys.stderr)
    d = mod.ollama_post(host, "/api/chat", {
        "model": model, "stream": False,
        # Deterministic, conservative decoding for a 0.5B auditor:
        # low temperature + min-p cuts the "vulnerability theater" tail;
        # a light repetition penalty breaks small-model loops.
        "options": {"temperature": 0.2, "min_p": 0.05,
                    "repeat_penalty": 1.1, "num_predict": 400},
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": question}]}, timeout)
    print(d.get("message", {}).get("content", "").strip())


def main():
    ap = argparse.ArgumentParser(
        description="SIRIUS security gate CLI")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_scan = sub.add_parser("scan")
    p_scan.add_argument("path")
    p_scan.add_argument("--format", choices=["text", "json", "md"],
                        default="text")
    p_scan.add_argument("--include-tests", action="store_true")

    p_gate = sub.add_parser("gate")
    p_gate.add_argument("path")
    p_gate.add_argument("--fail-on", default="high",
                        choices=["critical", "high", "medium", "low", "any"])
    p_gate.add_argument("--changed-only", action="store_true")
    p_gate.add_argument("--include-tests", action="store_true")

    p_rep = sub.add_parser("report")
    p_rep.add_argument("path")
    p_rep.add_argument("--out", default=None)
    p_rep.add_argument("--include-tests", action="store_true")

    p_ask = sub.add_parser("ask")
    p_ask.add_argument("question")
    p_ask.add_argument("--model", default="sirius-final")
    p_ask.add_argument("--host", default="localhost:11434")
    p_ask.add_argument("--timeout", type=int, default=120)

    args = ap.parse_args()
    if args.cmd == "ask":
        cmd_ask(args.question, args.model, args.host, args.timeout)
        return

    include_tests = getattr(args, "include_tests", False)
    findings = scan_path(args.path, include_tests)
    if args.cmd == "gate" and args.changed_only:
        changed = changed_files(args.path)
        if changed is not None:
            cs = set(changed)
            findings = [f for f in findings if f["file"] in cs]
            print(f"Scanning {len(cs)} changed file(s) vs HEAD")

    if args.cmd == "scan":
        if args.format == "json":
            print(json.dumps(findings, indent=2))
        elif args.format == "md":
            print(report_md(findings, args.path), end="")
        else:
            print_text(findings, args.path)
    elif args.cmd == "gate":
        if args.fail_on == "any":
            bad = findings
        else:
            bad = [f for f in findings
                   if SEVERITY_ORDER[f["severity"]]
                   <= SEVERITY_ORDER[args.fail_on]]
        if bad:
            print(f"GATE: FAIL — {len(bad)} finding(s) at/above "
                  f"'{args.fail_on}'")
            for f in bad[:20]:
                print(f"  [{f['severity'].upper()}] {f['file']}:"
                      f"{f['line']} {f['check']}: {f['label']}")
            sys.exit(1)
        print(f"GATE: PASS — no findings at/above '{args.fail_on}' "
              f"({len(findings)} below threshold, informational)")
    elif args.cmd == "report":
        md = report_md(findings, args.path)
        if args.out:
            with open(args.out, "w", encoding="utf-8") as fh:
                fh.write(md)
            print(f"Wrote {args.out}")
        else:
            print(md, end="")


if __name__ == "__main__":
    main()
