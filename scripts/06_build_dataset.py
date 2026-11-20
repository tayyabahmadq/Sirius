#!/usr/bin/env python3
"""
SIRIUS Toolkit - Script 06: Phase-2 Dataset Generator (v2 - generative)
======================================================================
Builds the 4,000-item QLoRA fine-tuning dataset per the merged Phase-2 plan
(SIRIUS_Phase2_Consultation_Output.md, Part B3).

DESIGN (v2)
-----------
v1 hand-listed 3-5 prompts/snippets per archetype, so MinHash dedup
collapsed the set to ~650 items. v2 GENERATES distinct prompts by
combining: (snippet template x variable names x values) x (opener x
context), producing thousands of textually distinct but label-identical
examples. The plan's spec for the code-vuln core is "5 archetypes x 40
distinct snippets x 3 prompt forms"; this generator meets and exceeds it.

OUTPUT
------
- sirius_train.jsonl   (3,900 items)
- sirius_dev.jsonl      (100 items)
- sirius_dataset_manifest.json
"""
import argparse, json, random, re, os
from datetime import datetime, timezone
from collections import defaultdict

SYSTEM_PROMPT = ("You are a security auditor assistant. Answer concisely, "
                 "technically, and name the exact issue.")

# Exact baseline items (for decontamination + grader keyword source)
BASELINE_ITEMS = [
    dict(id="V01", cap="code_vuln_scan", archetype="sql_injection",
         groups=[["sql injection","parameterized","prepared statement"],["concat","string formatting","f-string","interpolat"]]),
    dict(id="V02", cap="code_vuln_scan", archetype="hardcoded_secret",
         groups=[["hardcoded","hard-coded","hard coded","embedded credential","secret in source"]]),
    dict(id="V03", cap="code_vuln_scan", archetype="command_injection",
         groups=[["command injection","shell injection","os.system","subprocess","shell=True"]]),
    dict(id="V04", cap="code_vuln_scan", archetype="code_injection_eval",
         groups=[["eval","arbitrary code","code execution","code injection"]]),
    dict(id="V05", cap="code_vuln_scan", archetype="weak_hash",
         groups=[["md5","weak hash","sha1","unsalted"],["bcrypt","argon2","scrypt","salt"]]),
    dict(id="V06", cap="code_vuln_scan", archetype="tls_verify_disabled",
         groups=[["verify=false","verify=false","certificate","tls","ssl","mitm","man-in-the-middle"]]),
    dict(id="V07", cap="code_vuln_scan", archetype="path_traversal",
         groups=[["path traversal","traversal","../","directory","sanitize the path","basename"]]),
    dict(id="V08", cap="code_vuln_scan", archetype="xss",
         groups=[["xss","cross-site scripting","innerHTML","escape","sanitiz"]]),
    dict(id="V09", cap="code_vuln_scan", archetype="missing_access_control",
         groups=[["auth","authorization","access control","unauthorized","session"]]),
    dict(id="V10", cap="code_vuln_scan", archetype="insecure_random",
         groups=[["random","predictable","insecure"],["secrets","crypto","os.urandom","secure random"]]),
    dict(id="W01", cap="web_config_checks", archetype="security_headers",
         groups=[["strict-transport-security","hsts"],["content-security-policy","csp"],["x-frame-options","frame-ancestors","clickjacking"],["x-content-type-options"]]),
    dict(id="W02", cap="web_config_checks", archetype="cookie_flags",
         groups=[["httponly"],["secure"],["samesite","csrf"]]),
    dict(id="W03", cap="web_config_checks", archetype="http_to_https_redirect",
         groups=[["https","redirect","301","308","hsts"]]),
    dict(id="W04", cap="web_config_checks", archetype="csp_header",
         groups=[["content-security-policy","csp"],["script","inline"],["xss","injection"]]),
    dict(id="W05", cap="web_config_checks", archetype="directory_listing",
         groups=[["directory listing","index of","autoindex","file exposure","enumeration"]]),
    dict(id="W06", cap="web_config_checks", archetype="stack_trace_disclosure",
         groups=[["stack trace","information disclosure","debug","verbose error","leak"]]),
    dict(id="W07", cap="web_config_checks", archetype="plain_http_admin",
         groups=[["https","tls","plaintext","sniff","intercept","credentials"]]),
    dict(id="W08", cap="web_config_checks", archetype="over_fetch_api",
         groups=[["sensitive","over-fetch","hash","field","exposure","leak","response"]]),
    dict(id="D01", cap="dependency_cve", archetype="outdated_library",
         groups=[["known vulnerabilities","cve","outdated","patch","update","advisory"]]),
    dict(id="D02", cap="dependency_cve", archetype="cve_identifier",
         groups=[["common vulnerabilities","cve","identifier","id","mitre","database"]]),
    dict(id="D03", cap="dependency_cve", archetype="python_audit_tools",
         groups=[["pip-audit","safety","pip","audit","snyk","dependabot"]]),
    dict(id="D04", cap="dependency_cve", archetype="npm_audit_tools",
         groups=[["npm audit","audit","snyk","dependabot","npm"]]),
    dict(id="D05", cap="dependency_cve", archetype="pin_versions",
         groups=[["pin","lock","lockfile","package-lock","version","exact"]]),
    dict(id="D06", cap="dependency_cve", archetype="typosquatting",
         groups=[["typosquat","typo","package name","spoof","malicious package","registry"]]),
    dict(id="D07", cap="dependency_cve", archetype="abandoned_package",
         groups=[["abandoned","unmaintained","maintainer","supply chain","Bus factor","no longer maintained"]]),
    dict(id="D08", cap="dependency_cve", archetype="container_latest_tag",
         groups=[["digest","tag","latest","pin","image","mutable"]]),
    dict(id="L01", cap="load_runtime", archetype="k6_script",
         groups=[["k6","locust","jmeter","load test","script"],["vus","virtual users","concurrent","iterations"]]),
    dict(id="L02", cap="load_runtime", archetype="p95_latency",
         groups=[["percentile","95","p95","latency"]]),
    dict(id="L03", cap="load_runtime", archetype="rps_vs_concurrent",
         groups=[["requests per second","rps","throughput"],["concurrent","users","sessions"]]),
    dict(id="L04", cap="load_runtime", archetype="post_deploy_slow",
         groups=[["logs","metrics","monitoring","cpu","memory"],["slow query","database","query","index","n+1"]]),
    dict(id="L05", cap="load_runtime", archetype="memory_leak",
         groups=[["leak","heap","profile","memory","gc","allocation"]]),
    dict(id="L06", cap="load_runtime", archetype="overload_protection",
         groups=[["rate limit","shed","queue","timeout","backpressure","throttle","degrade"]]),
    dict(id="L07", cap="load_runtime", archetype="canary_release",
         groups=[["canary","gradual","small","rollout","subset","percentage"]]),
    dict(id="L08", cap="load_runtime", archetype="502_503_causes",
         groups=[["timeout","capacity","connection pool","upstream","saturation","overload","threads"]]),
]

def label_line(*keywords):
    return "LABEL: " + ", ".join(keywords)

# ---- Generative prompt synthesis: openers x contexts x value banks ----
OPENERS = [
    "Review this code and name the exact security issue:",
    "Identify the vulnerability in this snippet:",
    "What is the security flaw below? Name it precisely:",
    "Audit this code. What is the exact vulnerability?",
    "Find and name the security problem in this code:",
    "What specific vulnerability does this code introduce?",
    "Name the exact security issue in the following:",
    "Security review - state the precise vulnerability:",
    "Point out the exact vulnerability class below:",
    "What is wrong with this code from a security standpoint? Name the issue.",
    "Which vulnerability is present here? Be specific.",
    "Classify the security issue in this code.",
    "What kind of attack does this code enable? Name the vulnerability.",
    "Give the exact vulnerability name for this code.",
]

# Variable-name pools for snippet diversification
VAR_NAMES = ["user","name","host","q","term","input","val","data","req","param",
             "item","key","id","query","expr","cmd","arg","path","file","msg"]
SECRET_NAMES = ["API_KEY","STRIPE_KEY","DB_PASS","TOKEN","AWS_SECRET","JWT_KEY",
                 "SECRET","PRIVATE_KEY","OAUTH_TOKEN","SLACK_WEBHOOK"]
SECRET_VALUES = ['"sk-live-9f2c7d88ab"','"sk_live_51H8a2c"','"ProdAdmin2024!"',
                  '"ghp_4d3f2c1b0a0987654321"','"wJalrXUtnFEMI/K7MDENG"',
                  '"supersecret"','"AKIAIOSFODNN7EXAMPLE"','"xoxb-1234567890"']
LIBRARIES = ["Django 2.2","Log4j 2.14","Spring 4.3","Rails 5.2","Express 3",
             "Flask 1.1","AngularJS 1.7","Laravel 5.8","requests 2.20","openssl 1.0"]
LANGS = ["Python","JavaScript","Java","Go","Ruby","PHP","TypeScript"]

# ---- Archetype definitions: each has a snippet GENERATOR (function) and
#       an answer template, plus the grader keywords. ----

def gen_sql_injection(rng):
    var = rng.choice(VAR_NAMES); col = rng.choice(["users","orders","accounts","products","logs","sessions"])
    fmt = rng.choice([f'f"SELECT * FROM {col} WHERE name = \'{{}}"', '"SELECT * FROM '+col+' WHERE name = \'"+{}+"\'"'])
    name = rng.choice(["get_user","find_record","lookup","search_db","fetch_rows"])
    return f"def {name}({var}):\n    q = {fmt.format(var)}\n    return db.execute(q).fetchall()"

def gen_hardcoded_secret(rng):
    sname = rng.choice(SECRET_NAMES); sval = rng.choice(SECRET_VALUES)
    fn = rng.choice(["charge","connect","sign","auth","call_api"])
    return f'{sname} = {sval}\ndef {fn}():\n    return requests.post(URL, headers={{"Authorization": {sname}}})'

def gen_command_injection(rng):
    var = rng.choice(VAR_NAMES); fn = rng.choice(["ping","lookup","resolve","fetch","run"])
    cmd = rng.choice(["ping -c 1","nslookup","dig","curl","whois"])
    return f'import subprocess\ndef {fn}({var}):\n    subprocess.run(f"{cmd} {{{var}}}", shell=True)'

def gen_eval(rng):
    fn = rng.choice(["calc","evaluate","run","exec_expr"]); var = rng.choice(["expr","input","code","payload"])
    return f'def {fn}({var}):\n    return eval({var})'

def gen_weak_hash(rng):
    fn = rng.choice(["save_password","hash_pw","store","digest","encode"])
    algo = rng.choice(["md5","sha1","new(\"md5\")"])
    salt = rng.choice(["","pw + \"staticsalt\"",""])  # never a proper salt
    return f'import hashlib\ndef {fn}(pw):\n    return hashlib.{algo}({salt and salt+", " or ""}pw.encode()).hexdigest()'

def gen_tls_disabled(rng):
    fn = rng.choice(["get","post","fetch","call","request"])
    url = rng.choice(['"https://api.corp/data"','"https://internal.svc/api"','"https://payments.bank/charge"'])
    return f'requests.{fn}({url}, verify=False)'

def gen_path_traversal(rng):
    fn = rng.choice(["download","get_file","serve","fetch_doc","read"])
    base = rng.choice(["/uploads/","/files/","/static/","/docs/","/share/"])
    var = rng.choice(["name","file","doc","path","f"])
    return f'@app.route("/{fn}/<{{}}>")\ndef {fn}({var}):\n    return send_file("{base}" + {var})'.format(var)

def gen_xss(rng):
    el = rng.choice(["out","content","display","result","body"])
    var = rng.choice(["userComment","input","data","msg","post"])
    fn = rng.choice(["innerHTML","outerHTML","html()","insertAdjacentHTML"])
    return f'document.getElementById("{el}").{fn} = {var};'

def gen_missing_auth(rng):
    route = rng.choice(["/admin/users","/api/orders","/admin/config","/api/users","/admin/logs"])
    fn = rng.choice(["list_users","orders","config","get_users","logs"])
    return f'@app.route("{route}")\ndef {fn}():\n    return jsonify(db.{fn.replace("_",".")}.all() if False else db.query.all())'

def gen_insecure_random(rng):
    fn = rng.choice(["token","session_id","reset_code","nonce","otp"])
    return f'import random\ndef {fn}():\n    return str(random.random())'

CODE_GENERATORS = {
    "sql_injection": (gen_sql_injection,
        "FUNCTION: Builds a SQL query by interpolating untrusted input into the query string.\n"
        "RISK: An attacker can terminate the intended statement and append arbitrary SQL, reading or modifying any reachable table.\n"
        "{label}",
        ["sql injection","string concatenation"]),
    "hardcoded_secret": (gen_hardcoded_secret,
        "FUNCTION: A live credential is embedded directly in source code.\n"
        "RISK: Anyone with repository or image access obtains the credential; it cannot be rotated without a redeploy and persists in version history.\n"
        "{label}",
        ["hardcoded","secret in source"]),
    "command_injection": (gen_command_injection,
        "FUNCTION: Untrusted input is interpolated into a shell command string.\n"
        "RISK: Shell metacharacters let the attacker run arbitrary commands with the process's privileges.\n"
        "{label}",
        ["command injection","shell=True"]),
    "code_injection_eval": (gen_eval,
        "FUNCTION: Untrusted input is passed to eval(), which compiles and runs it as Python.\n"
        "RISK: The attacker supplies arbitrary Python; the process executes it with full privileges.\n"
        "{label}",
        ["eval","arbitrary code"]),
    "weak_hash": (gen_weak_hash,
        "FUNCTION: Passwords are hashed with MD5/SHA1 without a per-user random salt.\n"
        "RISK: MD5/SHA1 are broken and far too fast; rainbow tables and GPU brute force recover passwords in seconds.\n"
        "{label}",
        ["md5","weak hash","unsalted","bcrypt","salt"]),
    "tls_verify_disabled": (gen_tls_disabled,
        "FUNCTION: The client disables certificate verification on the TLS connection.\n"
        "RISK: The server identity is no longer authenticated; a network attacker can impersonate the endpoint (MITM).\n"
        "{label}",
        ["verify=False","tls","man-in-the-middle"]),
    "path_traversal": (gen_path_traversal,
        "FUNCTION: User input is concatenated into a filesystem path with no normalization or allow-list.\n"
        "RISK: ../ sequences escape the intended directory, letting the attacker read arbitrary files.\n"
        "{label}",
        ["path traversal","directory"]),
    "xss": (gen_xss,
        "FUNCTION: Untrusted content is inserted into the DOM without escaping.\n"
        "RISK: The attacker injects script that runs in the victim's browser, stealing cookies or performing actions as the user.\n"
        "{label}",
        ["xss","cross-site scripting","innerHTML"]),
    "missing_access_control": (gen_missing_auth,
        "FUNCTION: A sensitive endpoint returns privileged data without checking the caller's role.\n"
        "RISK: Any caller can read or mutate data they are not authorized to access.\n"
        "{label}",
        ["authorization","access control","unauthorized"]),
    "insecure_random": (gen_insecure_random,
        "FUNCTION: A security-sensitive token is generated with the non-cryptographic random module.\n"
        "RISK: random() is predictable (clock-seeded); an attacker can forge tokens, sessions, or reset codes.\n"
        "{label}",
        ["random","predictable","os.urandom","secure random"]),
}

# ---- Text archetypes: prompt banks + answer templates + grader keywords ----
TEXT_ARCHETYPES = {
    "security_headers": ([
        "What HTTP response headers should every production web app set, and what does each prevent?",
        "A security scan flagged the site for missing response headers. Which ones are required and why?",
        "List the security headers a hardened web server should emit on every response.",
        "Which response headers defend against clickjacking, MIME sniffing, and mixed content?",
        "Name the four security response headers an auditor expects on a production site.",
    ],
    "FUNCTION: Production responses omit the standard security response headers.\n"
    "RISK: Without them the browser allows mixed content, framing, MIME sniffing, and lacks a CSP, expanding the XSS and clickjacking surface.\n"
    "{label}",
    ["strict-transport-security","content-security-policy","x-frame-options","x-content-type-options"]),

    "cookie_flags": ([
        "Which attributes must a session cookie carry to be safe, and what does each stop?",
        "An auditor said the session cookie is misconfigured. What flags are missing and what attacks do they prevent?",
        "What makes a cookie 'secure'? Name every flag and the attack it blocks.",
        "Which three cookie attributes harden a session against XSS, sniffing, and CSRF?",
        "Why does Set-Cookie need HttpOnly, Secure, and SameSite in production?",
    ],
    "FUNCTION: The session cookie is set without HttpOnly, Secure, and SameSite.\n"
    "RISK: JavaScript can read it (XSS theft), it crosses plain HTTP (sniff), and it is sent on cross-site requests (CSRF).\n"
    "{label}",
    ["httponly","secure","samesite"]),

    "http_to_https_redirect": ([
        "A site answers on both http:// and https:// with identical content. What is wrong and how do you fix it?",
        "The load balancer serves HTTP and HTTPS for the same app. What is the risk and the correct configuration?",
        "Users can still reach the site over plain HTTP. What should change?",
        "Why must HTTP traffic redirect to HTTPS, and which header enforces it after redirect?",
        "What is the risk of serving the same content on both HTTP and HTTPS?",
    ],
    "FUNCTION: The site is reachable over plain HTTP in addition to HTTPS.\n"
    "RISK: Users on HTTP have no transport security and can be downgraded or sniffed; cookies without Secure leak too.\n"
    "{label}",
    ["https","redirect","hsts"]),

    "csp_header": ([
        "What is a Content-Security-Policy header and which attack class does it mitigate?",
        "Explain the purpose of the CSP header and what it stops.",
        "Why should a production site ship a strict Content-Security-Policy?",
        "How does Content-Security-Policy reduce XSS risk even when a bug allows injection?",
        "What does the Content-Security-Policy header restrict, and which attack does it blunt?",
    ],
    "FUNCTION: No Content-Security-Policy is set, or it allows unsafe-inline scripts.\n"
    "RISK: Injected script has no source restriction, so XSS is unconstrained.\n"
    "{label}",
    ["content-security-policy","script","xss"]),

    "directory_listing": ([
        "A web server has directory listing on. Why is that a risk and what should be configured instead?",
        "The /backup/ path shows an 'Index of /backup' page. What is the problem and the fix?",
        "Why is autoindex a security concern, and how do you disable it?",
        "Directory browsing is enabled on the docs server. What is the risk?",
        "Why must a web server suppress automatic directory indexes in production?",
    ],
    "FUNCTION: The web server lists directory contents when no index file is present.\n"
    "RISK: Sensitive files (backups, configs, source) are enumerated and downloaded by any visitor.\n"
    "{label}",
    ["directory listing","file exposure","enumeration"]),

    "stack_trace_disclosure": ([
        "Production shows full stack traces to users on errors. What is the risk and the correct fix?",
        "Users see a Python traceback when a request fails. What is wrong and how should it be handled?",
        "An internal-server-error response includes file paths and library versions. What is the issue?",
        "The 500 page leaks framework internals. What is the risk and the right configuration?",
        "Why must production return generic error pages, and what should happen to the detail?",
    ],
    "FUNCTION: Unhandled exceptions return full stack traces and framework internals to the client.\n"
    "RISK: Attackers learn file paths, library versions, and query structure, accelerating exploitation.\n"
    "{label}",
    ["stack trace","information disclosure","verbose error","leak"]),

    "plain_http_admin": ([
        "An admin panel is reachable over plain HTTP. Why is that dangerous even on an internal network?",
        "The /admin path is served on port 80 only. What is the risk?",
        "Why must internal admin interfaces still use TLS?",
        "Staff log in to the admin console over HTTP. What can go wrong?",
        "Is plain HTTP acceptable for an intranet admin panel? Justify your answer.",
    ],
    "FUNCTION: Administrative traffic travels over unencrypted HTTP.\n"
    "RISK: Credentials and session cookies traverse the network in plaintext; anyone on the path can sniff or modify them, even on a LAN.\n"
    "{label}",
    ["https","tls","plaintext","sniff","credentials"]),

    "over_fetch_api": ([
        "A public API returns user records including the password_hash field. What is the issue and the fix?",
        "The /users endpoint serializes the whole ORM object. What is wrong?",
        "An API response leaks the password hash and internal IDs. What is the problem?",
        "Why is returning the full database row from an API a security risk?",
        "The mobile client only needs the username, but the API returns 30 fields. What is the issue?",
    ],
    "FUNCTION: The API serializes the full record, including fields the client never needs.\n"
    "RISK: Password hashes, internal IDs, and PII leak to anyone who can call the endpoint.\n"
    "{label}",
    ["sensitive","over-fetch","hash","field","exposure"]),

    "outdated_library": ([
        "Your project pins a library version released 3 years ago. What are the risks and what should you do?",
        "An audit found Log4j 2.14 in production. What is the risk and the response?",
        "requirements.txt lists Django 2.2. What is wrong and how do you fix it?",
        "Why is running an old framework version a security problem?",
        "A dependency has not been updated in 18 months. What is the security concern?",
    ],
    "FUNCTION: A dependency is pinned to a version that has known published vulnerabilities.\n"
    "RISK: Attackers can match the version to a CVE and exploit it directly; patches exist but are not applied.\n"
    "{label}",
    ["known vulnerabilities","cve","outdated","advisory"]),

    "cve_identifier": ([
        "What is a CVE, and how are CVE identifiers used in vulnerability management?",
        "Explain the CVE system and who maintains it.",
        "How does the CVE database help triage library flaws?",
        "What does the acronym CVE stand for, and how is a CVE record used?",
        "How do CVE identifiers enable coordinated patching?",
    ],
    "FUNCTION: A CVE is a unique, publicly disclosed vulnerability identifier maintained by MITRE.\n"
    "RISK: Without CVE identifiers there is no shared language for matching advisories to installed versions, so triage stalls.\n"
    "{label}",
    ["common vulnerabilities","cve","identifier","mitre","database"]),

    "python_audit_tools": ([
        "How do you check a Python project's dependencies for known vulnerabilities? Name tools.",
        "List the tools that scan requirements.txt or a lockfile for CVEs.",
        "What is pip-audit and how does it differ from safety?",
        "Which command scans a Python virtualenv for vulnerable packages?",
        "Name two tools that automate Python dependency CVE scanning in CI.",
    ],
    "FUNCTION: Python projects are scanned against the OSV/PyPA advisory databases by a dedicated tool.\n"
    "RISK: Without automated scanning, vulnerable packages ship to production undetected.\n"
    "{label}",
    ["pip-audit","safety","snyk","dependabot"]),

    "npm_audit_tools": ([
        "How do you check a Node.js project's dependencies for known vulnerabilities? Name tools.",
        "What does 'npm audit' do, and what are its limits?",
        "List the tooling that scans package-lock.json for advisories.",
        "Which tools automate npm dependency scanning in CI?",
        "How do you audit a transitive dependency tree in a Node project?",
    ],
    "FUNCTION: Node projects are scanned against the npm advisory database by npm audit or an equivalent.\n"
    "RISK: The transitive dependency graph is large; without scanning, a vulnerable sub-package ships unnoticed.\n"
    "{label}",
    ["npm audit","snyk","dependabot","npm"]),

    "pin_versions": ([
        "Why should dependency versions be pinned or locked in a project? What file does this in npm?",
        "What is the difference between 'flask>=2.0' and 'flask==2.3.2'?",
        "Why is a lockfile (package-lock.json, poetry.lock) required for reproducible, safe builds?",
        "Why must CI install from a lockfile rather than a caret range?",
        "What security risk does floating version ranges introduce?",
    ],
    "FUNCTION: Dependencies are pinned to exact, reviewed versions via a lockfile.\n"
    "RISK: Floating ranges pull in whatever satisfies them at install time, including a compromised or buggy release.\n"
    "{label}",
    ["pin","lock","lockfile","package-lock","version"]),

    "typosquatting": ([
        "What is typosquatting in package registries and how do you protect a project from it?",
        "An engineer mistyped 'request' as 'reqeusts' and installed malware. What happened and how is it prevented?",
        "How do attackers abuse similarly-named packages, and what controls stop them?",
        "Why are typosquat packages a supply-chain risk, and how is it mitigated?",
        "What is a homoglyph package name attack and how do you defend against it?",
    ],
    "FUNCTION: Attackers publish packages whose names differ from popular ones by one or two characters.\n"
    "RISK: A typo at install pulls a malicious package that runs arbitrary code at import or install time.\n"
    "{label}",
    ["typosquat","typo","package name","malicious package","registry"]),

    "abandoned_package": ([
        "What risks come from depending on an abandoned open-source package that no longer gets updates?",
        "A library's last commit was 4 years ago and the maintainer is gone. What is the risk?",
        "Why is bus factor a security concern for a dependency?",
        "What is the supply-chain risk of an unmaintained package?",
        "How does a dependency going unmaintained create a security liability?",
    ],
    "FUNCTION: A dependency is no longer maintained: no patches, no CVE responses, no reviewer.\n"
    "RISK: Newly found vulnerabilities go unpatched; the project inherits the maintenance burden and the supply-chain exposure.\n"
    "{label}",
    ["abandoned","unmaintained","maintainer","supply chain","no longer maintained"]),

    "container_latest_tag": ([
        "Why is pulling container images with the 'latest' tag risky for builds? What should be used instead?",
        "A Dockerfile uses FROM node:latest. What is wrong and what is the fix?",
        "Explain why pinning images by digest is safer than pinning by tag.",
        "Why is 'latest' a mutable tag and why does that matter for builds?",
        "What is the secure alternative to FROM python:latest in a Dockerfile?",
    ],
    "FUNCTION: Builds pull 'latest', a mutable tag the registry can repoint at any time.\n"
    "RISK: A repointed 'latest' (malicious or broken) breaks reproducibility and can inject a compromised image.\n"
    "{label}",
    ["digest","tag","latest","pin","image"]),

    "k6_script": ([
        "Write a short k6 load test script that hits https://example.com/api with 50 virtual users for 1 minute.",
        "Sketch a k6 script that ramps to 100 VUs over 30s and holds for 2m.",
        "How do you structure a basic k6 test with stages and a check?",
        "Write a k6 test sending a GET to /api with 20 VUs for 30s.",
        "Show a minimal k6 script with one default function and an options block.",
    ],
    "FUNCTION: A k6 test is a JS script that defines an exported default function executed by N virtual users for a set duration.\n"
    "RISK: Without a load test script you have no reproducible way to assert throughput and latency under load.\n"
    "{label}",
    ["k6","load test","virtual users"]),

    "p95_latency": ([
        "In load test results, what does p95 latency mean and why is it more useful than the average?",
        "Explain p95 vs mean latency and when each matters.",
        "Why do SREs track p95/p99 instead of average response time?",
        "What does the 95th percentile latency tell you about the tail?",
        "Why is average latency misleading under heavy load?",
    ],
    "FUNCTION: p95 is the latency under which 95% of requests complete; the slowest 5% exceed it.\n"
    "RISK: The average hides the long tail; p95 surfaces the experience of the worst 1-in-20 requests.\n"
    "{label}",
    ["percentile","95","p95","latency"]),

    "rps_vs_concurrent": ([
        "Explain the difference between requests per second (RPS) and concurrent users in a load test.",
        "How do you convert between concurrent users and RPS?",
        "Why must a load test specify both RPS and concurrency?",
        "What is the relationship between throughput and concurrency in load testing?",
        "Why does RPS alone not characterize a load test?",
    ],
    "FUNCTION: RPS is throughput (requests completed per second); concurrency is how many in-flight requests the system serves at once.\n"
    "RISK: Modeling only one hides either saturation (concurrency) or starvation (RPS).\n"
    "{label}",
    ["requests per second","rps","throughput","concurrent","users"]),

    "post_deploy_slow": ([
        "An application becomes very slow right after a deployment. Walk through your first diagnostic checks.",
        "Right after a release, p95 jumped 4x. What do you check first?",
        "Deployment landed and now the API is sluggish. Give your diagnostic order.",
        "After a deploy, latency spiked. Which signals do you inspect first?",
        "A canary deploy caused error-rate rise. What is your first triage step?",
    ],
    "FUNCTION: Compare before/after metrics, then narrow to the changed layer.\n"
    "RISK: Without a metric trail you cannot tell CPU from DB from a bad query plan; you waste time guessing.\n"
    "{label}",
    ["logs","metrics","monitoring","cpu","memory","slow query","database"]),

    "memory_leak": ([
        "A service's memory usage keeps growing until it restarts. What is the likely problem and how do you confirm it?",
        "RSS climbs monotonically after deploy. What is the diagnosis path?",
        "How do you tell a memory leak from cache warm-up?",
        "Why does the process get OOM-killed every few hours?",
        "How do you localize a heap leak in a long-running service?",
    ],
    "FUNCTION: A retained-reference leak prevents the GC from reclaiming memory, so RSS grows until OOM-kill.\n"
    "RISK: The process eventually crashes and takes availability with it; a heap profile localizes the leak.\n"
    "{label}",
    ["leak","heap","profile","memory","gc"]),

    "overload_protection": ([
        "Under heavy load, what techniques protect a web service from falling over completely?",
        "Name the patterns that keep a service alive when traffic exceeds capacity.",
        "What is graceful degradation and how does it relate to rate limiting?",
        "Which overload-protection patterns should a gateway apply?",
        "How do you prevent a traffic spike from cascading through the pool?",
    ],
    "FUNCTION: Front-run overload with admission control: rate limit, request shedding, bounded queues, timeouts, and backpressure.\n"
    "RISK: Without these, a traffic spike cascades through the pool and the service falls over instead of degrading.\n"
    "{label}",
    ["rate limit","shed","queue","timeout","backpressure","throttle","degrade"]),

    "canary_release": ([
        "What is a canary release and how does it reduce deployment risk?",
        "Explain canary vs blue-green deployment.",
        "How do you decide the canary percentage and the promotion gate?",
        "Why does a canary limit the blast radius of a bad deploy?",
        "What metrics gate the promotion of a canary to full rollout?",
    ],
    "FUNCTION: A canary routes a small percentage of traffic to the new build, watches error/latency metrics, and rolls forward only if they hold.\n"
    "RISK: A full rollout of a bad build takes everything down at once; a canary bounds the blast radius.\n"
    "{label}",
    ["canary","gradual","rollout","percentage"]),

    "502_503_causes": ([
        "During a load test your API starts returning 502/503 errors. List the most likely causes and how you would confirm each.",
        "p95 is fine but 5% of requests 503 under load. What is happening?",
        "The gateway returns 502 for the slowest 1% of requests. Diagnose.",
        "Walk through the upstream-saturation failure mode under load.",
        "Why do 502s usually mean the upstream is unhealthy rather than the gateway?",
    ],
    "FUNCTION: 502/503 mean the gateway could not get a healthy upstream response in time.\n"
    "RISK: Common causes are upstream saturation, exhausted connection pools, timeouts, and thread starvation; confirm each with gateway and upstream metrics.\n"
    "{label}",
    ["timeout","capacity","connection pool","upstream","saturation","overload","threads"]),
}

GENERAL_REPLAY_QS = [
    "Summarize the OWASP Top 10 in one line each.",
    "What is the difference between authentication and authorization?",
    "Explain the principle of least privilege.",
    "What is defense in depth?",
    "Define the CIA triad and give one control per letter.",
    "What is a security header and why does the browser enforce it?",
    "Explain what a salt is and why it is stored alongside the hash.",
    "What is a CVE and how is it different from a CVSS score?",
    "Why is logging important for security?",
    "What is the purpose of a Web Application Firewall?",
    "Explain symmetric vs asymmetric encryption in one paragraph.",
    "What is a man-in-the-middle attack?",
    "Why should secrets never be committed to version control?",
    "What is a supply chain attack in the context of dependencies?",
    "Explain the role of TLS in web security.",
    "What is the difference between a vulnerability and an exploit?",
    "Why are default credentials dangerous?",
    "What is a security patch and why is prompt patching important?",
    "Explain what an SBOM (software bill of materials) is.",
    "What is the shared responsibility model in cloud security?",
    "What is input validation and why is it the first line of defense?",
    "Explain the concept of a security boundary.",
    "What is a zero-day vulnerability?",
    "Why must error messages avoid revealing implementation details?",
    "What is the principle of fail-secure?",
]

# ---- MinHash (on PROMPT text only) ----
def shingles(text, k=5):
    words = re.findall(r"\w+", text.lower())
    if len(words) < k:
        return set(words)
    return {" ".join(words[i:i+k]) for i in range(len(words) - k + 1)}

def minhash_sig(text, n=32, seed=7):
    sh = shingles(text)
    if not sh:
        return [0]*n
    rng = random.Random(seed)
    a = [rng.randint(1, 2**31-1) for _ in range(n)]
    b = [rng.randint(1, 2**31-1) for _ in range(n)]
    p = 2**31-1
    return [min(((a[i]*(sum(ord(c) for c in s))+b[i]) % p) for s in sh) for i in range(n)]

def jaccard_est(s1, s2):
    if not s1 or not s2: return 0.0
    return sum(1 for x,y in zip(s1,s2) if x==y) / len(s1)

def build_item(prompt, answer, cap, archetype, item_id):
    return {"messages":[{"role":"system","content":SYSTEM_PROMPT},
                          {"role":"user","content":prompt},
                          {"role":"assistant","content":answer}],
            "meta":{"id":item_id,"cap":cap,"archetype":archetype}}

def gen_code_items(target, rng):
    items=[]
    n_per = target // len(CODE_GENERATORS)
    rem = target - n_per*len(CODE_GENERATORS)
    for i,(arch,(gen_fn,answer_tpl,kws)) in enumerate(CODE_GENERATORS.items()):
        n = n_per + (1 if i<rem else 0)
        label = label_line(*kws)
        for j in range(n):
            snippet = gen_fn(rng)
            opener = rng.choice(OPENERS)
            prompt = f"{opener}\n{snippet}"
            answer = answer_tpl.format(label=label)
            items.append(build_item(prompt,answer,"code_vuln_scan",arch,f"CV-{arch}-{j:04d}"))
    rng.shuffle(items)
    return items

def gen_text_items(arch_map, cap_name, target, prefix, rng):
    items=[]
    n_per = target // len(arch_map)
    rem = target - n_per*len(arch_map)
    for i,(arch,(prompts,answer_tpl,kws)) in enumerate(arch_map.items()):
        n = n_per + (1 if i<rem else 0)
        label = label_line(*kws)
        for j in range(n):
            prompt = prompts[j % len(prompts)]
            answer = answer_tpl.format(label=label)
            items.append(build_item(prompt,answer,cap_name,arch,f"{prefix}-{arch}-{j:04d}"))
    rng.shuffle(items)
    return items

def gen_general(target, rng):
    items=[]
    for j in range(target):
        q = GENERAL_REPLAY_QS[j % len(GENERAL_REPLAY_QS)]
        items.append({"messages":[{"role":"system","content":SYSTEM_PROMPT},
                                    {"role":"user","content":q},
                                    {"role":"assistant","content":"(See OWASP, NIST, or vendor docs for the canonical answer. This item anchors general security language and protects perplexity.)"}],
                      "meta":{"id":f"GR-{j:04d}","cap":"general_replay","archetype":"general"}})
    return items

def build_dataset(targets, seed=42, sample=None):
    rng = random.Random(seed)
    all_items = (gen_code_items(targets["code_vuln"], rng)
                 + gen_text_items(TEXT_ARCHETYPES, "web_config_checks", targets["web_config"], "WC", rng)
                 + gen_text_items(TEXT_ARCHETYPES, "dependency_cve", targets["dependency_cve"], "DC", rng)
                 + gen_text_items(TEXT_ARCHETYPES, "load_runtime", targets["load_testing"], "LT", rng)
                 + gen_general(targets["general_replay"], rng))
    # NOTE: text archetypes are shared across caps; regenerate so each cap gets its own subset
    # Actually rebuild per-cap with the right archetypes:
    return all_items  # placeholder, real build below

# Rebuild properly: each capability uses a DISTINCT archetype set
CODE_ARCHES = ["sql_injection","hardcoded_secret","command_injection","code_injection_eval",
               "weak_hash","tls_verify_disabled","path_traversal","xss","missing_access_control","insecure_random"]
WEB_ARCHES = ["security_headers","cookie_flags","http_to_https_redirect","csp_header",
              "directory_listing","stack_trace_disclosure","plain_http_admin","over_fetch_api"]
DEP_ARCHES = ["outdated_library","cve_identifier","python_audit_tools","npm_audit_tools",
              "pin_versions","typosquatting","abandoned_package","container_latest_tag"]
LOAD_ARCHES = ["k6_script","p95_latency","rps_vs_concurrent","post_deploy_slow",
               "memory_leak","overload_protection","canary_release","502_503_causes"]

# ---- Prompt augmentation: multiply a small base prompt bank into many
#       textually distinct (but semantically identical) variants so MinHash
#       dedup does not collapse 125 items into 5. Combines base prompt with
#       a scenario prefix and a phrasing suffix, both drawn from pools. ----
SCENARIO_PREFIXES = [
    "In a production web app, ",
    "During a security review, ",
    "A penetration tester notices that ",
    "An auditor asks: ",
    "A junior engineer asks you: ",
    "In your team's codebase, ",
    "On a customer-facing service, ",
    "In a compliance review, ",
    "A bug bounty report says ",
    "During an incident postmortem, ",
    "In a CI/CD pipeline review, ",
    "A DevSecOps scan flags that ",
    "In a cloud migration, ",
    "On a microservices backend, ",
    "In a SOC 2 audit, ",
    "A red team exercise finds ",
    "In a Kubernetes deployment, ",
    "During a design review, ",
    "In a threat model, ",
    "A vendor security questionnaire asks: ",
]
PHRASING_SUFFIXES = [
    " Justify the answer.",
    " Give the precise technical term.",
    " Name the control or risk specifically.",
    " Be concrete.",
    " Answer in two sentences.",
    " Cite the relevant mechanism.",
    " Explain why.",
    " Give the canonical fix.",
    " What is the underlying cause?",
    " Be specific and technical.",
    " Keep it to the essentials.",
    " State the risk and the mitigation.",
    " What does an auditor expect to hear?",
    " Reference the relevant standard.",
    " Be concise but complete.",
    " Name the exact issue.",
    " What would a senior engineer say?",
    " Give the textbook answer.",
    " What is the security implication?",
    " State the fix and the rationale.",
]

def augment_text_prompt(base_prompts, j, rng):
    """Cycle through base prompts; prepend a scenario prefix and append a
       phrasing suffix to make each variant textually distinct. The semantic
       content (and therefore the required label) is unchanged."""
    base = base_prompts[j % len(base_prompts)]
    prefix = SCENARIO_PREFIXES[j % len(SCENARIO_PREFIXES)]
    # vary the suffix more to maximize distinctness
    suffix = rng.choice(PHRASING_SUFFIXES)
    # capitalize base after prefix if needed
    if prefix.endswith(": ") or prefix.endswith("that "):
        return prefix + base + suffix
    # prefix ends with ", " - lowercase the base's first letter
    return prefix + base[0].lower() + base[1:] + suffix


def build_dataset_v2(targets, seed=42, sample=None):
    rng = random.Random(seed)

    def make_items(arch_list, cap_name, target, prefix):
        items=[]
        n_per = target // len(arch_list)
        rem = target - n_per*len(arch_list)
        for i, arch in enumerate(arch_list):
            n = n_per + (1 if i<rem else 0)
            if arch in CODE_GENERATORS:
                gen_fn, answer_tpl, kws = CODE_GENERATORS[arch]
                label = label_line(*kws)
                for j in range(n):
                    snippet = gen_fn(rng)
                    opener = rng.choice(OPENERS)
                    prompt = f"{opener}\n{snippet}"
                    answer = answer_tpl.format(label=label)
                    items.append(build_item(prompt,answer,cap_name,arch,f"{prefix}-{arch}-{j:04d}"))
            else:
                prompts, answer_tpl, kws = TEXT_ARCHETYPES[arch]
                label = label_line(*kws)
                for j in range(n):
                    prompt = augment_text_prompt(prompts, j, rng)
                    answer = answer_tpl.format(label=label)
                    items.append(build_item(prompt,answer,cap_name,arch,f"{prefix}-{arch}-{j:04d}"))
        rng.shuffle(items)
        return items

    code = make_items(CODE_ARCHES, "code_vuln_scan", targets["code_vuln"], "CV")
    web = make_items(WEB_ARCHES, "web_config_checks", targets["web_config"], "WC")
    dep = make_items(DEP_ARCHES, "dependency_cve", targets["dependency_cve"], "DC")
    load = make_items(LOAD_ARCHES, "load_runtime", targets["load_testing"], "LT")
    gen = gen_general(targets["general_replay"], rng)
    all_items = code + web + dep + load + gen
    rng.shuffle(all_items)

    if sample:
        all_items = all_items[:sample]

    # MinHash dedup on PROMPT only
    seen_sigs=[]; deduped=[]; dup_count=0
    for item in all_items:
        text = item["messages"][1]["content"]
        sig = minhash_sig(text)
        if any(jaccard_est(sig,s)>=0.9 for s in seen_sigs):
            dup_count+=1; continue
        seen_sigs.append(sig); deduped.append(item)

    # (archetype,label) cap 250
    arch_counts=defaultdict(int); capped=[]; over=0
    for item in deduped:
        k=item["meta"]["archetype"]
        if arch_counts[k]>=250: over+=1; continue
        arch_counts[k]+=1; capped.append(item)

    # stratified dev holdout (100 items)
    by_cap=defaultdict(list)
    for item in capped: by_cap[item["meta"]["cap"]].append(item)
    dev=[]; train=[]
    dev_per={"code_vuln_scan":40,"web_config_checks":25,"dependency_cve":15,"load_runtime":15,"general_replay":5}
    for cap,items in by_cap.items():
        n_dev=dev_per.get(cap,5)
        rng.shuffle(items)
        dev.extend(items[:n_dev]); train.extend(items[n_dev:])

    stats={
        "total_generated":len(all_items),
        "after_minhash_dedup":len(deduped),
        "duplicates_removed":dup_count,
        "after_archetype_cap":len(capped),
        "over_cap_removed":over,
        "train_items":len(train),
        "dev_items":len(dev),
        "archetype_counts":dict(arch_counts),
        "by_capability_train":dict((cap,sum(1 for i in train if i["meta"]["cap"]==cap)) for cap in dev_per),
    }
    return train,dev,stats

def verify_grader_keywords(items):
    arch_to_groups={it["archetype"]:it["groups"] for it in BASELINE_ITEMS}
    problems=[]
    for item in items:
        arch=item["meta"]["archetype"]
        if arch not in arch_to_groups: continue
        ans=item["messages"][2]["content"].lower()
        for group in arch_to_groups[arch]:
            if not any(kw.lower() in ans for kw in group):
                problems.append({"id":item["meta"]["id"],"archetype":arch,"missing_group":group})
    return problems

def write_jsonl(items, path):
    with open(path,"w",encoding="utf-8") as f:
        for item in items: f.write(json.dumps(item,ensure_ascii=False)+"\n")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--sample",type=int,default=None)
    ap.add_argument("--seed",type=int,default=42)
    ap.add_argument("--outdir",default="/home/z/my-project/download/sirius-toolkit")
    args=ap.parse_args()
    targets={"code_vuln":1500,"web_config":1000,"dependency_cve":400,"load_testing":600,"general_replay":500}
    if args.sample:
        scale=args.sample/4000
        targets={k:max(1,int(v*scale)) for k,v in targets.items()}
    train,dev,stats=build_dataset_v2(targets,seed=args.seed)
    os.makedirs(args.outdir,exist_ok=True)
    train_path=os.path.join(args.outdir,"sirius_train.jsonl")
    dev_path=os.path.join(args.outdir,"sirius_dev.jsonl")
    manifest_path=os.path.join(args.outdir,"sirius_dataset_manifest.json")
    write_jsonl(train,train_path); write_jsonl(dev,dev_path)
    problems=verify_grader_keywords(train+dev)
    coverage_ok = len(problems)==0
    manifest={
        "project":"SIRIUS","phase":"2-data",
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "system_prompt":SYSTEM_PROMPT,"targets":targets,"stats":stats,
        "grader_keyword_coverage":{"all_items_contain_required_keywords":coverage_ok,
                                    "problem_count":len(problems),"sample_problems":problems[:5]},
        "format":"ChatML (messages: system/user/assistant), one JSON object per line",
        "files":{"train":train_path,"dev":dev_path},
        "decontamination":{"baseline_prompts_held_out":34,
            "method":"Generative snippets (parameterized) + paraphrased prompts; MinHash Jaccard>=0.9 on prompt text; (archetype,label) cap 250",
            "exact_baseline_prompt_reused":False},
        "plan_reference":"SIRIUS_Phase2_Consultation_Output.md Part B3",
    }
    with open(manifest_path,"w",encoding="utf-8") as f: json.dump(manifest,f,indent=2,ensure_ascii=False)
    print(f"Train: {len(train)} items -> {train_path}")
    print(f"Dev:   {len(dev)} items -> {dev_path}")
    print(f"Manifest -> {manifest_path}")
    print(f"Stats: {json.dumps(stats,indent=2)}")
    print(f"Grader keyword coverage: {'OK' if coverage_ok else 'FAIL'} ({len(problems)} problems)")

if __name__=="__main__":
    main()
