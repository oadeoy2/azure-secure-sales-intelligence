#!/usr/bin/env bash
set -euo pipefail
umask 077
private_dir="$(mktemp -d "$RUNNER_TEMP/lab-apply.XXXXXXXX")"
trap 'rm -rf -- "$private_dir"' EXIT
[[ "$REVIEWED_COMMIT" == "$GITHUB_SHA" && "$PLAN_RUN_ID" =~ ^[0-9]+$ && "$REVIEWED_PLAN_SHA256" =~ ^[[:xdigit:]]{64}$ && "$CONFIRMATION" == APPLY_REVIEWED_LAB_PLAN ]] || { echo 'Exact-plan coordinates/confirmation rejected.'; exit 1; }
prefix="reviewed-plans/$REVIEWED_COMMIT/$PLAN_RUN_ID"
for filename in lab.tfplan review.json; do
  if ! az storage blob download --account-name "$STATE_STORAGE_ACCOUNT" \
    --container-name lab-state --name "$prefix/$filename" \
    --file "$private_dir/$filename" --auth-mode login --only-show-errors \
    --output none >"$private_dir/download.log" 2>&1; then
    echo 'Private exact-plan download failed; no apply attempted.'
    exit 1
  fi
done
actual_hash="$(sha256sum "$private_dir/lab.tfplan" | cut -d ' ' -f 1)"
[[ "${actual_hash,,}" == "${REVIEWED_PLAN_SHA256,,}" ]] || { echo 'Reviewed binary digest mismatch; no apply attempted.'; exit 1; }
if ! terraform init -input=false -lockfile=readonly -no-color \
  -backend-config="storage_account_name=$STATE_STORAGE_ACCOUNT" \
  -backend-config="container_name=lab-state" \
  -backend-config="key=lab.tfstate" >"$private_dir/init.log" 2>&1; then
  echo 'Approved lab backend initialization failed; no apply attempted.'
  exit 1
fi
if ! terraform show -json "$private_dir/lab.tfplan" >"$private_dir/plan.json" 2>"$private_dir/show.log"; then
  echo 'Private binary decoding failed; no apply attempted.'
  exit 1
fi
python3 "$GITHUB_WORKSPACE/.github/scripts/plan-handoff.py" verify \
  "$private_dir/plan.json" "$private_dir/lab.tfplan" "$private_dir/review.json"
# Apply the saved binary only: no fresh plan, variable override, auto-approve
# flag or bootstrap/administrative root is used.
if ! terraform apply -input=false -lock=true -lock-timeout=60s -no-color \
  "$private_dir/lab.tfplan" >"$private_dir/apply.log" 2>&1; then
  echo 'Reviewed lab apply failed. Do not replan/retry automatically; request private investigation and assess partial state.'
  exit 1
fi
echo 'Reviewed saved lab plan applied. Private blobs retained pending the approved retention/cleanup procedure.'
