# Raw output dump — sirius-pass5

Budgets: [240, 64] · verdict histogram: PASS=29, OTHER=5

## V01 (code_vuln_scan, min_pass=1)
- **np=240** → OTHER (0/2, eval_count=31)
  ```
  LABEL: no vulnerability found
  FUNCTION: The SQL query is valid and executes against a secure database.
  RISK: none — the format is correct.
  ```
- **np=64** → PASS (1/2, eval_count=37)
  ```
  LABEL: no vulnerability found — SQL injection is impossible.
  FUNCTION: The query string is sanitized in the database call.
  RISK: none — the user's credentials are never exposed.
  ```

## V02 (code_vuln_scan, min_pass=1)
- **np=240** → PASS (1/1, eval_count=48)
  ```
  LABEL: hardcoded, secret in source
  FUNCTION: A live credential is embedded directly into source code.
  RISK: Anyone with repository or image access obtains the credential; it cannot be rotated without a redeploy and persists in version history.
  ```
- **np=64** → PASS (1/1, eval_count=48)
  ```
  LABEL: hardcoded, secret in source
  FUNCTION: A live credential is embedded directly into source code.
  RISK: Anyone with repository or image access obtains the credential; it cannot be rotated without a redeploy and persists in version history.
  ```

## V03 (code_vuln_scan, min_pass=1)
- **np=240** → PASS (1/1, eval_count=37)
  ```
  LABEL: command injection, os.system
  FUNCTION: Untrusted input is passed to a built-in shell command.
  RISK: Priviledged processes run arbitrary commands on your system.
  ```
- **np=64** → PASS (1/1, eval_count=42)
  ```
  LABEL: no vulnerability found — shell command is valid and executable.
  FUNCTION: python script that runs a system command via os.system() in a secure way.
  RISK: none — the pattern is correct.
  ```

## V04 (code_vuln_scan, min_pass=1)
- **np=240** → PASS (1/1, eval_count=54)
  ```
  LABEL: arbitrary code execution — external script in the user's expression
  FUNCTION: A custom function that evaluates a string into a value that can be executed by the process.
  RISK: The attacker injects arbitrary shell, which the victim process executes with full privileges.
  ```
- **np=64** → OTHER (0/1, eval_count=43)
  ```
  LABEL: sql injection, string interpolation
  FUNCTION: Untrusted input is interpolated into a SQL query string.
  RISK: Arbitrary SQL is executed on the database server; no SQL pattern is revealed to anyone else.
  ```

## V05 (code_vuln_scan, min_pass=2)
- **np=240** → PASS (2/2, eval_count=61)
  ```
  LABEL: md5, weak hash, unsalted, bcrypt, salt
  FUNCTION: Passwords are hashed with MD5/SHA1 without a per-user random salt.
  RISK: MD5/SHA1 are broken and far too fast; rainbow tables and GPU brute force recover passwords in seconds.
  ```
- **np=64** → PASS (2/2, eval_count=61)
  ```
  LABEL: md5, weak hash, unsalted, bcrypt, salt
  FUNCTION: Passwords are hashed with MD5/SHA1 without a per-user random salt.
  RISK: MD5/SHA1 are broken and far too fast; rainbow tables and GPU brute force recover passwords in seconds.
  ```

## V06 (code_vuln_scan, min_pass=1)
- **np=240** → PASS (1/1, eval_count=48)
  ```
  LABEL: verify=False, tls, man-in-the-middle
  FUNCTION: The client disables certificate verification on the TLS connection.
  RISK: The server identity is no longer authenticated; a network attacker can impersonate the endpoint (MITM).
  ```
- **np=64** → PASS (1/1, eval_count=48)
  ```
  LABEL: verify=False, tls, man-in-the-middle
  FUNCTION: The client disables certificate verification on the TLS connection.
  RISK: The server identity is no longer authenticated; a network attacker can impersonate the endpoint (MITM).
  ```

## V07 (code_vuln_scan, min_pass=1)
- **np=240** → PASS (1/1, eval_count=42)
  ```
  LABEL: path traversal, directory
  FUNCTION: User input is concatenated into a filesystem path with no normalization or allow-list.
  RISK: ../ sequences escape the intended directory, letting the attacker read arbitrary files.
  ```
- **np=64** → PASS (1/1, eval_count=42)
  ```
  LABEL: path traversal, directory
  FUNCTION: User input is concatenated into a filesystem path with no normalization or allow-list.
  RISK: ../ sequences escape the intended directory, letting the attacker read arbitrary files.
  ```

## V08 (code_vuln_scan, min_pass=1)
- **np=240** → PASS (1/1, eval_count=51)
  ```
  LABEL: xss, cross-site scripting, innerHTML
  FUNCTION: Untrusted content is inserted into the DOM without escaping.
  RISK: The attacker injects script that runs in the victim's browser, stealing cookies or performing actions as the user.
  ```
- **np=64** → PASS (1/1, eval_count=51)
  ```
  LABEL: xss, cross-site scripting, innerHTML
  FUNCTION: Untrusted content is inserted into the DOM without escaping.
  RISK: The attacker injects script that runs in the victim's browser, stealing cookies or performing actions as the user.
  ```

## V09 (code_vuln_scan, min_pass=1)
- **np=240** → OTHER (0/1, eval_count=15)
  ```
  LABEL: no vulnerability found — regex pattern matches expected route path correctly.
  ```
- **np=64** → WRONG_LABEL(xss) (0/1, eval_count=46)
  ```
  LABEL: xss, cross-site scripting, inner-hashing
  FUNCTION: Untrusted content is rendered directly into HTML.
  RISK: Attackers can inject arbitrary content, including JavaScript, script, style, and even PHP.
  ```

## V10 (code_vuln_scan, min_pass=2)
- **np=240** → PASS (2/2, eval_count=54)
  ```
  LABEL: random, predictable, os.urandom, secure random
  FUNCTION: A session token is generated from a predictable source (random).
  RISK: Random tokens are easy targets for eavesdropping or replay; they can be guessed by anyone who sees them.
  ```
- **np=64** → PASS (1/2, eval_count=50)
  ```
  LABEL: no vulnerability found — 404 random token generation.
  FUNCTION: A simple string conversion from a random integer to a human-readable string.
  RISK: No input is exposed; the user gets a predictable output (a random token).
  ```

## W01 (web_config_checks, min_pass=2)
- **np=240** → PASS (4/4, eval_count=63)
  ```
  LABEL: strict-transport-security, content-security-policy, x-frame-options, x-content-type-options
  FUNCTION: Production responses omit the standard security response headers.
  RISK: Without them the browser allows mixed content, framing, MIME sniffing, and lacks a CSP, expanding the XSS and clickjacking surface.
  ```
- **np=64** → PASS (4/4, eval_count=63)
  ```
  LABEL: strict-transport-security, content-security-policy, x-frame-options, x-content-type-options
  FUNCTION: Production responses omit the standard security response headers.
  RISK: Without them the browser allows mixed content, framing, MIME sniffing, and lacks a CSP, expanding the XSS and clickjacking surface.
  ```

## W02 (web_config_checks, min_pass=2)
- **np=240** → PASS (3/3, eval_count=62)
  ```
  LABEL: httponly, secure, samesite
  FUNCTION: The session cookie is set without HttpOnly, Secure, and SameSite.
  RISK: JavaScript can read it (XSS theft), it crosses plain HTTP (sniff), and it is sent on cross-site requests (CSRF).
  ```
- **np=64** → PASS (3/3, eval_count=62)
  ```
  LABEL: httponly, samesite, secure,httpparams
  FUNCTION: Session cookies are set without HttpOnly, SameSite, or Secure.
  RISK: JavaScript can read them (XSS theft), with cookies set without HttpOnly/SameSite/Secure (PHPPaw).
  ```

## W03 (web_config_checks, min_pass=1)
- **np=240** → PASS (1/1, eval_count=48)
  ```
  LABEL: https, certificate, key, transmit
  FUNCTION: The server generates its own certificate without a private key.
  RISK: The server can be traced and spoofed; the key is lost when the server leaves security purview.
  ```
- **np=64** → PASS (1/1, eval_count=64)
  ```
  LABEL: https, certificate, fingerprint, authority
  FUNCTION: A insecure SSL cert is embedded in a relic (Apache, MySQL, PostgreSQL) without a valid SHA-1/SHA-256 fingerprint.
  RISK: The worst-case attack is a blind recapture by an attacker with a cert of the same or
  ```

## W04 (web_config_checks, min_pass=1)
- **np=240** → PASS (3/3, eval_count=47)
  ```
  LABEL: content-security-policy, script, xss
  FUNCTION: No Content-Security-Policy is set, or it allows unsafe-inline scripts.
  RISK: Injected script has no source restriction, so XSS is unconstrained.
  ```
- **np=64** → PASS (3/3, eval_count=47)
  ```
  LABEL: content-security-policy, script, xss
  FUNCTION: No Content-Security-Policy is set, or it allows unsafe-inline scripts.
  RISK: Injected script has no source restriction, so XSS is unconstrained.
  ```

## W05 (web_config_checks, min_pass=1)
- **np=240** → PASS (1/1, eval_count=88)
  ```
  LABEL: directory listing, file exposure, enumeration
  FUNCTION: The site目录包含扩展名为.html、.php、.js和.css的文件，当访客访问时通过浏览器直接嵌入。
  RISK: 拖库和枚举：http://www.example.com/example/abc.js?b=123&f=456; 是从 example 目录加载的 JavaScript 文件。
  ```
- **np=64** → PASS (1/1, eval_count=53)
  ```
  LABEL: directory listing, file exposure, enumeration
  FUNCTION: The site enumerates four-fourths of all files and directories.
  RISK: Traverser behavior (path traversal) extends to the entire file system; any point in the file path is accessible.
  ```

## W06 (web_config_checks, min_pass=1)
- **np=240** → PASS (1/1, eval_count=63)
  ```
  LABEL: sensitive, overprotection, leak, hash, encryption
  FUNCTION: The application stores a complete view of every request with SHA-1 hashes.
  RISK: A attacker can generate hashes for any request, even those of legitimate users; a dump allows破解(attack) and assumes the right profile.
  ```
- **np=64** → PASS (1/1, eval_count=64)
  ```
  LABEL: sensitive, overprotection, leak, hash, encryption
  FUNCTION: The application stores a full SHA-1 or -256 hash of each file in the database.
  RISK: An attacker can delete or modify the file, or hash, at any time; a lookup by the hash requires the full
  ```

## W07 (web_config_checks, min_pass=1)
- **np=240** → PASS (1/1, eval_count=51)
  ```
  LABEL: https, tls, plaintext, sniff, credentials
  FUNCTION: Administrative traffic travels over unencrypted HTTP.
  RISK: Credentials and session cookies traverse the network in plaintext; anyone on the path can sniff or modify them, even on a LAN.
  ```
- **np=64** → PASS (1/1, eval_count=54)
  ```
  LABEL: https, tls, plaintext, sniff, credentials
  FUNCTION: Network traffic is produced over HTTP without a secure transport layer.
  RISK: Credentials and sensitive data pass unencrypted from client to server; sniffers can monitor them at the application or server level.
  ```

## W08 (web_config_checks, min_pass=1)
- **np=240** → PASS (1/1, eval_count=51)
  ```
  LABEL: sensitive, over-fetch, hash, field, exposure
  FUNCTION: The API exposes all fields; a custom validator filters accessible ones.
  RISK: Password hashes, internal IDs, and UUIDs are exposed to anyone who can call the endpoint.
  ```
- **np=64** → PASS (1/1, eval_count=54)
  ```
  LABEL: sensitive, over-fetch, hash, field, exposure
  FUNCTION: The API exposes a full field structure, including password hashes.
  RISK: Password hashes are exposed as part of the API response, even when anonymous; attackers can decrypt them and steal credentials.
  ```

## D01 (dependency_cve, min_pass=1)
- **np=240** → PASS (1/1, eval_count=56)
  ```
  LABEL: outdated, pinned, dependency, lockfile, version
  FUNCTION: The latest is pinned to one that has been removed or their build tools cannot parse it.
  RISK: The attacker can drop a payload with a compatible version; otherwise, the package gets upgraded automatically.
  ```
- **np=64** → PASS (1/1, eval_count=57)
  ```
  LABEL: outdated, pinned, dependency, lockfile, version
  FUNCTION: The latest is pinned to a release that has been broken or unstable.
  RISK: Someone can install it themselves (outdated) or find a vulnerable version (pinned) and install it as well.
  ```

## D02 (dependency_cve, min_pass=1)
- **np=240** → PASS (1/1, eval_count=60)
  ```
  LABEL: common vulnerabilities, cve, identifier, open source
  FUNCTION: A CVE is a unique, publicly disclosed security issue fixed by a publicly available patch.
  RISK: Without them MITMability, lifecycle, and open-source issues bind the problem to one vendor and prevent fast fix deployment.
  ```
- **np=64** → PASS (1/1, eval_count=64)
  ```
  LABEL: common vulnerabilities, cve, open source, advisory, fix
  FUNCTION: A CVE (Common Vulnerability Scoring System) is a predefined list of vulnerabilities associated with a product.
  RISK: The vast majority of security issues are CVE-identifiable; without them the risk is minimal. Identification is Open Source
  ```

## D03 (dependency_cve, min_pass=1)
- **np=240** → OTHER (0/1, eval_count=57)
  ```
  LABEL: pypandoc, pygments, black, flake8, docs
  FUNCTION: The project is committed to Git with a PEP 8-compliant style.
  RISK: No style is enforced; the formatter runs at commit time and has no linting.
  ```
- **np=64** → OTHER (0/1, eval_count=55)
  ```
  LABEL: pypandoc, pyproject.lock, codecov, coverage
  FUNCTION: The project is published with a PEP8 compliant PyProject file.
  RISK: No linting or release coverage, so the build and distribution are vulnerable to errors and duplicates.
  ```

## D04 (dependency_cve, min_pass=1)
- **np=240** → PASS (1/1, eval_count=53)
  ```
  LABEL: npm audit, pnpm audit, yargs audit
  FUNCTION: A package manager silently ignores known vulnerabilities in its dependency graph.
  RISK: Unpatched providers are inadvertently included without inspection; the default NPM does nothing and PNP audits fail.
  ```
- **np=64** → PASS (1/1, eval_count=46)
  ```
  LABEL: npm audit, pnpm audit, lerna audit
  FUNCTION: A list of known vulnerabilities is provided by npm audits.
  KILLER: No one else checks; the audit grows with no commit or release history.
  ```

## D05 (dependency_cve, min_pass=1)
- **np=240** → PASS (1/1, eval_count=46)
  ```
  LABEL: lockfile, version, pin, install, registry
  FUNCTION: A pinned version is passed to npm via a package-lock.json.
  RISK: Without it the registry pulls unversioned packages, which break dependencies.
  ```
- **np=64** → PASS (1/1, eval_count=46)
  ```
  LABEL: lock, version, pin, install, registry
  FUNCTION: Dependencies are pinned to specific releases via npm registries.
  RISK: Vulnerable versions wind up in any registry, where malware finds them and exploits them.
  ```

## D06 (dependency_cve, min_pass=1)
- **np=240** → PASS (1/1, eval_count=52)
  ```
  LABEL: typosquat, registry, unique identifier, package version
  FUNCTION: Namespacing prevents typosquat by replacing every occurrence with a unique identifier.
  RISK: Typosquat hits the registry at runtime; namespace resolution shields against that attack.
  ```
- **np=64** → PASS (1/1, eval_count=54)
  ```
  LABEL: typosquat, name, registry, domain
  FUNCTION: Schema vulnerabilities allow attacks like "500 server error" to propagate to arbitrary domains.
  RISK: Users recognize no pattern and fall on poisoned servers; the poisoning propagates to all domains.
  ```

## D07 (dependency_cve, min_pass=1)
- **np=240** → OTHER (0/1, eval_count=77)
  ```
  LABEL: closed source, proprietary, proprietary dependencies, locked code, out of warranty
  FUNCTION: Codebases are vulnerable to exploitation if they remain open source.
  RISK: Open source means the code is (1) freely redistributable; (2) subject to patches and support that end with a recall; and (3) licensed under an unlicensed license that has no warranty.
  ```
- **np=64** → OTHER (0/1, eval_count=59)
  ```
  LABEL: closed source, proprietary, proprietary dependencies, locked down, invasive
  FUNCTION: The project is released under an open source license but the source code is kept in a binary repository.
  RISK: A version control breach or new contributor can restore the original, licensed code at any time.
  ```

## D08 (dependency_cve, min_pass=1)
- **np=240** → PASS (1/1, eval_count=54)
  ```
  LABEL: latest, pin, official, branch
  FUNCTION: Production images are outaged by the latest stable.
  RISK: The same issues get fixed in the next release; the latest has the feature set and dependency stability committed by someone other than the security team.
  ```
- **np=64** → PASS (1/1, eval_count=64)
  ```
  LABEL: latest, pinned, official, dependency, lockfile
  FUNCTION: The latest is the earliest that will run on any host; the pinned is a specific version that the build system can install.
  RISK: A pinned version disappears if the official fails to build with it; theeload lets you specify a lockfile
  ```

## L01 (load_runtime, min_pass=1)
- **np=240** → PASS (1/2, eval_count=71)
  ```
  LABEL: k6, users, concurrency, random
  FUNCTION: A simple k6 load test script sets up 50 users and sends them through the endpoint at 500-600 requests per second.
  RISK: The regular user model is poisoned by synthetic traffic; with a k6 you distinguish between real and synthetic users.
  ```
- **np=64** → PASS (2/2, eval_count=64)
  ```
  LABEL: k6, users, concurrency, benchmarks
  FUNCTION: A simple K6 job that sets up 50 users and runs 1000 requests in parallel.
  RISK: The default is 100 concurrent requests per user; this saturates the server. A job with k6 sets a
  ```

## L02 (load_runtime, min_pass=1)
- **np=240** → PASS (1/1, eval_count=95)
  ```
  LABEL: p95, latencies, stddev, percentile
  FUNCTION: p95 is the longest latency interval under 95%, or standard deviation of the latency profile; a slowest 95% is a thief.
  RISK: The slowest 95% matters because (1) a single bad point takes on average 24. 7% new load, and (2) 95% hides pinching at the bottom.
  ```
- **np=64** → PASS (1/1, eval_count=64)
  ```
  LABEL: p95, 95th percentile, minimum, max, median
  FUNCTION: P95 is the error rate at which 95% of the workload is processed; the lowest that spans the whole dataset.
  RISK: Without it you have no information about the average or maximum; they both
  ```

## L03 (load_runtime, min_pass=1)
- **np=240** → PASS (2/2, eval_count=62)
  ```
  LABEL: throughput, throughput, users, users/min, percent
  FUNCTION: For a given URL or endpoint, the throughput is the number of requests processed per second.
  RISK: If you don’t know throughput, you can’t measure latency or estimate your capacity; fixed-rate loads are transparent and predictable.
  ```
- **np=64** → PASS (2/2, eval_count=55)
  ```
  LABEL: requests per second, rps, throughput, users per second, us
  FUNCTION: RPS is throughput (requests completed per second); US is users per second by how many.
  RISK: Misusing US exposes a hidden rate (poisoned metric).
  ```

## L04 (load_runtime, min_pass=2)
- **np=240** → PASS (1/1, eval_count=64)
  ```
  LABEL: logs, monitoring, cpu, memory, charts
  FUNCTION: Compare before/after metrics from yesterday to this week in a monitoring alerting system.
  RISK: Without this insight you have no way to compare now/next without breaking something; the wrong metric (CPU or RAM) and timeframe are arbitrary.
  ```
- **np=64** → PASS (1/1, eval_count=56)
  ```
  LABEL: logs, monitoring, cpu, memory, plot, trends
  FUNCTION: Compare now and then with a baseline plot to see what changes.
  RISK: Without a timeline you don’t know the context or scale of what’s changed, so you can miss major improvements.
  ```

## L05 (load_runtime, min_pass=1)
- **np=240** → PASS (1/1, eval_count=66)
  ```
  LABEL: heap, memory, overflow, leak, allocation
  FUNCTION: A pool of dynamically allocated memory is not managed by a GC; instead, it expands at runtime and shrinks as needed.
  RISK: When no garbage collector can work, the pool runs out of allocations (GC misses), consuming them (leaks).
  ```
- **np=64** → PASS (1/1, eval_count=59)
  ```
  LABEL: heap, memory, overflow, leak, allocation
  FUNCTION: A malloc or new on an unused stack results in garbage vtable entries stored on the heap.
  RISK: Unallocated vtable slots tie up registers and consume CPU; without bounds checking the overhead grows long function calls.
  ```

## L06 (load_runtime, min_pass=1)
- **np=240** → OTHER (0/1, eval_count=53)
  ```
  LABEL: heartbeat, monitor, retry, time limit, backlog
  FUNCTION: A heartbeat sends periodic requests to the server; if missing, the replica retries indefinitely.
  RISK: The server goes down when the connection is lost but the replica can keep working forever.
  ```
- **np=64** → OTHER (0/1, eval_count=52)
  ```
  LABEL: heartbeat, monitoring, cpu, memory, health check, ceilometer, Prometheus
  FUNCTION: Health checks are CPU/IO-heavy labor; metrics monitor them and warn.
  RISK: Without them the sink grows exponentially; monitoring finds it at scale.
  ```

## L07 (load_runtime, min_pass=1)
- **np=240** → PASS (1/1, eval_count=64)
  ```
  LABEL: canary, cycle, degradation, timeline
  FUNCTION: A canary is a quick, experimental release followed by monitoring and scaling only on performance.
  RISK: A cycle of regressions: old code gets tested, then degraded into the next iteration. The canary marks the new, fully tested version.
  ```
- **np=64** → PASS (1/1, eval_count=64)
  ```
  LABEL: canary, rollback, degradation
  FUNCTION: A canary routes a small fraction of production traffic to a staging environment for testing before deploying.
  RISK: Invariant degradation: The staging branch gets a broken version of the code; the rollback path is a clean clone. The canary also isolates the risk
  ```

## L08 (load_runtime, min_pass=1)
- **np=240** → PASS (1/1, eval_count=64)
  ```
  LABEL: connection, overload, resource, pool, channel, overload, excess, queue
  FUNCTION: Exploits mutual exclusion (overlapping reads) in Python's built-in HTTP client or aiohttp pool.
  RISK: Many clients share a single connection; a burst of requests blocks all but the fastest client.
  ```
- **np=64** → PASS (1/1, eval_count=64)
  ```
  LABEL: connection, overload, capacity, resources, async
  FUNCTION: The application exhausts its connections (threads, workers) to the server before creating enough CPU or resource context threads.
  RISK: Fast exhaustion leads to performance degradation (502/503) and to under-allocated resources (nodes,
  ```
