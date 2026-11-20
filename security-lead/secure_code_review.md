# Playbook — Security-Focused Diff Review (develop stage)

## 1. Orientation

Review PR *diffs* (not whole files): the regression risk is what the change
introduces. Inputs: diff/patch, linked design (if any). Output: review
comments in finding format, each tied to a diff line, or explicit approval.
Run `sirius_cli.py gate` first — hand-review what the scanner cannot see.

## 2. Check inventory

1. **New sink reached by old input**: does the diff add a query/shell/file/
   HTML sink whose input predates the change? New sink + old input = new
   injection.
2. **New trust boundary**: does the change accept input from a new source
   (new public endpoint, new message topic, new third-party webhook)?
   Webhooks especially: verify signature validation ships with the handler.
3. **Authz deltas**: routes added/removed from auth middleware; role checks
   broadened (`is_admin` → `staff`); ownership checks dropped in a
   refactor.
4. **Crypto deltas**: new hashing (must be bcrypt/argon2 for passwords),
   new token generation (must be `secrets`/crypto-random), any change to
   TLS verification flags.
5. **Dependency deltas**: new dependency (pin exact version; check the
   name letter-by-letter for typosquats; look for known CVEs before
   approving), version downgrades, lockfile edits that don't match the
   manifest.
6. **Config deltas**: debug flags in prod configs, cookie flag changes,
   header removals, `0.0.0.0` binds on admin services, port 80 additions.
7. **Error/log deltas**: new exception paths that leak internals to
   clients; new log lines carrying credential material.
8. **State/concurrency deltas**: new shared mutable state, check-then-act
   sequences, new counters without locks (race_condition class).
9. **Test delta honesty**: security-relevant change with no test? Note it;
   a mitigation without a regression test decays silently.
10. **Approve with restraint**: if the diff introduces no new sink,
    boundary, credential, or authz change — say "approved, no security
    concerns". Do not manufacture findings.

## 3. Evidence & severity anchors

- Critical: public unauthenticated endpoint with a write sink; credential
  added to source.
- High: authz loosening; dependency with known RCE CVE; disabled signature
  verification.
- Medium/low: missing tests, log hygiene, config hardening gaps.

## 4. Common wrong answers

- Re-litigating old code outside the diff — that's the auditor's scan job.
- Style comments dressed as security findings; label hygiene separately.
- Blocking on "risk acceptance" items that belong to the threat model, not
  the diff.

## 5. Syntax Anchors (exact patterns for a small model)

- **New sinks**: `os.system`, `subprocess`, `eval`, `exec`, `cursor.execute`,
  `render_template_string`. Any new occurrence needs justification.
- **Crypto deltas**: `md5`, `sha1`, `random.randint` (must be `secrets`),
  `verify=False` in requests.
- **Object-level authz**: ORM lookups using a route/path parameter directly
  (`User.query.get(id)`, `db.users.get(id)`) must be scoped to `current_user`
  or an explicit role check. Unscoped = BOLA/IDOR.
- **Mass assignment**: `**kwargs`, `request.json`, or `.update()` passed straight
  into a model constructor without a DTO/schema allowlist.

## 6. Golden Example (few-shot anchor)

Input Diff:
```
+ @app.route('/api/users/<id>')
+ def get_user(id):
+     return User.query.get(id).to_dict()
```

**Verdict**: HIGH — BOLA on user read.
**Attack Path**: Authenticated user can enumerate and read PII of any user by
iterating IDs.
**Risks**:
- Object-level authorization missing; query is not scoped to `current_user`.
- `to_dict()` may leak sensitive fields if not explicitly allowlisted.
**First Action**: Scope query to `current_user.users.get(id)` or add an explicit
role check; use an output schema instead of raw `to_dict()`.
