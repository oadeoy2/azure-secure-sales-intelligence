# ADR 0001: Single integrated Azure data and security platform

**Status:** Architecture approved for implementation; service-level verification pending. **Date:** 2026-11-13.

## Context

The platform needs trustworthy sales KPIs, secure delivery, operational awareness and a reviewable security response around one connected workload. The same synthetic event contract and report identifiers should move across all stages.

## Decision

Use Event Hubs Standard/Capture for ingestion, ADLS Bronze/Silver for traceable raw and trusted records, ADF for quality and orchestration, Synapse serverless SQL for analytical Gold queries, Azure SQL serverless for small secured KPI serving, and Azure AI for a provenance-backed executive report. Manage identities/infrastructure via Terraform and GitHub OIDC; govern access through Entra/RBAC, Azure Policy and Defender posture. Observe with Azure Monitor and selective Log Analytics, and verify actual Sentinel `AzureActivity` detections and response. Use a short-lived AKS Job as a workload-identity integration exercise with the same producer.

## Rationale

These components form independently testable boundaries with clear data lineage, security accountability and costs that can be measured by service. A serving database makes the business KPI interface queryable independently of lake exploration. Sentinel provides a concrete preventive-detective-response lifecycle tied to the platform's configuration integrity.

## Verification

Each phase must supply tests, an observed cloud result and a sanitized evidence manifest before its status is marked verified. Record any networking, latency, identity, regional support or cost tradeoff discovered during deployment in a follow-on ADR.
