# Playbook — Secure Architecture Review (design stage)

## 1. Orientation

Review the *shape* of the system: identities, trust boundaries, secret
flows, failure modes. Inputs: architecture doc, service list, auth design,
secret flow, network topology. A good architecture review finds classes of
bugs once instead of reviewing each instance forever.

## 2. Check inventory

1. **Single strong identity per hop**: every service-to-service call
   authenticates (mTLS, signed service tokens) — no "internal network is
   trusted" assumptions.
2. **Centralized authn/authz**: one session/token validation point;
   per-service re-implementation of JWT checks is how `verify_signature:
   False` sneaks in.
3. **Least privilege**: each service's credentials grant only its own
   resources (DB user scoped to its schema; cloud roles scoped per
   service — no shared admin identity).
4. **Secret flows**: secrets move platform → service at boot only; never
   service → service; never in code, images, or CI logs (see
   secrets_management.md).
5. **Tenant isolation**: one shared schema/database per service with
   tenant_id scoping — decide row-level vs schema-level isolation and
   enforce it in the data layer, not the view.
6. **Failure defaults**: on dependency failure, services fail closed for
   security-relevant actions (authn unavailable = deny, not allow).
7. **Ingress/egress shape**: public surface minimized; egress filtered or
   at least allowlisted for services that fetch URLs (ssrf control).
8. **Data lifecycle**: encryption in transit everywhere (TLS, internal
   included), encryption at rest for PII/payment data, defined retention
   and deletion paths (right-to-erasure needs a design, not a TODO).
9. **Multi-layer validation**: input validation at the boundary (schema)
   AND at the sink (parameterized queries, path containment) — one layer
   is one bypass away from failure.
10. **Blast radius**: can a compromise of one service reach credentials of
    another? (Shared runner tokens, shared DB superuser, wildcard cloud
    role = one finding covering a class.)

## 3. Evidence & severity anchors

- Critical: public write path without identity; shared admin credential
  across services.
- High: fail-open auth dependency; cross-service secret sharing; missing
  tenant scoping in the data layer.
- Medium: unfiltered egress on a URL-fetching service; missing encryption
  at rest for internal-only data.

## 4. Common wrong answers

- Recommending a service mesh for a 3-service monolith — match control
  weight to scale.
- Treating "it's internal" as an authentication strategy.
- Encryption theater: TLS at the edge only while internal hops carry
  tokens and PII in cleartext.
