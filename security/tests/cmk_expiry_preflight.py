"""Offline initial-CMK expiry check, never a recurring Terraform plan gate.

Run only before initial key creation or initial CMK enablement, using the same
reviewed concrete variable file that will be supplied to Terraform. This script
does not infer whether a deployment is new and makes no Azure calls.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path


def check_initial_expiry(enable_cmk: bool, expiry: str | None, now: datetime | None = None) -> None:
    if not enable_cmk:
        return
    if not isinstance(expiry, str):
        raise ValueError("CMK initial expiry must be an explicit UTC timestamp")
    try:
        parsed = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("CMK initial expiry must be a valid UTC timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError("CMK initial expiry must include UTC timezone information")
    observed = now if now is not None else datetime.now(timezone.utc)
    if observed.tzinfo is None:
        raise ValueError("The preflight clock must be timezone-aware")
    if parsed <= observed + timedelta(days=30):
        raise ValueError("Initial CMK expiry must be more than 30 days in the future")


def check_variable_file(path: Path, now: datetime | None = None) -> None:
    # Reject competing activation/expiry settings instead of pretending to
    # reproduce Terraform's complete variable-precedence model.
    if any(name in os.environ for name in ("TF_VAR_enable_cmk", "TF_VAR_key_expiration_utc")):
        raise ValueError("Remove competing CMK TF_VAR overrides before checking the reviewed variable file")
    with path.open(encoding="utf-8-sig") as handle:
        if path.name.endswith(".json"):
            values = json.load(handle)
        else:
            try:
                import hcl2
            except ImportError as error:
                raise ValueError("HCL input requires the existing Checkov Python environment; JSON tfvars needs only Python") from error
            values = hcl2.load(handle)
            values = {name: value[0] if isinstance(value, list) and len(value) == 1 else value
                      for name, value in values.items()}
    if not isinstance(values, dict) or values.get("enable_cmk") is not True:
        raise ValueError("The reviewed variable file must explicitly set enable_cmk=true")
    check_initial_expiry(True, values.get("key_expiration_utc"), now)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enable-cmk", action="store_true", help="Explicit initial CMK creation/enablement check")
    parser.add_argument("--var-file", type=Path, help="Same reviewed .tfvars or .tfvars.json file supplied to Terraform")
    args = parser.parse_args()
    if not args.enable_cmk:
        print("SKIP: initial CMK check was not requested; no CMK input is required")
        return 0
    if args.var_file is None:
        parser.error("--enable-cmk requires the reviewed --var-file")
    try:
        check_variable_file(args.var_file)
    except (OSError, ValueError) as error:
        parser.exit(1, f"FAIL: {error}\n")
    print("PASS: initial CMK expiry in the reviewed variable file is more than 30 days away")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
