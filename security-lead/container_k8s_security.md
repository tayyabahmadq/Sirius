# Playbook — Container & Kubernetes Hardening (build/deploy stage)

## 1. Orientation

Review Dockerfiles, compose files, and k8s manifests for the runtime
attack surface: image provenance, privilege, isolation, and network
reach. The question is not "does it run" but "what can a compromised
container do".

## 2. Check inventory

1. **Base images pinned**: version tags or digests, never `latest`;
   minimal bases (alpine/distroless/slim); images from the official
   registry namespace; known-CVE base versions flagged.
2. **Root user**: containers run as a non-root USER; k8s
   `runAsNonRoot: true` + a fixed `runAsUser`; no sudo in images.
3. **Capabilities & privilege**: `privileged: false`,
   `allowPrivilegeEscalation: false`, drop ALL capabilities and add back
   only what's needed (usually none); no host namespaces
   (`hostNetwork/hostPID/hostIPC: false`).
4. **Filesystem**: `readOnlyRootFilesystem: true` with explicit writable
   volumeMounts for tmp/data; build containers don't carry source secrets
   in layers (.dockerignore for .env, .git, keys).
5. **Secrets into runtime**: no secrets in ENV build args or image layers
   — env vars are readable via `/proc` and image history; use secret
   manager or k8s Secrets mounted as files, never baked images.
6. **Resource controls**: CPU/memory requests+limits on every container —
   no-limit pods are the memory-leak blast radius; also protects neighbors
   from noisy-neighbor OOM.
7. **Network policy**: default-deny ingress/egress per namespace, then
   allow service-to-service paths explicitly; public pods separated from
   internal-only pods by policy, not by convention.
8. **Service account**: pod-level service accounts with least RBAC (no
   cluster-admin on app pods); `automountServiceAccountToken: false`
   where the app never calls the API.
9. **Liveness/readiness + securityContext defaults set at namespace level
   (PSP/PSS baseline: restricted)** — a namespace with unrestricted pods
   undermines per-pod settings.
10. **Probe for the class, not the instance**: one misprivileged
    Deployment usually means a copy-pasted template — fix the template
    (Helm chart / base manifest), then sweep all environments.

## 3. Evidence & severity anchors

- Critical: privileged pod with host mounts or cluster-admin RBAC on a
  user-facing service.
- High: root containers on public services; secrets baked into images;
  missing resource limits on memory-leak-prone services.
- Medium: unpinned minor-version tags; missing default-deny network
  policy; automounted tokens on API-less pods.

## 4. Common wrong answers

- Recommending `latest` → `stable` — both are mutable; pin versions or
  digests.
- Dropping capabilities list without testing: verify the app still runs,
  otherwise fixes get reverted silently.
- Treating network policy as "nice to have": east-west movement is how a
  web-RCE becomes a cluster compromise.
