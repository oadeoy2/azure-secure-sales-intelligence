#!/usr/bin/env bash
# Runs only from the protected, manually dispatched lab-plan job.
set -euo pipefail
umask 077
private_dir="$(mktemp -d "$RUNNER_TEMP/lab-plan.XXXXXXXX")"
trap 'rm -rf -- "$private_dir"' EXIT

if ! terraform init -input=false -lockfile=readonly -no-color \
  -backend-config="storage_account_name=$STATE_STORAGE_ACCOUNT" \
  -backend-config="container_name=lab-state" \
  -backend-config="key=lab.tfstate" >"$private_dir/init.log" 2>&1; then
  echo 'Backend initialization failed. No raw backend log is exposed; arrange a separately approved private diagnostic session.'
  exit 1
fi

set +e
terraform plan -input=false -lock=true -lock-timeout=60s -detailed-exitcode \
  -no-color -out="$private_dir/lab.tfplan" >"$private_dir/plan.log" 2>&1
plan_exit=$?
set -e
if [[ "$plan_exit" != 0 && "$plan_exit" != 2 ]]; then
  echo 'Terraform plan failed. No raw plan log is exposed; arrange a separately approved private diagnostic session.'
  exit 1
fi
if ! terraform show -json "$private_dir/lab.tfplan" >"$private_dir/plan.json" 2>"$private_dir/show.log"; then
  echo 'Plan decoding failed; no plan output is exposed.'
  exit 1
fi
python3 "$GITHUB_WORKSPACE/.github/scripts/summarize-plan.py" \
  "$private_dir/plan.json" "$private_dir/lab.tfplan"
python3 "$GITHUB_WORKSPACE/.github/scripts/plan-handoff.py" create \
  "$private_dir/plan.json" "$private_dir/lab.tfplan" "$private_dir/review.json"
prefix="reviewed-plans/$GITHUB_SHA/$GITHUB_RUN_ID"
for filename in lab.tfplan review.json; do
  if ! az storage blob upload --account-name "$STATE_STORAGE_ACCOUNT" \
    --container-name lab-state --name "$prefix/$filename" \
    --file "$private_dir/$filename" --auth-mode login --overwrite false \
    --only-show-errors --output none >"$private_dir/upload.log" 2>&1; then
    echo 'Private plan upload failed. Inspect the private prefix; do not overwrite or apply a partial handoff.'
    exit 1
  fi
done
echo "Private handoff stored for commit $GITHUB_SHA and plan run $GITHUB_RUN_ID."
echo 'Review the exact private binary before separately approving apply. Private blobs require an approved retention/cleanup procedure.'
