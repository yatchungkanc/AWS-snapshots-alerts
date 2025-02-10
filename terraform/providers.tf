# providers.tf
provider "aws" {
  region = var.aws_region
}

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 4.0"
    }
  }
  required_version = ">= 1.0.0"

  # backend "s3" {
  #   # Configure your backend settings here or via -backend-config
  # }
}

