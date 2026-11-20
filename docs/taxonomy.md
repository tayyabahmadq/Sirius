# SIRIUS Vulnerability Taxonomy — Canonical Labels & Evidence

This is the single source of truth for class names, the exact LABEL phrases
the auditor emits, and the evidence keywords each phrase must contain (aligned
with `04_sirius_baseline.py` grader groups).

## Canonical answer contract

- The **first line** of every answer is `LABEL: <canonical_label>` — or
  `LABEL: no vulnerability found` for safe code.
- Evidence keywords live **in the LABEL line itself** wherever possible, so the
  class survives truncation.
- Never append speculative classes. One snippet, one class (or "no
  vulnerability found").

## code_vuln_scan

| Archetype | Canonical LABEL (must contain ↓) | Evidence keywords (grader-aligned) |
|---|---|---|
| `sql_injection` | `sql injection — unparameterized query built by string concatenation` | sql injection; concatenation / f-string / format |
| `hardcoded_secret` | `hardcoded secret — embedded credential in source code` | hardcoded; secret in source / embedded credential |
| `command_injection` | `command injection — user input reaches a shell with shell=True/os.system` | command injection; os.system / shell=True / subprocess |
| `code_injection_eval` | `arbitrary code execution — eval/exec on user-controlled input` | eval; arbitrary code; code execution |
| `weak_hash` | `weak unsalted password hash (md5/sha1) — fix with bcrypt or argon2 salted hashing` | md5/sha1/weak hash/unsalted **and** bcrypt/argon2/scrypt/salt |
| `tls_verify_disabled` | `tls verification disabled (verify=False) — man-in-the-middle risk` | verify=False; tls/ssl; mitm / man-in-the-middle |
| `path_traversal` | `path traversal — user-controlled path joined without sanitization` | path traversal; ../ / sanitize / basename |
| `xss` | `cross-site scripting (xss) — unescaped user data written into html` | xss; innerHTML / escape / sanitiz |
| `missing_access_control` | `missing access control — authenticated/authorized check absent on sensitive route` | auth*; access control; unauthorized / session |
| `insecure_random` | `insecure predictable random for security token — use crypto-grade secrets/os.urandom` | random/predictable/insecure **and** secrets/os.urandom/crypto |

## web_config_checks

| Archetype | Canonical LABEL |
|---|---|
| `security_headers` | missing security headers (strict-transport-security/hsts, content-security-policy/csp, x-frame-options, x-content-type-options) |
| `cookie_flags` | cookie missing secure/httponly/samesite flags — csrf exposure |
| `plain_http_admin` | admin panel served over plain http — credentials in cleartext |
| `directory_listing` | directory listing enabled — source/data disclosure |
| `stack_trace_disclosure` | debug/stack traces exposed in production — info disclosure |
| `http_to_https_redirect` | no http→https redirect — cleartext downgrade |
| `csp_header` | missing/unsafe content-security-policy — xss amplifier |
| `over_fetch_api` | api over-fetches fields — pii/sensitive data leakage |

## dependency_cve

| Archetype | Canonical LABEL |
|---|---|
| `outdated_library` | outdated dependency with known cve — upgrade & pin |
| `typosquatting` | typosquatted package name in manifest |
| `container_latest_tag` | container image uses latest tag — non-reproducible, supply-chain risk |
| `pin_versions` | unpinned dependency versions — nondeterministic supply chain |
| `audit_tools` | no dependency audit tooling in ci — cves reach production unnoticed |

## load_runtime

| Archetype | Canonical LABEL |
|---|---|
| `k6_script` | load-test spec (k6) with thresholds (p95) and checks |
| `memory_leak` | unbounded growth per request — memory leak |
| `overload_protection` | no timeout/rate-limit/backpressure — collapse under load |

## Safe-code contract (hard negatives)

A safe item is emitted only when the snippet **actually mitigates** the class:
parameterized query, list-argument subprocess without shell, `ast.literal_eval`,
`bcrypt`/`argon2` + per-user salt, default `verify=True` or explicit CA bundle,
`secrets.token_hex`/`os.urandom`, env/secret-manager credentials, auth decorator
present, `secure_filename`/`send_from_directory`, escaped output. The LABEL is
always `no vulnerability found` followed by the mitigation reason — never a
vulnerability class. Restraint is a trained capability: the auditor must be able
to say "clean" on code that merely *looks* security-themed.
