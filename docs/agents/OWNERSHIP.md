# Ownership and review boundaries

| Role | Owned or leading paths | Partner/reviewer |
| --- | --- | --- |
| Platform | `infra/`, `.github/workflows/`, cloud role assignments | Security reviews RBAC/policy; SRE reviews telemetry |
| Security | `security/`, `infra/modules/sentinel/`, `infra/modules/policy/` (coordinate Terraform ownership) | Platform verifies provider and identity integration |
| Data & AI | `scripts/`, `pipelines/adf/`, `sql/`, `data/`, `k8s/producer-job/` implementation | SRE reviews data tests, Platform reviews auth and Azure resource interfaces |
| SRE & Quality | `tests/`, `docs/runbooks/`, telemetry design and `evidence/` templates | Security checks incident handling, Data reviews data quality assertions |
| Architecture mentor | Read-only integrated design assessment; approved ADR commentary | Human architect owns decisions |
| Technical publisher | `README.md`, `docs/PROJECT_WALKTHROUGH.md`, `docs/case-studies/`, approved diagrams | Primary owner and SME verify all technical claims |

Main Codex coordinator resolves interfaces and PR scope. Each PR must have a review by an agent other than its author; a human owns deployment and merge decisions. Files are assigned by task when responsibility overlaps. Never run agents concurrently against shared Terraform state or the same working file.
