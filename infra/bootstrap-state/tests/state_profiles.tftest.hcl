# All runs use an entirely mocked provider and command=plan. No Azure calls,
# backend access, resource creation or Terraform test apply runs are allowed.
mock_provider "azurerm" {
  override_during = plan
  mock_data "azurerm_client_config" {
    defaults = {
      tenant_id = "00000000-0000-0000-0000-000000000001"
      object_id = "00000000-0000-0000-0000-000000000002"
    }
  }
  mock_resource "azurerm_user_assigned_identity" {
    defaults = {
      id           = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-state-test/providers/Microsoft.ManagedIdentity/userAssignedIdentities/state-encryption"
      principal_id = "00000000-0000-0000-0000-000000000003"
    }
  }
  mock_resource "azurerm_key_vault" {
    defaults = { id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-state-test/providers/Microsoft.KeyVault/vaults/state-test-vault" }
  }
  mock_resource "azurerm_key_vault_key" {
    defaults = { versionless_id = "https://state-test-vault.vault.azure.net/keys/terraform-state-encryption" }
  }
  mock_resource "azurerm_storage_account" {
    defaults = { id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-state-test/providers/Microsoft.Storage/storageAccounts/statetestmock" }
  }
  mock_resource "azurerm_log_analytics_workspace" {
    defaults = { id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-state-test/providers/Microsoft.OperationalInsights/workspaces/state-audit" }
  }
}

variables {
  subscription_id      = "00000000-0000-0000-0000-000000000000"
  location             = "eastus2"
  resource_group_name  = "rg-state-test"
  storage_account_name = "statetestmock"
  audit_workspace_name = "state-audit"
  audit_daily_quota_gb = 0.1
  tags                 = { environment = "test" }
}

run "default_lrs_platform_keys" {
  command = plan
  assert {
    condition     = azurerm_storage_account.state.account_replication_type == "LRS" && length(azurerm_storage_account.state.customer_managed_key) == 0 && length(azurerm_storage_account.state.identity) == 0
    error_message = "Defaults must be LRS and platform-managed keys with no attached identity."
  }
  assert {
    condition     = length(data.azurerm_client_config.bootstrap) == 0 && length(azurerm_key_vault.state) == 0 && length(azurerm_key_vault_key.state) == 0 && length(azurerm_user_assigned_identity.state_encryption) == 0 && length(azurerm_role_assignment.bootstrap_crypto) == 0 && length(azurerm_role_assignment.storage_crypto) == 0 && length(azurerm_monitor_diagnostic_setting.state_key_vault) == 0
    error_message = "Default lab plan must have no CMK resources, tenant lookup or crypto role dependencies."
  }
  assert {
    condition     = azurerm_monitor_diagnostic_setting.state_blob.log_analytics_workspace_id == azurerm_log_analytics_workspace.state_audit.id && length(azurerm_storage_container.state) == 2
    error_message = "Auditing and both protected state containers remain mandatory."
  }
}

run "zrs_platform_keys" {
  command = plan
  variables { storage_replication_type = "ZRS" }
  assert {
    condition     = azurerm_storage_account.state.account_replication_type == "ZRS" && length(azurerm_storage_account.state.customer_managed_key) == 0 && length(data.azurerm_client_config.bootstrap) == 0
    error_message = "ZRS must not enable CMK or its tenant dependency."
  }
}

run "gzrs_platform_keys" {
  command = plan
  variables { storage_replication_type = "GZRS" }
  assert {
    condition     = azurerm_storage_account.state.account_replication_type == "GZRS" && length(azurerm_storage_account.state.customer_managed_key) == 0 && length(data.azurerm_client_config.bootstrap) == 0
    error_message = "GZRS must not enable CMK or its tenant dependency."
  }
}

run "lrs_customer_keys" {
  command = plan
  variables {
    enable_cmk                 = true
    key_vault_name             = "state-test-vault"
    bootstrap_admin_ipv4_cidrs = ["192.0.2.10/32"]
    key_expiration_utc         = "2099-01-01T00:00:00Z"
  }
  assert {
    condition     = azurerm_storage_account.state.account_replication_type == "LRS" && length(azurerm_storage_account.state.customer_managed_key) == 1 && length(azurerm_key_vault.state) == 1 && length(azurerm_role_assignment.storage_crypto) == 1 && length(azurerm_monitor_diagnostic_setting.state_key_vault) == 1
    error_message = "LRS and CMK must be independently selectable with crypto dependencies present."
  }
}

run "zrs_customer_keys" {
  command = plan
  variables {
    storage_replication_type   = "ZRS"
    enable_cmk                 = true
    key_vault_name             = "state-test-vault"
    bootstrap_admin_ipv4_cidrs = ["192.0.2.10/32"]
    key_expiration_utc         = "2099-01-01T00:00:00Z"
  }
  assert {
    condition     = azurerm_storage_account.state.account_replication_type == "ZRS" && length(azurerm_storage_account.state.customer_managed_key) == 1
    error_message = "ZRS and CMK must be independently selectable."
  }
}

run "gzrs_customer_keys" {
  command = plan
  variables {
    storage_replication_type   = "GZRS"
    enable_cmk                 = true
    key_vault_name             = "state-test-vault"
    bootstrap_admin_ipv4_cidrs = ["192.0.2.10/32"]
    key_expiration_utc         = "2099-01-01T00:00:00Z"
  }
  assert {
    condition     = azurerm_storage_account.state.account_replication_type == "GZRS" && length(azurerm_storage_account.state.customer_managed_key) == 1
    error_message = "GZRS and CMK must be independently selectable."
  }
}

run "reject_invalid_customer_vault_name" {
  command = plan
  variables {
    enable_cmk                 = true
    key_vault_name             = "invalid--vault"
    bootstrap_admin_ipv4_cidrs = ["192.0.2.10/32"]
    key_expiration_utc         = "2099-01-01T00:00:00Z"
  }
  expect_failures = [var.key_vault_name]
}

run "reject_missing_customer_key_inputs" {
  command = plan
  variables { enable_cmk = true }
  expect_failures = [var.key_vault_name, var.bootstrap_admin_ipv4_cidrs, var.key_expiration_utc]
}

run "reject_broad_admin_cidr" {
  command = plan
  variables {
    enable_cmk                 = true
    key_vault_name             = "state-test-vault"
    bootstrap_admin_ipv4_cidrs = ["0.0.0.0/0"]
    key_expiration_utc         = "2099-01-01T00:00:00Z"
  }
  expect_failures = [var.bootstrap_admin_ipv4_cidrs]
}

# Historical initial-version expiry is valid for ongoing reconciliation after
# rotation; the separate initial-CMK preflight MUST reject it before creation.
run "historical_expiry_does_not_lock_reconciliation" {
  command = plan
  variables {
    enable_cmk                 = true
    key_vault_name             = "state-test-vault"
    bootstrap_admin_ipv4_cidrs = ["192.0.2.10/32"]
    key_expiration_utc         = "2000-01-01T00:00:00Z"
  }
  assert {
    condition     = length(azurerm_storage_account.state.customer_managed_key) == 1
    error_message = "Historical initial-version expiry must not block CMK reconciliation after rotation."
  }
}

run "reject_unsupported_replication" {
  command = plan
  variables { storage_replication_type = "RAGRS" }
  expect_failures = [var.storage_replication_type]
}
