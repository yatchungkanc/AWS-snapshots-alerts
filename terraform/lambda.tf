# lambda.tf
resource "aws_lambda_function" "snapshot_inventory" {
  filename         = data.archive_file.lambda_package.output_path
  function_name    = "snapshot-inventory-${var.environment}"
  role            = aws_iam_role.lambda_role.arn
  handler         = "lambda_function.lambda_handler"
  runtime         = "python3.9"
  timeout         = 300
  memory_size     = 256
  
  # Add source code hash to detect changes
  source_code_hash = data.archive_file.lambda_package.output_base64sha256

  environment {
    variables = {
      S3_BUCKET_NAME = aws_s3_bucket.snapshot_inventory.id
      SNS_TOPIC_ARN  = aws_sns_topic.snapshot_inventory.arn
      ENVIRONMENT    = var.environment
    }
  }

  tags = var.tags
}
