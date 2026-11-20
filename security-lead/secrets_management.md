# Playbook — Secrets Lifecycle Management (cross-cutting)

## 1. Orientation

Covers generation, storage, distribution, rotation, and leakage response
for every credential type: passwords, API keys, tokens, signing keys,
certificates. The lead's job is the *lifecycle* — most secret incidents
are lifecycle failures (never rotated, over-scoped, invisible inventory),
not single leaks.

## 2. Check inventory

1. **Inventory first**: you cannot protect what you haven't listed —
   enumerate every credential class (cloud keys, DB passwords, JWT
   signing keys, webhooks, CI tokens), its owner, scope, and age.
   An unlisted credential is a finding by itself.
2. **Generation**: secrets generated with cryptographic randomness
   (secrets module / crypto RNG); no human-chosen passwords for
   machine-to-machine auth; minimum entropy by class (API keys ≥ 128
   bits).
3. **Storage**: secrets live in a manager (vault-class tool or platform
   secret store) with access control and audit logs; repo storage is
   forbidden regardless of "private" repo claims.
4. **Distribution**: platform → workload at boot (mounted secret,
   identity-based access); the service reads its own secrets only; no
   secret ever passes through tickets, chat, email, or image layers.
5. **Rotation**: every credential class has a rotation interval and an
   automation path (dual-credential overlap so rotation doesn't cause
   downtime); signing keys have offline roots and online leaves.
6. **Scoping**: each credential grants the minimum (DB user scoped to its
   schema; cloud roles per service); shared "god keys" are a finding even
   if never leaked.
7. **Human access**: production secrets require break-glass approval and
   produce audit events; standing human read access to all secrets is a
   finding.
8. **Leakage response runbook**: on confirmed leak — **revoke first**,
   rotate, then hunt use in logs (reverse order burns the window); the
   runbook includes every credential class, not just passwords.
9. **Scan continuously**: secret scanning on repos and CI logs; the
   scanner's findings trigger the runbook automatically; historical
   leaks in git history require rotation, not history rewriting.
10. **Third-party credentials**: vendor API keys get per-service identity
    and per-service revocation; if a vendor supports scoped sub-keys or
    OIDC federation, prefer it over shared master keys.

## 3. Evidence & severity anchors

- Critical: leaked production credential still valid (unrotated); secret
  in a public repo or CI log without revocation.
- High: shared admin credential across services; no rotation path for a
  class of secrets; secrets in image layers.
- Medium: manual rotation on a quarterly class; missing audit on secret
  access; break-glass without alerting.

## 4. Common wrong answers

- "We removed it from the file" — removal without rotation changes
  nothing; the credential is compromised the moment it hits any log or
  history.
- Treating rotation as risky downtime — dual credentials exist exactly to
  make rotation boring.
- Encrypting secrets at rest in a repo (git-crypt style) and calling it a
  vault: access control and audit are the point, not encryption alone.
