"""Offline workflow trust-boundary and private-plan regression tests.

Uses synthetic plans and calls only the pure Python handoff/summary helpers.
No Azure/GitHub CLI, Terraform or workflow dispatch is executed.
"""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml


ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github/workflows"
SCRIPTS = ROOT / ".github/scripts"
HANDOFF = runpy.run_path(str(SCRIPTS / "plan-handoff.py"))
CANARY = "SYNTHETIC_PRIVATE_PLAN_CANARY"
COMMIT = "a" * 40


def load_workflow(name):
    # BaseLoader preserves the YAML 'on' key and makes boolean handling explicit.
    return yaml.load((WORKFLOWS / name).read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def validate_privileged(workflow, kind):
    if set(workflow.get("on", {})) != {"workflow_dispatch"}:
        raise ValueError("Privileged jobs must be manual only")
    if workflow.get("permissions") != {"contents": "read"} or set(workflow.get("jobs", {})) != {kind}:
        raise ValueError("Unexpected repository permission or job")
    job = workflow["jobs"][kind]
    if job.get("environment") != {"plan": "lab-plan", "apply": "lab-deploy"}[kind]:
        raise ValueError("Wrong protected environment")
    if job.get("permissions") != {"contents": "read", "id-token": "write"}:
        raise ValueError("OIDC permission must be limited to the approved job")
    terms = {
        "github.event_name == 'workflow_dispatch'", "github.ref == 'refs/heads/main'",
        "github.event.repository.default_branch == 'main'",
        f"vars.WORKFLOW_{kind.upper()}_ENABLED == 'true'",
    }
    terms |= {"inputs.approved_cloud_read"} if kind == "plan" else {
        "inputs.reviewed_commit == github.sha", "inputs.confirmation == 'APPLY_REVIEWED_LAB_PLAN'"}
    actual = {term.strip() for term in job.get("if", "").split("&&")}
    if actual != terms or "||" in job.get("if", ""):
        raise ValueError("Privileged dispatch, main, enable or approval guard changed")
    if workflow.get("concurrency") != {"group": "terraform-lab-state", "cancel-in-progress": "false"}:
        raise ValueError("State writers must share a noncancelling concurrency group")
    for step in job.get("steps", []):
        action = step.get("uses")
        if action and (not re.fullmatch(r"[^@]+@[0-9a-f]{40}", action) or "upload-artifact" in action):
            raise ValueError("Unpinned action or public artifact handoff")
        if action and action.startswith("actions/checkout@"):
            if step.get("with", {}).get("ref") != "${{ github.sha }}" or step["with"].get("persist-credentials") != "false":
                raise ValueError("Checkout must use exact dispatch commit without persisted credentials")


class WorkflowBoundaryTests(unittest.TestCase):
    def test_current_privileged_workflows(self):
        for kind in ("plan", "apply"):
            validate_privileged(load_workflow(f"terraform-{kind}.yml"), kind)

    def test_reject_automatic_or_untrusted_triggers(self):
        for trigger in ("push", "pull_request", "pull_request_target", "workflow_run"):
            workflow = load_workflow("terraform-apply.yml")
            workflow["on"][trigger] = {}
            with self.assertRaises(ValueError): validate_privileged(workflow, "apply")

    def test_reject_each_removed_dispatch_guard(self):
        for kind in ("plan", "apply"):
            workflow = load_workflow(f"terraform-{kind}.yml")
            terms = workflow["jobs"][kind]["if"].split("&&")
            for index in range(len(terms)):
                changed = deepcopy(workflow)
                changed["jobs"][kind]["if"] = "&&".join(terms[:index] + terms[index + 1:])
                with self.assertRaises(ValueError): validate_privileged(changed, kind)

    def test_reject_guard_bypass(self):
        workflow = load_workflow("terraform-apply.yml")
        workflow["jobs"]["apply"]["if"] += " || true"
        with self.assertRaises(ValueError): validate_privileged(workflow, "apply")

    def test_reject_wrong_environment_and_broad_permissions(self):
        for field, value in (("environment", "unprotected"), ("permissions", {"contents": "write", "id-token": "write"})):
            workflow = load_workflow("terraform-apply.yml")
            workflow["jobs"]["apply"][field] = value
            with self.assertRaises(ValueError): validate_privileged(workflow, "apply")

    def test_reject_unpinned_action_or_public_artifact(self):
        for action in ("azure/login@v2", "actions/upload-artifact@" + "a" * 40):
            workflow = load_workflow("terraform-plan.yml")
            workflow["jobs"]["plan"]["steps"].append({"uses": action})
            with self.assertRaises(ValueError): validate_privileged(workflow, "plan")

    def test_pull_request_security_has_no_cloud_permissions(self):
        workflow = load_workflow("security.yml")
        self.assertEqual(workflow["permissions"], {"contents": "read"})
        self.assertNotIn("pull_request_target", workflow["on"])
        for job in workflow["jobs"].values():
            self.assertNotIn("id-token", job.get("permissions", {}))
            self.assertFalse(any("azure/login" in step.get("uses", "") for step in job.get("steps", [])))


class PrivatePlanTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="synthetic-handoff-")
        self.addCleanup(self.temporary.cleanup)
        directory = Path(self.temporary.name)
        self.plan_path, self.binary_path, self.metadata_path = (directory / name for name in ("plan.json", "plan.bin", "review.json"))
        self.binary_path.write_bytes(b"synthetic-plan-only")
        self.environment = {"GITHUB_SHA": COMMIT, "GITHUB_RUN_ID": "123", "PLAN_RUN_ID": "123",
                            "ARM_SUBSCRIPTION_ID": "synthetic-subscription", "TF_VAR_resource_group_name": "synthetic-lab",
                            "TF_VAR_workspace_name": "synthetic-workspace", "TF_VAR_tags": '{"environment":"test"}',
                            "TF_VAR_daily_quota_gb": "0.1"}
        self.plan = {"terraform_version": "1.15.2", "complete": True, "errored": False,
                     "variables": {key: {"value": value} for key, value in {
                         "subscription_id": "synthetic-subscription", "resource_group_name": "synthetic-lab",
                         "workspace_name": "synthetic-workspace", "tags": {"environment": "test"}, "daily_quota_gb": 0.1}.items()},
                     "planned_values": {"private": CANARY},
                     "resource_changes": [{"mode": "managed", "address": "module.observability.azurerm_log_analytics_workspace.this",
                                           "change": {"actions": ["create"]}}]}

    def inspect(self):
        self.plan_path.write_text(json.dumps(self.plan), encoding="utf-8")
        with patch.dict(os.environ, self.environment):
            return HANDOFF["inspect"](str(self.plan_path), str(self.binary_path))

    def test_accept_scoped_synthetic_plan(self):
        metadata = self.inspect()
        self.assertEqual(metadata["commit"], COMMIT)
        self.assertEqual(metadata["plan_sha256"], hashlib.sha256(self.binary_path.read_bytes()).hexdigest())

    def test_reject_incomplete_or_wrong_version(self):
        for key, bad in (("complete", False), ("errored", True), ("terraform_version", "0.0.0")):
            original = self.plan[key]
            self.plan[key] = bad
            with self.assertRaises(ValueError): self.inspect()
            self.plan[key] = original

    def test_reject_different_subscription_or_scope(self):
        for key in ("subscription_id", "resource_group_name", "workspace_name", "tags", "daily_quota_gb"):
            original = self.plan["variables"][key]["value"]
            self.plan["variables"][key]["value"] = "wrong"
            with self.assertRaises(ValueError): self.inspect()
            self.plan["variables"][key]["value"] = original

    def test_reject_unexpected_managed_resource(self):
        self.plan["resource_changes"][0]["address"] = "azurerm_role_assignment.unapproved"
        with self.assertRaises(ValueError): self.inspect()

    def test_metadata_tampering_and_digest_rejected_without_canary_leak(self):
        metadata = self.inspect()
        for key in ("commit", "root", "plan_run_id", "plan_sha256"):
            changed = deepcopy(metadata)
            changed[key] = "wrong"
            self.metadata_path.write_text(json.dumps(changed), encoding="utf-8")
            result = subprocess.run([sys.executable, str(SCRIPTS / "plan-handoff.py"), "verify", str(self.plan_path),
                                     str(self.binary_path), str(self.metadata_path)], capture_output=True, text=True,
                                    env={**os.environ, **self.environment, "REVIEWED_PLAN_SHA256": metadata["plan_sha256"]})
            self.assertEqual(result.returncode, 1)
            self.assertNotIn(CANARY, result.stdout + result.stderr)

    def test_summary_only_emits_counts_and_digest(self):
        self.inspect()
        command = [sys.executable, str(SCRIPTS / "summarize-plan.py"), str(self.plan_path), str(self.binary_path)]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(set(json.loads(result.stdout)), {"create", "update", "delete", "plan_sha256"})
        self.assertNotIn(CANARY, result.stdout + result.stderr)
        self.plan["complete"] = False
        self.plan_path.write_text(json.dumps(self.plan), encoding="utf-8")
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertNotIn(CANARY, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
