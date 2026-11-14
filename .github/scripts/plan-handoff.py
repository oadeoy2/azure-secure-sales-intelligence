"""Create/verify private exact-plan metadata; never emit plan values or IDs."""
import hashlib
import json
import os
from pathlib import Path
import re
import sys


def inspect(plan_path: str, binary_path: str) -> dict:
    plan = json.loads(Path(plan_path).read_text(encoding="utf-8-sig"))
    if plan.get("terraform_version") != "1.15.2" or plan.get("complete") is not True or plan.get("errored"):
        raise ValueError("Unapproved Terraform version or incomplete plan")
    values = {name: item["value"] for name, item in plan["variables"].items()}
    required = {"subscription_id": "ARM_SUBSCRIPTION_ID", "resource_group_name": "TF_VAR_resource_group_name",
                "workspace_name": "TF_VAR_workspace_name", "tags": "TF_VAR_tags", "daily_quota_gb": "TF_VAR_daily_quota_gb"}
    for key, environment in required.items():
        expected = os.environ[environment]
        if key == "tags":
            expected = json.loads(expected)
        elif key == "daily_quota_gb":
            expected = float(expected)
        if values.get(key) != expected:
            raise ValueError("Plan inputs differ from approved environment")
    allowed = {"module.observability.azurerm_log_analytics_workspace.this"}
    for change in plan.get("resource_changes", []):
        if change["mode"] == "managed" and change["address"] not in allowed:
            raise ValueError("Plan includes a resource outside the Phase 1 lab boundary")
    return {"schema_version": 1, "root": "infra/environments/lab", "terraform_version": "1.15.2",
            "commit": os.environ["GITHUB_SHA"], "plan_run_id": os.environ.get("PLAN_RUN_ID", os.environ["GITHUB_RUN_ID"]),
            "plan_sha256": hashlib.sha256(Path(binary_path).read_bytes()).hexdigest()}


def main() -> int:
    try:
        mode, plan_path, binary_path, metadata_path = sys.argv[1:]
        actual = inspect(plan_path, binary_path)
        if not re.fullmatch(r"[0-9a-fA-F]{40}", actual["commit"]) or not actual["plan_run_id"].isdigit():
            raise ValueError("Invalid workflow coordinates")
        if mode == "create":
            Path(metadata_path).write_text(json.dumps(actual, sort_keys=True), encoding="utf-8")
        elif mode == "verify":
            expected = json.loads(Path(metadata_path).read_text(encoding="utf-8-sig"))
            if expected != actual or actual["plan_sha256"].lower() != os.environ["REVIEWED_PLAN_SHA256"].lower():
                raise ValueError("Exact-plan metadata or reviewed digest mismatch")
        else:
            raise ValueError("Unsupported operation")
    except (ValueError, OSError, KeyError, TypeError):
        print("Private exact-plan verification failed; no plan values are exposed.", file=sys.stderr)
        return 1
    print("Private exact-plan verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
