# Engineering review policy

## Review questions

- **Correctness:** Does the code satisfy the current phase's interface and acceptance contract? Are failures, retries, replay, data quality and boundaries covered by tests?
- **Security:** Are OIDC/Entra credentials least privilege? Are RBAC and networking scoped? Are Sentinel detections and playbooks safe and reviewable? Are secret scans and policy checks enforced?
- **Reliability and operations:** Can we detect failures, isolate a fault, recover, and show the result? Are logs and metrics usable and cost-bounded?
- **Cost:** Are billable resource lifetimes and telemetry ingestion bounded, monitored and cleaned up?
- **Evidence:** Are test outputs and claimed metrics actually observed, timestamped, redacted and reproducible?
- **Documentation:** Does the public repo explain architecture and impact without personal material or unverifiable results?

Give actionable findings with severity, location and fix strategy; prefer meaningful issues over style-only suggestions. A different specialist must review changes written by an implementation agent. Mark unexecuted tests as such. Human architecture, deployment, publication and merge approvals remain mandatory.
