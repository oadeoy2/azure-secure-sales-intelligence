# Six-phase implementation roadmap

**Status:** planning and repository scaffold. Update status only after evidence exists.

| Phase | Deliverables | Acceptance evidence | Lead agents | Status |
| --- | --- | --- | --- | --- |
| 01 — Secure foundation | Terraform state and Azure baseline, Entra/RBAC, GitHub OIDC security checks, Sentinel workspace + AzureActivity | Blocked insecure CI fixture, real activity ingestion, scoped access and cost | Platform + Security | Planned |
| 02 — Ingestion | Synthetic Python events via identity-based Event Hubs sender; Capture to Bronze Avro; AKS Workload Identity exercise | Actual Avro, run/row counts, metric proof; AKS job and teardown if exercised | Data/AI + Platform | Planned |
| 03 — Data quality | ADF Bronze to validated Silver Parquet, dedup and reject diagnostics | Reconciliation, reproducible fixtures, observed failure signal | Data/AI + SRE | Planned |
| 04 — Analytics and governance | Synapse Gold aggregates, Azure SQL KPI serving, Policy and Defender posture | Gold-to-SQL numeric match, idempotent retry, scoped access and policy test | Data/AI + Security + Platform | Planned |
| 05 — AI report | Azure AI executive report grounded in current SQL snapshot | SQL figure cross-check, report ID, freshness and quality disclosures | Data/AI + SRE | Planned |
| 06 — Security operations and demo | Monitor workbook, Sentinel scheduled KQL, controlled test incident, safe triage, runbooks and cleanup | Actual incident fields, documented resolution, recovery and full data replay, measured bill and teardown | Security + SRE | Planned |

## Phase-level process

**Preflight -> local implementation -> cross-review -> local tests -> human deployment approval -> bounded Azure verification -> measured cost / teardown -> architecture debrief -> publication review.**

Do not advance a phase without a verifiable acceptance result or an explicitly recorded blocker. One coherent workload is carried through the entire implementation. Record actual hours and actual costs rather than forecasts as results.

## Engineering artifacts

- Infrastructure: `infra/bootstrap-state`, `infra/environments/lab`, `infra/modules/`
- Event and serving code: `scripts/`, `pipelines/adf/`, `sql/`, `k8s/producer-job/`
- Security: `security/kql/`, `security/playbooks/`, `security/tests/`
- Reliability and review: `tests/`, `docs/runbooks/`, `docs/decisions/`
- Public proof: `docs/PROJECT_WALKTHROUGH.md`, `docs/case-studies/`, `evidence/phase-0N/`
