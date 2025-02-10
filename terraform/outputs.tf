# outputs.tf
output "lambda_function_name" {
  description = "Name of the created Lambda function"
  value       = aws_lambda_function.snapshot_inventory.function_name
}

output "s3_bucket_name" {
  description = "Name of the S3 bucket storing reports"
  value       = aws_s3_bucket.snapshot_inventory.id
}

output "sns_topic_arn" {
  description = "ARN of the SNS topic"
  value       = aws_sns_topic.snapshot_inventory.arn
}
