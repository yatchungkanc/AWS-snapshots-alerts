# variables.tf
variable "aws_region" {
  description = "AWS region to deploy resources"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name (e.g., nonprod, prod)"
  type        = string
}

variable "bucket_name" {
  description = "Name of the S3 bucket for snapshot inventory reports"
  type        = string
}

variable "product" {
  description = "Product name (e.g., Opsbank2)"
  type        = string
}

variable "notification_email" {
  description = "Email address for SNS notifications"
  type        = string
}

variable "tags" {
  description = "Common tags for all resources"
  type        = map(string)
  default = {
    Project     = "Snapshot-Inventory"
    ManagedBy   = "Terraform"
  }
}

