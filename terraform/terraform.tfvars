# terraform.tfvars
aws_region         = "eu-west-1"
environment        = "nonprod"
bucket_name        = "elsevier-tio-875143248408"
notification_email = "c.yatchungkan@elsevier.com"
product            = "Opsbank2"

tags = {
  Product     = "Opsbank2"
  Project     = "Snapshot-Inventory"
  Environment = "nonprod"
  ManagedBy   = "Terraform"
  Owner       = "Chris Yatchungkan"
}
