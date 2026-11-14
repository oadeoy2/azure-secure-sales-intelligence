"""Guard scoped lab-profile scanner exceptions using parsed Terraform HCL.

Terraform mock plans independently exercise expression evaluation and resource
counts. These source guards ensure exceptions cannot silently expand the lab
profile, disable CMK safeguards or hide encryption drift.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import hcl2

from blob_audit_control import resources, scalar


def variables(directory: Path) -> dict[str, dict]:
    result = {}
    for source in directory.glob("*.tf"):
        with source.open(encoding="utf-8") as handle:
            document = hcl2.load(handle)
        for block in document.get("variable", []):
            result.update(block)
    return result


def check_profiles(items: dict[str, dict], inputs: dict[str, dict]) -> None:
    replication = inputs.get("storage_replication_type", {})
    cmk = inputs.get("enable_cmk", {})
    if scalar(replication.get("default")) != "LRS" or scalar(cmk.get("default")) is not False:
        raise ValueError("The approved lab defaults are LRS and Microsoft-managed encryption")
    if scalar(cmk.get("type")) != "${bool}":
        raise ValueError("CMK activation must remain an explicit boolean")
    enum = "${contains(['LRS', 'ZRS', 'GZRS'],var.storage_replication_type)}"
    if not any(scalar(block.get("condition")) == enum for block in replication.get("validation", [])):
        raise ValueError("Replication choices must remain limited to LRS/ZRS/GZRS")
    account = items.get("azurerm_storage_account.state", {})
    if scalar(account.get("account_replication_type")) != "${var.storage_replication_type}":
        raise ValueError("Replication must remain independent from the CMK toggle")
    for lifecycle in account.get("lifecycle", []):
        if "ignore_changes" in lifecycle:
            raise ValueError("State encryption must not be hidden by ignore_changes")
    if "customer_managed_key" in account or "identity" in account:
        raise ValueError("Default profile must not require an unconditional CMK or encryption identity")
    if "azurerm_storage_account_customer_managed_key.state" in items:
        raise ValueError("The inline CMK block must be the sole encryption owner")
    expected = {"identity", "customer_managed_key"}
    dynamic = {}
    for block in account.get("dynamic", []):
        dynamic.update(block)
    if not expected.issubset(dynamic):
        raise ValueError("CMK-enabled profile requires both identity and encryption blocks")
    for name in expected:
        expression = scalar(dynamic[name].get("for_each"))
        if expression != "${var.enable_cmk ? [1] : []}":
            raise ValueError("Encryption and identity must be controlled only by enable_cmk")
    content = dynamic["customer_managed_key"].get("content", [{}])[0]
    if scalar(content.get("key_vault_key_id")) != "${azurerm_key_vault_key.state[0].versionless_id}":
        raise ValueError("CMK profile must reference the managed rotatable vault key")
    if scalar(content.get("user_assigned_identity_id")) != "${azurerm_user_assigned_identity.state_encryption[0].id}":
        raise ValueError("CMK profile must use its scoped encryption identity")
    optional = ("azurerm_user_assigned_identity.state_encryption", "azurerm_key_vault.state",
                "azurerm_role_assignment.bootstrap_crypto", "azurerm_key_vault_key.state",
                "azurerm_role_assignment.storage_crypto", "azurerm_monitor_diagnostic_setting.state_key_vault")
    for address in optional:
        if scalar(items.get(address, {}).get("count")) != "${var.enable_cmk ? 1 : 0}":
            raise ValueError(f"CMK dependency must be explicitly optional: {address}")
    for name in ("key_vault_name", "bootstrap_admin_ipv4_cidrs", "key_expiration_utc"):
        if name not in inputs or "default" not in inputs[name] or scalar(inputs[name]["default"]) is not None:
            raise ValueError("CMK-only inputs must be optional in the default profile")
    for lifecycle in items["azurerm_key_vault_key.state"].get("lifecycle", []):
        for precondition in lifecycle.get("precondition", []):
            expression = str(scalar(precondition.get("condition")))
            if "plantimestamp(" in expression or "timestamp(" in expression:
                raise ValueError("Initial expiry must not become a moving-clock Terraform plan gate")


def validate_with_mutations(directory: Path) -> int:
    actual, inputs = resources(directory), variables(directory)
    check_profiles(actual, inputs)
    mutations = []
    changed = deepcopy(inputs)
    changed["enable_cmk"]["default"] = [True]
    mutations.append((actual, changed))
    changed = deepcopy(inputs)
    changed["storage_replication_type"]["default"] = ["GZRS"]
    mutations.append((actual, changed))
    for address in ("azurerm_key_vault.state", "azurerm_key_vault_key.state",
                    "azurerm_user_assigned_identity.state_encryption"):
        changed = deepcopy(actual)
        changed[address]["count"] = [1]
        mutations.append((changed, inputs))
    changed = deepcopy(actual)
    changed["azurerm_storage_account.state"]["lifecycle"][0]["ignore_changes"] = [["customer_managed_key"]]
    mutations.append((changed, inputs))
    changed = deepcopy(actual)
    changed["azurerm_key_vault_key.state"]["lifecycle"][0]["precondition"] = [
        {"condition": ["${timecmp(var.key_expiration_utc,plantimestamp()) > 0}"]}]
    mutations.append((changed, inputs))
    changed = deepcopy(inputs)
    del changed["key_vault_name"]["default"]
    mutations.append((actual, changed))
    changed = deepcopy(inputs)
    changed["storage_replication_type"]["validation"] = []
    mutations.append((actual, changed))
    changed = deepcopy(actual)
    for block in changed["azurerm_storage_account.state"]["dynamic"]:
        if "identity" in block:
            block["identity"]["for_each"] = [[]]
    mutations.append((changed, inputs))
    changed = deepcopy(actual)
    for block in changed["azurerm_storage_account.state"]["dynamic"]:
        if "customer_managed_key" in block:
            block["customer_managed_key"]["content"][0]["key_vault_key_id"] = ["wrong-key"]
    mutations.append((changed, inputs))
    changed = deepcopy(actual)
    changed["azurerm_storage_account.state"]["account_replication_type"] = ["${var.enable_cmk ? 'GZRS' : 'LRS'}"]
    mutations.append((changed, inputs))
    for changed_items, changed_inputs in mutations:
        try:
            check_profiles(changed_items, changed_inputs)
        except ValueError:
            continue
        raise AssertionError("A broken state profile passed semantic validation")
    return len(mutations)
