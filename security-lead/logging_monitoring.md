# Playbook — Security Logging & Monitoring (operate stage)

## 1. Orientation

Design the audit trail that detection, forensics, and the IR playbook
depend on. The unit of value is the **investigation**: for each abuse case
from the threat model, can we answer "who did what, when, from where"
after the fact? If not, that's the finding.

## 2. Check inventory

1. **Identity-bound events**: every security-relevant action records the
   authenticated principal (user id, service identity) — requests
   attributed only to an IP address cannot support authorization analysis.
2. **Event coverage**: login success/failure, permission denied, password
   reset, MFA changes, role/admin changes, data export, secret access,
   config changes, token issuance. These are the IR backbone events.
3. **Field hygiene**: structured logs (JSON) with stable field names
   (timestamp UTC, actor, action, resource, result, source ip,
   request id); free-text log lines can't be queried under pressure.
4. **No secrets in logs** (auditor class `secrets_in_logs`): passwords,
   tokens, Authorization headers, reset links, full card numbers never
   reach any log; log redaction is a middleware, not per-dev diligence.
5. **Immutability & retention**: security logs ship to a store the app
   cannot write to or delete (attacker-proofing: separate credentials),
   retained long enough to cover slow-burn intrusions and compliance
   needs (define per class, in writing).
6. **Time sync**: NTP-synchronized clocks across services — an
   investigation across unsynchronized clocks is guesswork.
7. **Detection rules on the backbone events**: alert on impossible travel/
   burst failures (credential stuffing), permission-denied spikes (BOLA
   probing), role changes (privilege escalation), export volume anomalies
   (exfiltration). Rules start coarse — precision comes from iteration,
   silence is worse than noise initially.
8. **Signal vs noise budget**: every alert has an owner and an expected
   action; alerts nobody acts on get deleted — fatigue hides real events.
9. **Traceability**: request id propagates across services so one request's
   story is reconstructible end-to-end; metrics and logs share ids.
10. **Test the loop**: quarterly — inject a synthetic attack (test login
    burst, test export) and verify: it triggered a detection, someone
    could investigate, and the trail was complete. A monitoring design
    that has never been exercised is a hypothesis.

## 3. Evidence & severity anchors

- High (design): backbone event classes missing; logs writable/deletable
  by the app; no request-id correlation across services.
- Medium: unstructured logs; retention undefined; alerts without owners.
- The "no secrets in logs" auditor class remains the code-level gate —
  this playbook is the system-level complement.

## 4. Common wrong answers

- Logging everything at debug to "not miss anything" — volume buries
  signal and costs the incident the ability to search.
- Treating logs as a debugging tool only: audit logs are a security
  control with different requirements (immutability, identity, coverage).
- Buying a SIEM as the fix: without backbone event coverage upstream,
  the SIEM analyzes air.
