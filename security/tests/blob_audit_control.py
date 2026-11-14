"""Semantic replacement for legacy Checkov CKV2_AZURE_21, scoped to state.

Validate parsed HCL references, not text presence. No Azure calls are made.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import hcl2


def scalar(value):
    # Checkov's pinned HCL parser returns scalar attributes as singleton lists.
    return value[0] if isinstance(value, list) and len(value) == 1 else value


def resources(directory: Path) -> dict[str, dict]:
    result = {}
    for source in directory.glob("*.tf"):
        with source.open(encoding="utf-8") as handle:
            document = hcl2.load(handle)
        for block in document.get("resource", []):
            for kind, names in block.items():
                for name, attributes in names.items():
                    address = f"{kind}.{name}"
                    if address in result:
                        raise ValueError(f"Duplicate resource: {address}")
                    result[address] = attributes
    return result


def check_state_blob_audit(items: dict[str, dict]) -> None:
    account = items.get("azurerm_storage_account.state", {})
    container = items.get("azurerm_storage_container.state", {})
    diagnostic = items.get("azurerm_monitor_diagnostic_setting.state_blob", {})
    workspace = items.get("azurerm_log_analytics_workspace.state_audit", {})
    for resource in (account, workspace, diagnostic):
        if "count" in resource or "for_each" in resource:
            raise ValueError("Scoped state audit resources must be unconditional singletons")
    if "count" in container or scalar(container.get("for_each")) != "${toset(['lab-state', 'admin-state'])}":
        raise ValueError("Audit replacement covers exactly the two approved state containers")
    expected = {
        "target_resource_id": "${azurerm_storage_account.state.id}/blobServices/default",
        "log_analytics_workspace_id": "${azurerm_log_analytics_workspace.state_audit.id}",
        "log_analytics_destination_type": "Dedicated",
    }
    if any(scalar(diagnostic.get(key)) != value for key, value in expected.items()):
        raise ValueError("State Blob diagnostics must target its Blob service and dedicated audit workspace")
    categories = {scalar(block.get("category")) for block in diagnostic.get("enabled_log", [])}
    if not {"StorageRead", "StorageWrite", "StorageDelete"}.issubset(categories):
        raise ValueError("State Blob diagnostics must enable read/write/delete categories")
    if scalar(container.get("storage_account_id")) != "${azurerm_storage_account.state.id}":
        raise ValueError("State containers must use the audited account")
    if scalar(account.get("shared_access_key_enabled")) is not False:
        raise ValueError("Legacy key-based logging must not enable shared keys")
    if scalar(workspace.get("retention_in_days")) != 90:
        raise ValueError("Audit workspace must retain data for 90 days")
    for attribute in ("local_authentication_enabled", "allow_resource_only_permissions"):
        if scalar(workspace.get(attribute)) is not False:
            raise ValueError("Audit workspace requires explicit Entra/workspace access controls")
    for resource in (workspace, diagnostic):
        if not any(scalar(block.get("prevent_destroy")) is True for block in resource.get("lifecycle", [])):
            raise ValueError("Audit workspace and diagnostics must be protected from incidental destroy")


def validate_with_mutations(directory: Path) -> int:
    actual = resources(directory)
    check_state_blob_audit(actual)
    mutations = []
    for category in ("StorageRead", "StorageWrite", "StorageDelete"):
        changed = deepcopy(actual)
        diagnostic = changed["azurerm_monitor_diagnostic_setting.state_blob"]
        diagnostic["enabled_log"] = [block for block in diagnostic["enabled_log"]
                                     if scalar(block.get("category")) != category]
        mutations.append(changed)
    for attribute in ("target_resource_id", "log_analytics_workspace_id"):
        changed = deepcopy(actual)
        changed["azurerm_monitor_diagnostic_setting.state_blob"][attribute] = ["wrong-reference"]
        mutations.append(changed)
    changed = deepcopy(actual)
    del changed["azurerm_log_analytics_workspace.state_audit"]
    mutations.append(changed)
    changed = deepcopy(actual)
    changed["azurerm_storage_account.state"]["shared_access_key_enabled"] = [True]
    mutations.append(changed)
    for address in ("azurerm_storage_account.state", "azurerm_log_analytics_workspace.state_audit",
                    "azurerm_monitor_diagnostic_setting.state_blob"):
        for attribute, disabled in (("count", [0]), ("for_each", [{}])):
            changed = deepcopy(actual)
            changed[address][attribute] = disabled
            mutations.append(changed)
    changed = deepcopy(actual)
    changed["azurerm_storage_container.state"]["for_each"] = [{}]
    mutations.append(changed)
    for changed in mutations:
        try:
            check_state_blob_audit(changed)
        except ValueError:
            continue
        raise AssertionError("A broken Blob audit configuration passed semantic validation")
    return len(mutations)
