# Architecture: secure sales intelligence platform

## Purpose

A synthetic sales workload provides auditable revenue and product-category analytics while demonstrating secure, repeatable platform provisioning and a measurable operational/security response. The architecture prioritizes data correctness, access isolation, observability and deployment evidence.

## Connected workload

```text
Python synthetic producer -> Event Hubs Standard + Capture -> ADLS Bronze Avro
    -> ADF validation / reject metrics -> ADLS Silver Parquet
    -> Synapse serverless SQL Gold -> idempotent Azure SQL KPI serving
    -> Azure AI executive summary (current SQL snapshot + provenance)
```

**Why these components:** Event Hubs decouples event producers, Capture preserves source records for replay, ADF provides orchestration/quality gates, ADLS maintains raw and trusted layers, Synapse gives on-demand analytical views, and Azure SQL serves small auditable KPI snapshots. AI output uses current, checked values rather than invented sample numbers. Capture and downstream jobs introduce bounded staged latency; show actual freshness.

## Platform and security planes

- **Provision and authenticate:** Terraform, GitHub Actions OIDC, Entra identities and scoped RBAC make resource changes reproducible, attributable and passwordless.
- **Prevent:** Checkov, Gitleaks and Azure Policy validate risky changes; Defender for Cloud supplies posture findings.
- **Observe:** Azure Monitor metrics and selective Log Analytics logs expose ingestion, pipeline and SQL health and budgeted telemetry costs.
- **Detect and respond:** Sentinel ingests AzureActivity and detects a controlled configuration write; its incident is triaged and resolved with reviewed infrastructure-as-code changes.
- **Kubernetes integration:** A time-boxed AKS Job runs the shared producer with Workload Identity and a restricted container security context.

## Verification status

These are intended interfaces. Each capability becomes verified after its actual deployment, query results, tests, security events and cleanup artifacts are recorded with date and context under `evidence/`.
