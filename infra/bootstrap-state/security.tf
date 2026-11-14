data "azurerm_client_config" "bootstrap" {
  count = var.enable_cmk ? 1 : 0
}

variable "key_vault_name" {
  type    = string
  default = null
  validation {
    condition     = !var.enable_cmk || try(can(regex("^[a-zA-Z][a-zA-Z0-9-]{1,22}[a-zA-Z0-9]$", var.key_vault_name)) && !strcontains(var.key_vault_name, "--"), false)
    error_message = "Supply a globally unique 3-24 character Key Vault name without consecutive hyphens."
  }
}
variable "bootstrap_admin_ipv4_cidrs" {
  description = "Approved fixed public egress CIDRs of the human bootstrap administrator; never broad GitHub runner ranges."
  type        = list(string)
  default     = null
  validation {
    condition = !var.enable_cmk || try(length(var.bootstrap_admin_ipv4_cidrs) > 0 && alltrue([
      for cidr in var.bootstrap_admin_ipv4_cidrs : can(cidrnetmask(cidr)) && try(tonumber(split("/", cidr)[1]) >= 24, false)
    ]), false)
    error_message = "Supply at least one approved IPv4 CIDR with /24 or narrower prefix."
  }
}
variable "key_expiration_utc" {
  description = "Explicit initial key expiry RFC3339 timestamp, selected during deployment approval; no moving timestamp() defaults."
  type        = string
  default     = null
  validation {
    condition     = !var.enable_cmk || can(formatdate("YYYY-MM-DD", var.key_expiration_utc))
    error_message = "Supply a valid RFC3339 timestamp for initial key expiry."
  }
}
variable "audit_workspace_name" { type = string }
variable "audit_daily_quota_gb" {
  description = "Approved audit ingestion guardrail, not a hard cost limit."
  type        = number
  validation {
    condition     = var.audit_daily_quota_gb > 0 && var.audit_daily_quota_gb <= 10
    error_message = "Supply an explicit positive audit quota no greater than 10 GB/day."
  }
}

resource "azurerm_user_assigned_identity" "state_encryption" {
  count               = var.enable_cmk ? 1 : 0
  name                = "state-storage-encryption"
  resource_group_name = azurerm_resource_group.state.name
  location            = azurerm_resource_group.state.location
  tags                = var.tags
  lifecycle { prevent_destroy = true }
}

resource "azurerm_key_vault" "state" {
  count = var.enable_cmk ? 1 : 0
  #checkov:skip=CKV_AZURE_189:Approved public administrative endpoint with default-deny firewall; security/SCANNER_EXCEPTIONS.md.
  #checkov:skip=CKV2_AZURE_32:Approved initial topology excludes private infrastructure; security/SCANNER_EXCEPTIONS.md.
  name                          = var.key_vault_name
  resource_group_name           = azurerm_resource_group.state.name
  location                      = azurerm_resource_group.state.location
  tenant_id                     = data.azurerm_client_config.bootstrap[0].tenant_id
  sku_name                      = "standard"
  rbac_authorization_enabled    = true
  purge_protection_enabled      = true
  soft_delete_retention_days    = 90
  public_network_access_enabled = true
  tags                          = var.tags
  network_acls {
    default_action = "Deny"
    bypass         = "AzureServices"
    ip_rules       = var.bootstrap_admin_ipv4_cidrs
  }
  lifecycle { prevent_destroy = true }
}

# This root is human-administered. The executing administrator requires scoped
# role-assignment authority; the grant deliberately does not target routine CI.
resource "azurerm_role_assignment" "bootstrap_crypto" {
  count                = var.enable_cmk ? 1 : 0
  scope                = azurerm_key_vault.state[0].id
  role_definition_name = "Key Vault Crypto Officer"
  principal_id         = data.azurerm_client_config.bootstrap[0].object_id
}

resource "azurerm_key_vault_key" "state" {
  count = var.enable_cmk ? 1 : 0
  #checkov:skip=CKV_AZURE_112:Standard software RSA custody is explicit lab decision; HSM not claimed; security/SCANNER_EXCEPTIONS.md.
  name            = "terraform-state-encryption"
  key_vault_id    = azurerm_key_vault.state[0].id
  key_type        = "RSA"
  key_size        = 2048
  key_opts        = ["wrapKey", "unwrapKey"]
  expiration_date = var.key_expiration_utc
  tags            = var.tags
  rotation_policy {
    automatic { time_before_expiry = "P30D" }
    expire_after         = "P90D"
    notify_before_expiry = "P29D"
  }
  depends_on = [azurerm_role_assignment.bootstrap_crypto]
  lifecycle {
    prevent_destroy = true
  }
}

resource "azurerm_role_assignment" "storage_crypto" {
  count                = var.enable_cmk ? 1 : 0
  scope                = azurerm_key_vault.state[0].id
  role_definition_name = "Key Vault Crypto Service Encryption User"
  principal_id         = azurerm_user_assigned_identity.state_encryption[0].principal_id
}

# Separate from disposable lab telemetry and owned exclusively by this admin root.
resource "azurerm_log_analytics_workspace" "state_audit" {
  name                            = var.audit_workspace_name
  resource_group_name             = azurerm_resource_group.state.name
  location                        = azurerm_resource_group.state.location
  sku                             = "PerGB2018"
  retention_in_days               = 90
  daily_quota_gb                  = var.audit_daily_quota_gb
  local_authentication_enabled    = false
  allow_resource_only_permissions = false
  tags                            = var.tags
  lifecycle { prevent_destroy = true }
}

resource "azurerm_monitor_diagnostic_setting" "state_blob" {
  name                           = "state-blob-audit"
  target_resource_id             = "${azurerm_storage_account.state.id}/blobServices/default"
  log_analytics_workspace_id     = azurerm_log_analytics_workspace.state_audit.id
  log_analytics_destination_type = "Dedicated"
  enabled_log { category = "StorageRead" }
  enabled_log { category = "StorageWrite" }
  enabled_log { category = "StorageDelete" }
  lifecycle { prevent_destroy = true }
}

resource "azurerm_monitor_diagnostic_setting" "state_key_vault" {
  count                          = var.enable_cmk ? 1 : 0
  name                           = "state-key-audit"
  target_resource_id             = azurerm_key_vault.state[0].id
  log_analytics_workspace_id     = azurerm_log_analytics_workspace.state_audit.id
  log_analytics_destination_type = "Dedicated"
  enabled_log { category_group = "allLogs" }
  lifecycle { prevent_destroy = true }
}

output "state_key_vault_id" { value = try(azurerm_key_vault.state[0].id, null) }
output "state_audit_workspace_id" { value = azurerm_log_analytics_workspace.state_audit.id }
