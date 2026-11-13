# Evidence-driven technical documentation standard

## Target readers

An engineer should understand architecture and data flow; a reviewer should find tests and observed security proof; a recruiter or hiring manager should understand technical ownership and why the project matters within two minutes.

## Documentation hierarchy

1. `README.md`: business challenge, architecture, component choices and validation links.
2. `docs/PROJECT_WALKTHROUGH.md`: end-to-end story with security, reliability and operating evidence.
3. `docs/decisions/`: brief ADRs stating an implemented decision and its constraints.
4. `docs/case-studies/`: single design challenge, implementation, failure/recovery and measurable impact.
5. `evidence/`: reproducible, sanitized outputs from actual tests, with dates and resource-cost context.

## Verification rules

Use accurate evidence status: Planned / Implemented locally / Verified in Azure / Blocked. A design diagram does not imply deployment. Report real cost, real observed throughput and real query results or leave a clearly labeled placeholder. Prefer business outcome and technical mechanisms over self-promotion. Use neutral industry language, cite any third-party material actually reused, and redact sensitive context. External articles or video narratives should derive from this checked record and receive human editorial approval before distribution.
