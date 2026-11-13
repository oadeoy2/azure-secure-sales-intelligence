# Phase 1 Codex prompts

## A. Scope and read-only design gate

```text
Review PLANS.md Phase 01 and existing repository contents. Assign platform_engineer to Terraform/state/OIDC preflight and security_engineer to Sentinel/AzureActivity/Policy/RBAC preflight; ask sre_quality_engineer to define verification and cost evidence. Return an actionable task map with file paths, Terraform outputs and identity contracts, security test gates and estimated cost sources. No file changes, Azure operations or GitHub writes.
```

## B. Approved local implementation

```text
Implement Phase 01 locally, restricted to the plan I approved. Delegate nonoverlapping Terraform, CI, security test and observability files to the appropriate specialists. Include Terraform formatting and validation, Checkov/Gitleaks scanning in GitHub Actions, secure OIDC deployment configuration, Log Analytics + Sentinel onboarding and AzureActivity subscription diagnostics. Add reproducible local tests/fixtures and explain remaining Azure permissions. Perform code review with a different agent. Run nonmutating local checks and report exact results. Do not apply/destroy, activate paid services, alter GitHub settings, send test events, push, merge, or proceed to Phase 02 without approval.
```

## C. Independent review and evidence gate

```text
Review the Phase 01 diff and evidence against PLANS.md. Ask security_engineer to inspect RBAC/OIDC/Sentinel configuration and sre_quality_engineer to inspect telemetry, testability and resource cost. Give findings by severity with file/line and verification steps. Ask architecture_mentor to question the trust boundaries and explain AWS parallels. Ask technical_publisher to suggest README and case-study updates using only verified results. Do not edit files or deploy.
```
