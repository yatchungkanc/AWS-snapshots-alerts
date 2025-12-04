# s3.tf
resource "aws_s3_bucket" "snapshot_inventory" {
  bucket = "${var.bucket_name}-${var.environment}"
  tags   = var.tags
}

resource "aws_s3_bucket_versioning" "snapshot_inventory" {
  bucket = aws_s3_bucket.snapshot_inventory.id
  versioning_configuration {
    status = "Disabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "snapshot_inventory" {
  bucket = aws_s3_bucket.snapshot_inventory.id

  rule {
    id     = "cleanup_old_reports"
    status = "Enabled"

    expiration {
      days = 30
    }
  }
}

