variable "workspace_name" {
  description = "Log Analytics workspace name."
  type        = string
  validation {
    condition     = can(regex("^[A-Za-z0-9][A-Za-z0-9-]{2,61}[A-Za-z0-9]$", var.workspace_name))
    error_message = "Workspace name must contain 4-63 letters, digits or hyphens and start/end with a letter or digit."
  }
}

variable "resource_group_name" {
  description = "Existing lab resource group name."
  type        = string
}

variable "location" {
  description = "Approved Azure region."
  type        = string
}

variable "tags" {
  description = "Sanitized ownership, phase and lifecycle tags."
  type        = map(string)
}

variable "retention_in_days" {
  description = "Workspace default retention. Table/Sentinel retention must also be reviewed before deployment."
  type        = number
  default     = 30
  validation {
    condition     = var.retention_in_days >= 30 && var.retention_in_days <= 90 && floor(var.retention_in_days) == var.retention_in_days
    error_message = "Lab retention must be an integer between 30 and 90 days."
  }
}

variable "daily_quota_gb" {
  description = "Explicitly approved ingestion quota in GB/day. This is not a hard spending cap and reaching it can reduce visibility."
  type        = number
  validation {
    condition     = var.daily_quota_gb > 0 && var.daily_quota_gb <= 10
    error_message = "Approve a positive lab ingestion quota no greater than 10 GB/day."
  }
}
