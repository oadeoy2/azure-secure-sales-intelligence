terraform {
  required_version = ">= 1.9, < 2.0"
  required_providers {
    azurerm = { source = "hashicorp/azurerm", version = "~> 4.0" }
  }
  # First approved bootstrap uses protected local state. See README before migration.
}

provider "azurerm" {
  subscription_id                 = var.subscription_id
  resource_provider_registrations = "none"
  storage_use_azuread             = true
  features {
    resource_group { prevent_deletion_if_contains_resources = true }
    key_vault {
      purge_soft_delete_on_destroy       = false
      purge_soft_deleted_keys_on_destroy = false
      recover_soft_deleted_key_vaults    = true
      recover_soft_deleted_keys          = true
    }
  }
}

variable "subscription_id" { type = string }
variable "location" { type = string }
variable "resource_group_name" { type = string }
variable "storage_account_name" {
  type = string
  validation {
    condition     = can(regex("^[a-z0-9]{3,24}$", var.storage_account_name))
    error_message = "Use 3-24 lowercase letters and digits."
  }
}
variable "tags" { type = map(string) }
variable "storage_replication_type" {
  description = "Replication choice is independent of encryption-key custody."
  type        = string
  default     = "LRS"
  validation {
    condition     = contains(["LRS", "ZRS", "GZRS"], var.storage_replication_type)
    error_message = "Choose LRS, ZRS or GZRS."
  }
}
variable "enable_cmk" {
  description = "Opt-in customer-managed key custody; false uses Azure platform-managed encryption."
  type        = bool
  default     = false
}

resource "azurerm_resource_group" "state" {
  name     = var.resource_group_name
  location = var.location
  tags     = var.tags
  lifecycle { prevent_destroy = true }
}

resource "azurerm_storage_account" "state" {
  #checkov:skip=CKV_AZURE_206:Approved lab default LRS; independent validated LRS/ZRS/GZRS profiles and tradeoffs in security/SCANNER_EXCEPTIONS.md.
  #checkov:skip=CKV_AZURE_59:Approved authenticated public endpoint for GitHub-hosted lab runners; security/SCANNER_EXCEPTIONS.md.
  #checkov:skip=CKV2_AZURE_33:Private endpoints excluded from approved initial lab; security/SCANNER_EXCEPTIONS.md.
  #checkov:skip=CKV_AZURE_33:No Queue workload; queue telemetry adds unrelated scope; security/SCANNER_EXCEPTIONS.md.
  name                             = var.storage_account_name
  resource_group_name              = azurerm_resource_group.state.name
  location                         = azurerm_resource_group.state.location
  account_tier                     = "Standard"
  account_replication_type         = var.storage_replication_type
  account_kind                     = "StorageV2"
  min_tls_version                  = "TLS1_2"
  https_traffic_only_enabled       = true
  shared_access_key_enabled        = false
  allow_nested_items_to_be_public  = false
  public_network_access_enabled    = true
  default_to_oauth_authentication  = true
  cross_tenant_replication_enabled = false
  local_user_enabled               = false
  tags                             = var.tags

  dynamic "identity" {
    for_each = var.enable_cmk ? [1] : []
    content {
      type         = "UserAssigned"
      identity_ids = [azurerm_user_assigned_identity.state_encryption[0].id]
    }
  }
  dynamic "customer_managed_key" {
    for_each = var.enable_cmk ? [1] : []
    content {
      key_vault_key_id          = azurerm_key_vault_key.state[0].versionless_id
      user_assigned_identity_id = azurerm_user_assigned_identity.state_encryption[0].id
    }
  }

  # Approved GitHub-hosted-runner lab boundary: authenticated public endpoint.
  # No misleading dynamic-runner IP allowlist or private networking is created.
  blob_properties {
    versioning_enabled = true
    delete_retention_policy { days = 30 }
    container_delete_retention_policy { days = 30 }
  }
  lifecycle {
    prevent_destroy = true
  }
  # Inline encryption is the sole configuration owner; no ignored CMK drift.
  depends_on = [azurerm_role_assignment.storage_crypto]
}

resource "azurerm_storage_container" "state" {
  #checkov:skip=CKV2_AZURE_21:Modern Blob diagnostics enforced by security/tests/blob_audit_control.py; legacy checker requires shared keys; security/SCANNER_EXCEPTIONS.md.
  for_each              = toset(["lab-state", "admin-state"])
  name                  = each.value
  storage_account_id    = azurerm_storage_account.state.id
  container_access_type = "private"
  lifecycle { prevent_destroy = true }
}

output "storage_account_name" { value = azurerm_storage_account.state.name }
output "lab_state_container_id" { value = azurerm_storage_container.state["lab-state"].id }
output "admin_state_container_id" { value = azurerm_storage_container.state["admin-state"].id }
