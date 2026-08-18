terraform {
  required_version = "= 1.13.3"

  required_providers {
    azapi = {
      source  = "azure/azapi"
      version = "~> 2.6"
    }
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.45"
    }
    azuread = {
      source  = "hashicorp/azuread"
      version = "~> 3.5"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.7"
    }
  }
}

provider "azurerm" {
  subscription_id = var.subscription_id

  resource_provider_registrations = "none"

  features {}
}

provider "azapi" {
  subscription_id = var.subscription_id
}

provider "azuread" {}
