# Playbook — Incident Response Leadership (operate stage)

## 1. Orientation

Lead the response to a suspected security incident (not an outage —
security IR assumes an adversary who adapts). Roles: incident lead
(coordination, decisions), SIRIUS (technical triage, containment design).
Order matters: contain → eradicate → recover → learn. Skipping to root
cause while the attacker is active is the classic failure.

## 2. Check inventory

1. **Declare and scope (15 minutes)**: what system, what access level, is
   it ongoing? Assign an incident lead and a scribe; start a timeline
   with UTC timestamps. Unknown scope means assume widest plausible scope.
2. **Contain before analyzing**: for active access — revoke credentials/
   sessions first (secrets runbook step 8), then isolate hosts, then
   preserve evidence. Containment actions that destroy evidence (wiping
   the box) trade the investigation for safety — prefer snapshot-then-
   isolate.
3. **Evidence preservation**: snapshot disks/memory, export relevant logs
   to append-only storage, record hashes; the timeline needs raw material
   that survives cleanup.
4. **Triage severity**: critical = active exfiltration/RCE on prod with
   customer impact → page executives, prepare comms; high = confirmed
   access without confirmed impact; medium = attempted/blocked. Severity
   drives comms and legal requirements (breach notification windows).
5. **Impact analysis**: what data could the access level reach? Use the
   credential's scope (not the attacker's intent) as the bound; check
   access logs for the credential's actual use window.
6. **Eradicate**: close the entry point (patch, disable the path, remove
   persistence — new users, keys, scheduled jobs, webshells) before
   recovery; verify by re-scanning, not by hoping.
7. **Recover**: restore from known-good, rotate everything the incident
   touched, monitor the fixed path specifically for recurrence — attackers
   re-test closed doors.
8. **Learn (blameless postmortem within a week)**: timeline, root cause,
   containment effectiveness, and 3–5 concrete hardening actions with
   owners and dates; convert at least one action into an automated gate
   (test, scan, policy) so the lesson compounds.
9. **Comms discipline**: one spokesperson; facts only (what happened,
   what we did, what users should do); never speculate about attribution
   in writing.
10. **Legal/compliance hooks**: breach notification triggers depend on
    data classes and jurisdiction — loop in legal early on customer-data
    incidents; document decisions with timestamps.

## 3. Evidence & severity anchors

- Critical: active attacker in prod, confirmed data access, ransomware
  in motion.
- High: confirmed credential compromise with unclear use; persistence
  found without confirmed data access.
- Medium/low: blocked attempts, scanner noise — still logged and trended,
  not paged.

## 4. Common wrong answers

- Rebuilding the compromised box before imaging it — destroys the only
  ground truth.
- Announcing "no data was accessed" before the access-log analysis
  supports it.
- Postmortems that end in "be more careful" — actions must be assignable
  and verifiable.
