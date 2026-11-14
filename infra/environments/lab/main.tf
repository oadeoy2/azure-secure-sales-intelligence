terraform {
  required_version = ">= 1.9, < 2.0"
  required_providers {
    azurerm = { source = "hashicorp/azurerm", version = "~> 4.0" }
  }
  backend "azurerm" {
    use_azuread_auth = true
    use_oidc         = true
  }
}

provider "azurerm" {
  subscription_id                 = var.subscription_id
  resource_provider_registrations = "none"
  storage_use_azuread             = true
  features {
    resource_group { prevent_deletion_if_contains_resources = true }
  }
}

variable "subscription_id" { type = string }
variable "resource_group_name" { type = string }
variable "workspace_name" { type = string }
variable "tags" { type = map(string) }
variable "daily_quota_gb" { type = number }
variable "retention_in_days" {
  type    = number
  default = 30
}

# The privileged bootstrap owns the resource group and IAM, outside lab state.
data "azurerm_resource_group" "lab" { name = var.resource_group_name }

module "observability" {
  source              = "../../modules/observability"
  resource_group_name = data.azurerm_resource_group.lab.name
  location            = data.azurerm_resource_group.lab.location
  workspace_name      = var.workspace_name
  tags                = var.tags
  daily_quota_gb      = var.daily_quota_gb
  retention_in_days   = var.retention_in_days
}

output "resource_group_id" { value = data.azurerm_resource_group.lab.id }
output "log_analytics_workspace_id" { value = module.observability.workspace_id }
output "workspace_customer_id" { value = module.observability.workspace_customer_id }
