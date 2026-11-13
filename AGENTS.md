# Codex engineering instructions — Azure Secure Sales Intelligence Platform

## Purpose

Build one coherent, evidence-backed Azure sales-intelligence platform through six phases. Favor production-minded engineering choices, small verifiable change sets and clear decision records. Public documentation must explain components **implemented and why they serve a business or engineering need**. Use no fictional company identity or personal career-preparation narrative in public repository files.

## Before each task

Read `README.md`, `PLANS.md`, `docs/architecture/OVERVIEW.md`, `docs/architecture/DATA_CONTRACT.md`, and the applicable guidance in `docs/agents/`. Inspect the real repository to distinguish placeholders, proposed architecture and verified deployment evidence.

## Architecture contracts

- Synthetic event producer using Entra identity -> Event Hubs Standard Capture -> real ADLS Bronze Avro -> ADF validation -> Silver Parquet -> Synapse serverless SQL Gold -> Azure SQL serving -> executive AI report based on verified KPI rows.
- GitHub Actions OIDC, Terraform, identity and network controls, Checkov/Gitleaks, Azure Policy, Defender for Cloud posture review, Azure Monitor/Log Analytics, and Sentinel with an actual tested AzureActivity detection/incident.
- An AKS producer Job may demonstrate workload identity and container hardening while preserving the same producer, schema and stream.
- Enforce sales event IDs, UTC timestamps, report run IDs, deduplication, rejected-row accounting, idempotent SQL loads, freshness and verifiable output claims.

## Agent delegation

The primary Codex agent is coordinator. Use the agent definitions under `.codex/agents/` for bounded implementation, independent reviews, architecture mentorship and technical publication. Delegate parallel tasks only when files/interfaces do not overlap. Each specialist returns objective, affected files, exact tests and results, decision rationale, risks and required approvals.

| Agent | Typical assignment |
| --- | --- |
| `platform_engineer` | Terraform, Azure RBAC/identity/network, OIDC and integration |
| `security_engineer` | IaC/policy controls, Defender posture, Sentinel KQL and response |
| `data_ai_engineer` | Producer, ADF, Silver/Gold, Azure SQL and AI evidence |
| `sre_quality_engineer` | Observability, validation, alerts, runbooks and reliability testing |
| `architecture_mentor` | Independent architecture critique, conceptual explanation and AWS/Azure design parallels |
| `technical_publisher` | Evidence-based README, diagrams, walkthroughs and technical case studies |

## Workflow and permissions

1. Orient in read-only mode and propose scope/paths, dependencies, tests and cost/risk.
2. After approval to implement, change only scoped local files and run nonmutating local validation.
3. Assign independent technical review; report severity and file/line for actionable findings.
4. Present review and deployment approval requests separately. Only the human lead decides architecture, cost, cloud writes, branch push/merge and external publication.
5. After expressly approved live validation, record sanitized results with timestamps, cost, recovery/incident evidence and cleanup status.
6. Ask the `architecture_mentor` for a design debrief; ask the `technical_publisher` to update public docs from verified evidence only.

Every change must be reviewed by an agent other than its author. Model reviews supplement deterministic checks and the human merge decision. Repository branch rulesets and CI must be separately configured.

## Security and integrity

Require explicit human authorization before Azure writes, subscription-level diagnostics changes, Sentinel/Defender activation, paid services, test events, `terraform apply/destroy`, GitHub settings or remote push/merge, and external publication. Do not store credentials, tokens, state files, secret variables, real customer records or unredacted identifiers in Git. Use synthetic data; least-privilege Entra roles; small bounded experiments; scoped resource diagnostics; and budget/cleanup evidence.

Never claim deployed, reviewed, secure, compliant, cost-effective or successful based on a plan or unexecuted test. Show `Planned`, `Implemented / locally tested`, `Verified in Azure`, or `Blocked` precisely.

## Public technical writing standard

Write for platform engineers, security reviewers, hiring managers and technical users: what problem was solved, which architecture was built, why each component matters, how to reproduce/verify it, and what evidence supports the results. Keep personal study notes, mock assessment records, outreach drafts and unpublished scripts outside tracked repository paths. Preserve attribution for any third-party material actually reused. See `docs/agents/PUBLISHING_STANDARDS.md`.
