"""Hard-failing baseline and isolated scanner canaries; never contacts Azure."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from blob_audit_control import validate_with_mutations
from state_profile_control import validate_with_mutations as validate_profiles
from test_cmk_expiry_preflight import run_frozen_clock_tests

ROOT = Path(__file__).resolve().parents[2]
CHECKOV_VERSION = "3.2.495"
GITLEAKS_VERSION = "8.24.3"


def execute(command: list[str], expected: int = 0) -> str:
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    if result.returncode != expected:
        # Scanner output may contain sensitive context: redact at scanner and
        # avoid echoing full output on failures. Re-run locally for triage.
        raise RuntimeError(f"{Path(command[0]).name} exit {result.returncode}; expected {expected}")
    return result.stdout


def executable(value: str) -> str:
    resolved = str(Path(value).resolve()) if Path(value).is_file() else shutil.which(value)
    if not resolved:
        raise RuntimeError(f"Required scanner unavailable: {value}")
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkov", default=os.environ.get("CHECKOV", "checkov"))
    parser.add_argument("--gitleaks", default=os.environ.get("GITLEAKS", "gitleaks"))
    args = parser.parse_args()
    checkov, gitleaks = executable(args.checkov), executable(args.gitleaks)
    if execute([checkov, "--version"]).strip() != CHECKOV_VERSION:
        raise RuntimeError("Unexpected Checkov version")
    if GITLEAKS_VERSION not in execute([gitleaks, "version"]):
        raise RuntimeError("Unexpected Gitleaks version")
    mutations = validate_with_mutations(ROOT / "infra/bootstrap-state")
    print(f"PASS: modern state Blob audit control; {mutations} broken mutations rejected", flush=True)
    profile_mutations = validate_profiles(ROOT / "infra/bootstrap-state")
    print(f"PASS: independent state profile source guards; {profile_mutations} broken mutations rejected", flush=True)
    expiry_tests = run_frozen_clock_tests()
    print(f"PASS: initial CMK expiry preflight; {expiry_tests} frozen-clock tests", flush=True)
    fixtures = ROOT / "security/tests/fixtures/checkov"
    for kind, status in (("secure", 0), ("insecure", 1)):
        report = json.loads(execute([checkov, "-d", str(fixtures / kind), "--framework", "terraform",
                                     "--check", "CKV_AZURE_44", "--output", "json", "--quiet", "--skip-download"], status))
        findings = report["results"]["failed_checks"]
        summary = report["summary"]
        if summary["parsing_errors"] or summary["resource_count"] != 1:
            raise RuntimeError("Fixture did not parse exactly one resource")
        if kind == "secure" and summary["passed"] != 1:
            raise RuntimeError("Secure fixture did not pass the named TLS check")
        if kind == "insecure" and not any(item["check_id"] == "CKV_AZURE_44" for item in findings):
            raise RuntimeError("Negative fixture did not fail CKV_AZURE_44")
    print("PASS: named Checkov TLS canary and secure counterpart", flush=True)
    execute([gitleaks, "git", str(ROOT), "--redact", "--no-banner"])
    # Scan deployable sources/docs separately from ignored local tooling and
    # private evidence. Git history scan above still includes tracked history.
    with tempfile.TemporaryDirectory(prefix="phase01-secret-scan-") as temporary:
        clean = Path(temporary) / "tracked"
        clean.mkdir()
        tracked = execute(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"])
        for relative in filter(None, tracked.split("\0")):
            source = ROOT / relative
            if source.is_file():
                destination = clean / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
        execute([gitleaks, "dir", str(clean), "--redact", "--no-banner"])
        canary = Path(temporary) / "canary"
        canary.mkdir()
        # Explicit synthetic marker matches a test-only rule, no credential.
        marker = "SYNTHETIC_CANARY_" + "never-a-real-credential"
        (canary / "canary.txt").write_text(marker, encoding="utf-8")
        config = Path(temporary) / "canary.toml"
        config.write_text('[[rules]]\nid = "synthetic-canary"\ndescription = "Generated scanner canary"\nregex = "' + marker + '"\n', encoding="utf-8")
        report = Path(temporary) / "canary.json"
        execute([gitleaks, "dir", str(canary), "--config", str(config), "--redact", "--no-banner",
                 "--report-format", "json", "--report-path", str(report)], 1)
        findings = json.loads(report.read_text(encoding="utf-8"))
        if not any(item["RuleID"] == "synthetic-canary" for item in findings):
            raise RuntimeError("Gitleaks canary did not fail the named rule")
    print("PASS: Gitleaks history, working sources, generated canary", flush=True)
    baseline = json.loads(execute([checkov, "-d", "infra", "--framework", "terraform",
                                   "--output", "json", "--quiet", "--skip-download"]))
    summary = baseline["summary"]
    if summary["parsing_errors"] or summary["passed"] < 1 or summary["failed"]:
        raise RuntimeError("Terraform baseline is empty, unparsed or has failures")
    print(f"PASS: deployable Terraform Checkov baseline ({summary['passed']} passed; "
          f"{summary['skipped']} scoped skips)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
