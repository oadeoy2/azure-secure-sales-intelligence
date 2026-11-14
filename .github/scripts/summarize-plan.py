"""Print only action counts and binary-plan digest, never plan values or IDs."""
import hashlib
import json
from pathlib import Path
import sys


def main() -> int:
    try:
        plan = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8-sig"))
        if plan.get("errored") or plan.get("complete") is not True:
            raise ValueError("Incomplete or errored plan")
        actions = [change["change"]["actions"] for change in plan.get("resource_changes", [])]
        counts = {action: sum(action in values for values in actions)
                  for action in ("create", "update", "delete")}
        counts["plan_sha256"] = hashlib.sha256(Path(sys.argv[2]).read_bytes()).hexdigest()
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        print("Unable to produce a sanitized complete-plan summary.", file=sys.stderr)
        return 1
    print(json.dumps(counts, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
