"""Run local Terraform checks in an isolated copy; never contact Azure or state.

Provider downloads may need network access. The bootstrap profile suite uses
only mocked-provider plans; no live plan/apply/destroy is run. Security checks
have a separate Security-owned entry point in the validation runbook.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile


def run(command: list[str], cwd: Path) -> bool:
    print(f"CHECK: {' '.join(command)}", flush=True)
    completed = subprocess.run(command, cwd=cwd, check=False)
    print(f"RESULT: exit={completed.returncode}", flush=True)
    return completed.returncode == 0


def run_mock_profiles(executable: str, cwd: Path) -> bool:
    # This isolated directory contains only the reviewed mock suite. Using a
    # test directory avoids Windows filter-path differences; JSON counts reject
    # Terraform's otherwise successful zero-test exit.
    command = [executable, "test", "-test-directory=tests", "-json"]
    print(f"CHECK: {' '.join(command)}", flush=True)
    completed = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)
    try:
        events = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
        summaries = [event["test_summary"] for event in events if event.get("type") == "test_summary"]
        passed = (
            completed.returncode == 0
            and len(summaries) == 1
            and summaries[0].get("status") == "pass"
            and summaries[0].get("passed", 0) >= 11
            and all(summaries[0].get(key) == 0 for key in ("failed", "errored", "skipped"))
        )
    except (ValueError, KeyError, TypeError):
        passed = False
    if not passed:
        print(completed.stdout, end="", flush=True)
        print(completed.stderr, end="", flush=True)
    else:
        print(f"PASS: bootstrap mock profiles ({summaries[0]['passed']} passed)", flush=True)
    print(f"RESULT: exit={completed.returncode}; nonempty mock suite={'PASS' if passed else 'FAIL'}", flush=True)
    return passed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--terraform", default="terraform", help="Terraform executable path")
    parser.add_argument(
        "--bootstrap-only", action="store_true",
        help="Validate bootstrap without copying any lab or other-root source files",
    )
    args = parser.parse_args()
    executable = shutil.which(args.terraform)
    if executable is None:
        parser.error("Terraform executable is unavailable")
    repository = Path(__file__).resolve().parents[1]
    infra = repository / "infra"
    if not run([executable, "fmt", "-check", "-recursive", str(infra)], repository):
        return 1
    sources = sorted(infra.rglob("*.tf"))
    sources = [p for p in sources if ".terraform" not in p.parts]
    if args.bootstrap_only:
        sources = [p for p in sources if p.relative_to(infra).parts[0] == "bootstrap-state"]
    if not sources:
        print("FAIL: no Terraform implementation found")
        return 1
    # Copy source, the reviewed mock profile suite and dependency locks only.
    # Never copy state, credentials,
    # variable values, plans or provider caches into validation workspaces.
    with tempfile.TemporaryDirectory(prefix="phase01-validate-") as temporary:
        isolated = Path(temporary) / "infra"
        locks = [p for p in infra.rglob(".terraform.lock.hcl") if ".terraform" not in p.parts]
        if args.bootstrap_only:
            locks = [p for p in locks if p.relative_to(infra).parts[0] == "bootstrap-state"]
        profile_suite = infra / "bootstrap-state/tests/state_profiles.tftest.hcl"
        if not profile_suite.is_file():
            print("FAIL: bootstrap mock profile suite is missing")
            return 1
        for source in sources + locks + [profile_suite]:
            destination = isolated / source.relative_to(infra)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        roots = sorted({p.parent.relative_to(infra) for p in sources})
        pinned_lock = isolated / "bootstrap-state/.terraform.lock.hcl"
        if not pinned_lock.is_file():
            print("FAIL: pinned bootstrap provider lock is missing")
            return 1
        results = []
        for root in roots:
            directory = isolated / root
            # Standalone module validation uses the same pinned provider as the
            # consuming roots, rather than resolving a newer release silently.
            if not (directory / ".terraform.lock.hcl").is_file():
                shutil.copy2(pinned_lock, directory / ".terraform.lock.hcl")
            print(f"ROOT: infra/{root.as_posix()}", flush=True)
            initialized = run([executable, "init", "-backend=false", "-input=false", "-lockfile=readonly", "-no-color"], directory)
            validated = initialized and run([executable, "validate", "-no-color"], directory)
            if validated and root == Path("bootstrap-state"):
                validated = run_mock_profiles(executable, directory)
            results.append(validated)
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
