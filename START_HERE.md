# Start here: OpenAI Codex

This is the repository entry point for the Azure Secure Sales Intelligence Platform. It is a project scaffold with agent instructions and implementation acceptance criteria. It does not represent deployed Azure infrastructure.

## 1. Prepare the repository

1. Create an empty **private** GitHub repository named `azure-secure-sales-intelligence` with no generated README, license or `.gitignore`.
2. Clone it using GitHub Desktop or `git clone`.
3. Extract **the contents of the repository starter ZIP** into the cloned repository root so `AGENTS.md` and `.codex/` sit at the root (not inside a second nested folder).
4. In your terminal run `git status` and verify the dot folders `.codex/` and `.github/` are present.
5. Review the files; commit as `chore: initialize platform architecture and codex workflow`; push the initial commit.

## 2. Connect Codex

Open the cloned folder in Codex CLI/app/IDE extension. The root `AGENTS.md` provides shared instructions; `.codex/config.toml` and six `.codex/agents/*.toml` files configure specialist subagents for supported Codex clients. Enable/trust the repository configuration if the client requests this. Mult-agent behavior and the ability to spawn specific roles depend on the client and its current capabilities.

**First task — copy into Codex (read-only):**

```text
Act as the technical coordinator. Read AGENTS.md, README.md, PLANS.md,
docs/architecture/OVERVIEW.md, docs/architecture/DATA_CONTRACT.md,
docs/agents/OWNERSHIP.md, docs/agents/REVIEW_POLICY.md, and docs/agents/WORKFLOW.md.
Inspect repository contents and distinguish placeholders from implemented code.
Use platform_engineer, security_engineer, data_ai_engineer, and
sre_quality_engineer for independent read-only reviews when available.
Ask architecture_mentor to critique Phase 1 tradeoffs and request
technical_publisher to assess README clarity against actual evidence.
Synthesize a Phase 1 readiness brief: file-by-file tasks, owner, shared
interfaces, required Azure permissions, verification commands, cost exposure,
security checks and human approval gates.
Do not edit files, create cloud resources, apply/destroy Terraform,
change GitHub settings, commit, push, merge or begin another phase.
```

## 3. Start Phase 1 local work

After reviewing the readiness brief, use the scoped prompt in [`docs/agents/PHASE_01_PROMPTS.md`](docs/agents/PHASE_01_PROMPTS.md). Authorization to write and locally validate code is separate from approval to change Azure resources or GitHub configuration.

## 4. Review and explain decisions

Before marking a phase complete, ask `architecture_mentor` to explain the design in plain English, critique trust boundaries, test your reasoning, and compare equivalent AWS patterns. You can keep personalized practice notes in a local-only coaching kit separate from the repository.

## 5. Build a credible public engineering record

After real verification, ask `technical_publisher` to update `README.md`, `docs/PROJECT_WALKTHROUGH.md`, relevant ADRs, and a short case study citing sanitized evidence and actual outcomes. Review every claim before release. Then change repository visibility to public only after running a sensitive-data scan and a complete documentation review.

## Repo hygiene before each push

Check `git status`, `.gitignore`, changes to evidence screenshots and accidental credentials. Do not add third-party source guides or private transcripts to version control. CI protections and GitHub rulesets must be configured separately; text files do not enforce them.
