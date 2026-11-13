# Delivery workflow

1. **Scope:** inspect current branch, code and evidence, identify one concrete deliverable, dependencies, acceptance tests and cloud-cost exposure.
2. **Design:** capture material security, operations, reliability and cost rationale in an ADR; request human architecture approval.
3. **Implement:** delegate bounded, nonoverlapping local code tasks; run local format, validation, lint, secrets scan and functional tests as available.
4. **Cross-review:** independent author/reviewer checks correctness, identity, networking, billing, reliability, reproducibility and evidence quality.
5. **Approval:** human explicitly authorizes Azure operations and budget. Preview and review Terraform plans before approved changes.
6. **Verify:** time-box the live validation, collect redacted screenshots/query results and measured cost, and capture cleanup/retention state.
7. **Teach:** `architecture_mentor` performs a technical design debrief and provides Azure/AWS analogies when appropriate.
8. **Publish:** `technical_publisher` reconciles verified evidence to README, architecture decisions, walkthrough and case-study claims; human reviews the public diff.
9. **Close:** update phase status and stop before the next scope begins.

## GitHub controls

Configure default branch rulesets with required pull requests and passing security/test checks when those checks actually exist. A separate eligible human reviewer is needed if enabling required GitHub human approvals; an AI review alone does not satisfy a GitHub approval policy. Review `CODEOWNERS`, repository secrets/variables, OIDC federation subjects and branch settings before cloud CI runs.
