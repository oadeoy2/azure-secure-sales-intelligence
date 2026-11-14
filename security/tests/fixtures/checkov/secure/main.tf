resource "azurerm_storage_account" "fixture" {
  name                     = "syntheticfixtureonly"
  resource_group_name      = "synthetic-fixture-only"
  location                 = "eastus"
  account_tier             = "Standard"
  account_replication_type = "LRS"
  min_tls_version          = "TLS1_2"
}
