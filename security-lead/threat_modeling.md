# Playbook — Threat Modeling (STRIDE, design stage)

## 1. Orientation

Run before implementation on any new feature, service, or data flow.
Inputs: architecture sketch, data-flow description, trust boundaries
(user / internet / service mesh / admin / third party / database). Output:
abuse cases per element + mitigations mapped to the design, not to a wish
list.

## 2. Check inventory

1. **Diagram the data flow**: every trust boundary crossed by data or an
   identity (external user → API → service → DB; service → third party;
   admin → control plane).
2. **Enumerate assets**: data worth stealing (PII, tokens, payment data),
   capabilities worth hijacking (payments, admin actions, email sending).
3. **Spoofing**: how does each boundary authenticate the caller? Any
   unauthenticated hop is a finding.
4. **Tampering**: can an actor modify data in flight or at rest outside a
   validated path (unsigned webhooks, client-trusted prices, mutable
   queues)?
5. **Repudiation**: are security-relevant actions attributed to an identity
   in tamper-evident logs?
6. **Information disclosure**: what leaves each component (errors, logs,
   responses, caches) and to whom?
7. **Denial of service**: what single unbounded input (payload size, list
   size, rate) can exhaust memory/connections/cost?
8. **Elevation of privilege**: enumerate roles and the fields/endpoints
   that could grant them (mass assignment, IDOR, admin routes).
9. **Abuse cases**: for each asset, write the one-sentence "attacker with X
   can do Y via Z" — a threat with no concrete path is not a threat.
10. **Mitigation mapping**: each accepted threat needs a control that lives
    *in the design* (not "we'll be careful"); unresolved criticals block
    the design gate.

## 3. Evidence & severity anchors

- Critical: unauthenticated write path to an asset; privilege escalation
  reachable from public input.
- High: tampering possible on an internal hop; unbounded resource
  consumption on a public endpoint.
- Medium/low: repudiation gaps, missing rate shape, disclosure of
  non-sensitive metadata.

## 4. Common wrong answers

- Listing every STRIDE letter for every component generically — the value
  is in concrete abuse paths, not coverage theater.
- Proposing controls that contradict the stated requirements (e.g., mTLS on
  a public API) without flagging the trade-off.
- Modeling only the happy path: abuse cases start from the attacker's
  shortest path, not the user journey.
