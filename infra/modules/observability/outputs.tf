output "workspace_id" {
  description = "Workspace ARM resource ID for Sentinel and diagnostics."
  value       = azurerm_log_analytics_workspace.this.id
}

output "workspace_customer_id" {
  description = "Workspace customer GUID for query tooling; not an authentication secret."
  value       = azurerm_log_analytics_workspace.this.workspace_id
}

output "workspace_name" {
  description = "Workspace resource name."
  value       = azurerm_log_analytics_workspace.this.name
}
