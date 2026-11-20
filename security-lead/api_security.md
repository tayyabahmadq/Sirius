# Playbook — API Security Verification (develop stage)

## 1. Orientation

Verify an API's security posture endpoint by endpoint: authentication,
authorization, input handling, output shape, and abuse limits. Inputs:
route table / OpenAPI spec, sample handlers, auth middleware. An API is
secure when *every* route satisfies the inventory — one missing route
compromises the whole surface.

## 2. Check inventory

1. **Authentication coverage**: enumerate every route; flag any without
   auth except an explicit public allowlist (health, docs). Discovery via
   framework route dump beats reading code.
2. **Object-level authorization (BOLA/IDOR)**: for every route with an id
   parameter, confirm the query is scoped to the authenticated caller
   (`WHERE owner_id = current_user`) — not just that the user is logged in.
3. **Function-level authorization**: admin/action routes check role
   server-side; the client hiding a button is not authorization.
4. **Input validation**: schema/DTO at the boundary (types, ranges,
   lengths, enums); reject unknown fields (mass assignment) instead of
   splatting the payload into models.
5. **Mass actions**: bulk endpoints (ids: [...]) enforce the same
   per-object authorization as single endpoints — loops that skip the
   ownership check are a class of BOLA.
6. **Rate limiting & quotas**: public and authed endpoints have rate
   shape; unbounded expensive endpoints (search, export, report) have
   explicit quotas.
7. **Response shape**: serializers return an explicit allowlist of fields
   (no `__all__`, no raw model dumps); errors return generic messages,
   details to logs.
8. **HTTP method safety**: state-changing operations reject GET; CORS
   config allows only trusted origins (credentials never with `*`).
9. **Idempotency & replay**: payment-like actions carry idempotency keys;
   signed webhooks verify signatures and timestamps (replay window).
10. **Versioning & deprecation**: deprecated auth schemes (basic auth,
    api-key-in-query) have a sunset date; keys in URLs leak into logs.

## 3. Evidence & severity anchors

- Critical: unauthenticated write route; BOLA on payment/PII read.
- High: role check missing on action routes; unknown-field splatting into
  models; webhook without signature verification.
- Medium: missing rate shape on expensive endpoints; over-fetched fields;
  api key accepted in query string.

## 4. Common wrong answers

- Treating "it returns 401 without a token" as authorization — 401 is
  authentication; BOLA lives behind it.
- Recommending GraphQL/WAF as a substitute for per-route authz checks.
- Flagging internal undocumented routes as public — verify reachability
  first, then classify.

## 5. Syntax Anchors (exact patterns for a small model)

- **BOLA/IDOR**: ORM calls using route parameters directly
  (`User.find(params[:id])`, `db.users.get(id)`). Must be scoped, e.g.
  `current_user.posts.find(id)`.
- **Mass assignment**: `**kwargs`, `*args`, or `request.json` passed directly
  into constructors or `.update()` without a DTO/schema filter.
- **Authz bypass**: route registered without a decorator/middleware check;
  compare against the auth matrix, not against the endpoint name.
- **Injection**: string concatenation/f-strings inside SQL, Cypher, or shell
  calls; require parameterized queries or allowlists.
