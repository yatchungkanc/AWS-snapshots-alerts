# sns.tf
resource "aws_sns_topic" "snapshot_inventory" {
  name = "snapshot-inventory-${var.environment}"
  tags = var.tags
}

resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.snapshot_inventory.arn
  protocol  = "email"
  endpoint  = var.notification_email
}

