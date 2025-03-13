# iam.tf
resource "aws_iam_role" "lambda_role" {
  name = "snapshot_inventory_lambda_role_${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = var.tags
}

resource "aws_iam_role_policy" "lambda_policy" {
  name = "snapshot_inventory_lambda_policy_${var.environment}"
  role = aws_iam_role.lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          # EC2 Permissions
          "ec2:DescribeRegions",
          "ec2:DescribeSnapshots",
          "ec2:DescribeVolumes",
          
          # RDS Permissions
          "rds:DescribeDBSnapshots",
          "rds:DescribeDBInstances",
          "rds:DescribeDBClusters",
          "rds:DescribeDBClusterSnapshots",
          
          # AWS Backup Permissions
          "backup:ListBackupJobs",
          "backup:DescribeBackupJob",
          "backup:ListBackupVaults",
          "backup:ListRecoveryPointsByBackupVault",
          
          # S3 and SNS Permissions
          "s3:PutObject",
          "sns:Publish",
          
          # CloudWatch Logs Permissions
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "*"
      }
    ]
  })
}

