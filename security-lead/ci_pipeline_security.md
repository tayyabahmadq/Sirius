# Playbook — CI Pipeline Security (build/deploy stage)

## 1. Orientation

The pipeline is privileged code that runs on attacker-influenced input
(PR diffs, dependency names, issue titles). Harden it like production:
least privilege, credential isolation, no injection surface. Inputs:
pipeline YAML (.github/workflows, .gitlab-ci.yml), runner config, deploy
jobs.

## 2. Check inventory

1. **Pull-request trust**: workflows triggered by `pull_request_target`
   run with repo secrets on untrusted code — restructure so untrusted
   code never shares a job with secrets (build in unprivileged job,
   deploy with secrets only on protected refs).
2. **Injection via untrusted input**: user-controlled text interpolated
   into `run:` shell blocks (branch names, PR titles, issue bodies,
   commit messages) is command injection on the runner — use `env:`
   intermediaries, never `${{ }}` inline in shell.
3. **Credential scoping**: tokens (GITHUB_TOKEN, cloud creds) get
   least-privilege scopes and short lifetimes; deploy credentials are
   OIDC-federated where available, never long-lived keys in repo secrets
   used by all jobs.
4. **Third-party actions pinned**: external actions pinned to a full
   commit SHA (tags are mutable); audit new actions before adoption.
5. **Runner isolation**: self-hosted runners never serve public repos
   (ephemeral runners per job otherwise); no docker.sock mounted into
   build containers; PR builds cannot reach internal network.
6. **Supply-chain gates**: dependency audit step (pip-audit --strict /
   npm audit / trivy image --exit-code 1) that FAILS the pipeline;
   SBOM emitted; artifact/image signed and the signature verified at
   deploy.
7. **Secrets hygiene**: no secrets in build logs (`set -x` off,
   mask env); a leaked runner log is a credential leak — logs are the
   exfiltration channel.
8. **Branch protection**: deploys run only from protected refs; releases
   tagged from CI, never from laptops; force-push disabled on release
   branches.
9. **Environment separation**: dev/test/prod deploy jobs are separate
   environments with separate approvals and credentials — one pipeline
   compromise must not equal prod compromise.
10. **Post-deploy verification**: the pipeline verifies what it deployed
    (image digest matches the signed artifact), not just that commands
    exited 0.

## 3. Evidence & severity anchors

- Critical: secrets available in a job running untrusted PR code;
  shell interpolation of untrusted input into `run:`.
- High: unpinned third-party actions with secrets in scope; shared
  long-lived deploy keys; docker.sock on PR runners.
- Medium: missing audit/SBOM gates; secrets visible in masked-but-not-
  redacted logs; missing environment separation.

## 4. Common wrong answers

- Recommending "move to a managed CI" as a fix for pull_request_target —
  the trust structure is the bug, not the vendor.
- Treating signed images as optional hardening: without deploy-time
  verification, signatures are decoration.
- Flagging dev-only pipelines with no secrets as critical — severity
  follows credential reach.
