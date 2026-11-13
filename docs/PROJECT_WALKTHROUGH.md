# Project walkthrough: Azure Secure Sales Intelligence Platform

**Current state:** planned reference architecture. This walkthrough will be expanded with tested deployment artifacts and measured outcomes as phases complete.

## Problem and expected outcome

A sales analytics workload needs reliable data freshness, accurate rollups and trustworthy executive reporting. Security teams need deployment controls and a way to investigate configuration changes. Platform operations needs actionable signals for pipeline health and restoration.

## Architecture and ownership

Terraform and GitHub Actions manage reusable Azure foundations. A synthetic producer publishes to Event Hubs; raw records land in ADLS, flow through ADF quality validation, become Synapse Gold aggregates, and are published into secured Azure SQL. An AI summary presents current verified business metrics. The platform is governed with policy, monitored operationally, and backed by Sentinel detections and incident handling. See [architecture](architecture/OVERVIEW.md).

## Evidence-linked demonstrations

| Demo | What it proves | Evidence status |
| --- | --- | --- |
| Secure pull-request gate | Unsafe IaC change is caught before deployment | Planned |
| Traceable business data | Producer run maps into Bronze, Silver, Gold and SQL KPI rows | Planned |
| Governing access and posture | RBAC, Azure Policy and Defender recommendations are inspected | Planned |
| Security detection + response | Real AzureActivity event triggers Sentinel rule and incident | Planned |
| Reliability restoration | A pipeline issue is detected, diagnosed and recovered | Planned |
| Grounded reporting | AI brief values reconcile with current SQL snapshot | Planned |

Once measured, record exact commands, queries, test run IDs and redacted proof under `evidence/`, then update this page with observed results and realistic business impact. No customer or payment data is used.
