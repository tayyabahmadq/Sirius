# SIRIUS Security-Lead Corpus (Phase 5)

The second knowledge base: everything SIRIUS needs to act as the **head of
security across the software development lifecycle** — not just auditing
artifacts, but running design reviews, hardening pipelines, leading
incidents, and knowing when *not* to raise a finding.

All content is original, written for the SIRIUS project. Nothing is copied
from any third-party repository or dataset.

## Contents

```
ROLE.md                  the role definition: capability map (SDLC stage →
                         playbook) + the answer contract
                         (recommendation → why/abuse → controls → first action)
threat_modeling.md       STRIDE-in-practice: trust boundaries, abuse cases,
                         mitigation mapping (design stage)
secure_architecture.md   identities, least privilege, tenant isolation,
                         fail-closed defaults, blast radius (design stage)
secure_code_review.md    diff-focused review: new sinks, authz deltas,
                         dependency deltas, restraint rules (develop stage)
api_security.md          endpoint-by-endpoint verification: BOLA/IDOR, mass
                         assignment, rate shape, response shape (develop)
ci_pipeline_security.md  pull_request_target, injection via ${{ }},
                         credential scoping, supply-chain gates (build/deploy)
container_k8s_security.md pinned images, non-root, capabilities, resource
                         limits, network policy, RBAC (build/deploy)
secrets_management.md    inventory → generation → storage → distribution →
                         rotation → leakage response (cross-cutting)
incident_response.md     declare → contain → preserve → triage → eradicate →
                         recover → learn (operate stage)
logging_monitoring.md    backbone events, immutability, detection rules,
                         game-day proof (operate stage)
lead_scenarios.json      87 scenario Q&A + 6 restraint traps (training data
                         source for script 17)
lead_eval_items.json     50-item capability eval (5 per capability + 5
                         traps), keyword-group format, selftested 50/50
```

## Design decisions

1. **Restraint is a capability.** 6 of the scenarios and 5 of the eval
   items are traps: the correct answer is "no finding — approve". A
   security lead that manufactures findings to look thorough is worse
   than useless; the eval measures this explicitly (`restraint` cap).
2. **Answers follow the ROLE.md contract** — recommendation first, then
   concrete abuse path, then controls, then the minimal first action. No
   generic boilerplate.
3. **Decontaminated by construction.** Script 17 runs a 13-gram overlap
   gate between every training item and all eval material (the 34-item
   suite, eval100, lead_eval_items) and drops collisions; 17 template
   overlaps were removed in the current build.
4. **Facts are conservative.** Only well-established version pairs are
   cited (Log4Shell = CVE-2021-44228, fixed in the 2.17.x line;
   Spring4Shell = CVE-2022-22965, fixed in 5.3.18/5.2.20). No invented
   CVEs, no unverifiable claims.

## Pipeline position

```
17_build_pass6_data.py    this corpus → sirius_train_pass6_lead.jsonl
                          (mixed with pass5 replay + auditor knowledge)
07_train_colab.py         --pass-name pass6 --base-model <pass5 merged dir>
                          (conservative: r=8, lr 1e-5, 1 epoch)
19_eval_capabilities.py   the 50-item eval + restraint score + McNemar
20_merge_scale_sweep.py   pick the merge scale at capability level
sirius_cli.py             the deterministic half of the role (CI gate)
```

Scanner/leader division of labor: `sirius_cli.py` handles the syntactic
classes deterministically (22 checks, same taxonomy as the auditor
corpus); the playbooks and the model handle judgment — races, design
flaws, process gaps, and the traps where the right answer is "clean".
