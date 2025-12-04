# AWS Snapshot Inventory Generator

This project automates the process of generating and reporting AWS snapshot inventories across multiple services and regions.

The AWS Snapshot Inventory Generator is a serverless application that creates comprehensive reports of snapshots from various AWS services, including EC2 EBS snapshots, RDS snapshots, and EFS backups via AWS Backup. It calculates snapshot ages, categorizes them by age groups, and generates both detailed CSV reports and summary notifications. Additionally, it identifies and reports on unattached EBS volumes to help with cost optimization.

The application is built using AWS Lambda and is deployed using Terraform. It leverages several AWS services, including S3 for report storage, SNS for notifications, and EventBridge for daily scheduling. The solution scans all AWS regions and is designed to be easily deployable and configurable across different environments.

## Repository Structure

```
.
├── docs/
│   ├── infra.dot
│   └── infra.svg
├── src/
│   └── lambda_function.py
├── terraform/
│   ├── data.tf
│   ├── eventbridge.tf
│   ├── iam.tf
│   ├── lambda.tf
│   ├── outputs.tf
│   ├── providers.tf
│   ├── s3.tf
│   ├── sns.tf
│   ├── terraform.tfvars
│   └── variables.tf
├── .gitignore
├── cleanup.sh
├── deploy.sh
├── README.md
├── requirements-lambda.txt
├── sample-output.png
└── test_snapshot_inventory.py
```

### Key Files:
- `src/lambda_function.py`: The main Lambda function that generates multi-region snapshot inventory and unattached volume reports.
- `deploy.sh`: Enhanced deployment script with support for full deployment, Lambda-only updates, rolling deployments, and rollback capabilities.
- `cleanup.sh`: Comprehensive cleanup script with S3 bucket emptying, resource removal, and retry logic.
- `terraform/`: Directory containing Terraform configuration files for infrastructure provisioning.
- `terraform/terraform.tfvars`: Configuration file with actual deployment values.
- `test_snapshot_inventory.py`: Comprehensive test suite for verifying deployment, configuration, and functionality.
- `docs/`: Infrastructure diagrams and documentation.
- `sample-output.png`: Example of the generated report output.

## Usage Instructions

### Installation

Prerequisites:
- AWS CLI (version 2.0 or later)
- Terraform (version 1.0 or later)
- Python 3.9 or later
- jq (for JSON processing in cleanup scripts)
- go-aws-sso (optional, for AWS Single Sign-On authentication)

Steps:
1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd AWS-snapshots-alerts
   ```

2. Install Python dependencies (optional for local testing):
   ```bash
   pip install -r requirements-lambda.txt
   ```

### Deployment

Before deploying the application, you must configure the required variables in `terraform/terraform.tfvars`:

```hcl
aws_region         = "eu-west-1"                    # AWS region for deployment
environment        = "nonprod"                      # Environment name (nonprod or prod)
bucket_name        = "your-unique-bucket-name"      # Unique S3 bucket name
notification_email = "admin@example.com"            # Email for receiving notifications
product            = "YourProduct"                  # Product name for resource tagging

tags = {
  Product     = "YourProduct"
  Project     = "Snapshot-Inventory"
  Environment = "nonprod"
  ManagedBy   = "Terraform"
  Owner       = "Your Name"
}
```

To deploy the application:

1. Configure your AWS credentials:
   ```bash
   aws configure
   ```
   
   If using AWS SSO, use go-aws-sso to authenticate:
   ```bash
   go-aws-sso login
   ```

2. Run the deployment script:
   ```bash
   ./deploy.sh -e nonprod -f  # Full deployment to nonprod environment
   ./deploy.sh -e nonprod -l  # Update Lambda only in nonprod environment
   ```

   Available options:
   - `-e, --environment`: Specify the environment (nonprod or prod)
   - `-f, --full`: Perform a full deployment
   - `-l, --lambda-only`: Update only the Lambda function code
   - `-r, --rolling`: Perform rolling deployment with canary testing
   - `-w, --weight`: Traffic weight for new version (default: 10%)
   - `--promote`: Promote canary to full production
   - `--rollback`: Rollback to previous version
   - `-h, --help`: Show help message

### Configuration

The application can be configured through environment variables and Terraform variables. Key configurations include:

- `S3_BUCKET_NAME`: Name of the S3 bucket for storing reports
- `SNS_TOPIC_ARN`: ARN of the SNS topic for notifications
- `ENVIRONMENT`: Environment name (nonprod/prod)
- `EMAIL_SUBJECT`: Custom email subject (optional)

The Lambda function is configured with:
- Runtime: Python 3.9
- Timeout: 300 seconds (5 minutes)
- Memory: 256 MB
- Scheduled execution: Daily via EventBridge

These can be modified in the respective Terraform files.

### Testing

To run the deployment verification tests:

```bash
# Set environment variables for testing
export LAMBDA_FUNCTION_NAME="snapshot-inventory-nonprod"
export S3_BUCKET_NAME="your-bucket-name"
export SNS_TOPIC_NAME="your-sns-topic-arn"

# Run tests
python -m unittest test_snapshot_inventory.py
```

The test suite includes:
- Lambda function configuration validation
- S3 bucket configuration and encryption verification
- IAM role and permissions testing
- SNS topic configuration validation
- Lambda function invocation testing
- Deployment rollback capability verification

### Cleanup

To remove all deployed resources:

```bash
./cleanup.sh -e nonprod -f  # Force cleanup without confirmation
./cleanup.sh -e nonprod     # Interactive cleanup with confirmation
./cleanup.sh --s3-only      # Clean only S3 bucket contents
```

Options:
- `-e, --environment`: Specify environment (nonprod or prod)
- `-f, --force`: Force cleanup without confirmation
- `--s3-only`: Clean up only S3 contents
- `-h, --help`: Show help message

### Troubleshooting

Common issues:

1. **Deployment Failure**
   - Error: "NoSuchBucket: The specified bucket does not exist"
   - Solution: Ensure the S3 bucket name is globally unique and correctly specified in `terraform.tfvars`.

2. **Lambda Function Timeout**
   - Error: "Task timed out after 300 seconds"
   - Solution: For accounts with many snapshots across regions, consider increasing timeout in `terraform/lambda.tf` or optimizing the scanning logic.

3. **Insufficient Permissions**
   - Error: "AccessDenied: User is not authorized to perform: ..."
   - Solution: Review IAM roles in `terraform/iam.tf`. The function needs permissions for EC2, RDS, EFS, Backup, S3, and SNS across all regions.

4. **Region Access Issues**
   - Error: "UnauthorizedOperation" in specific regions
   - Solution: Ensure your AWS credentials have access to all regions, or modify the code to skip inaccessible regions.

Debugging:
- Check CloudWatch Logs at `/aws/lambda/snapshot-inventory-{environment}` for detailed execution logs
- Enable verbose logging by adding print statements in the Lambda function
- Use the AWS CLI to test individual service calls: `aws ec2 describe-snapshots --owner-ids {account-id}`

## Data Flow

The AWS Snapshot Inventory Generator processes data through the following steps:

1. **EventBridge** triggers the Lambda function daily using a scheduled rule
2. **Lambda function** iterates through all AWS regions and queries:
   - **EC2**: EBS snapshots owned by the account
   - **RDS**: Database snapshots
   - **AWS Backup**: EFS backup jobs (completed)
   - **EC2**: Unattached EBS volumes
3. **Data processing**: Calculates ages, categorizes by age groups, and aggregates by region/type
4. **Report generation**: Creates two CSV files:
   - Snapshot inventory with details (ID, type, region, age, size)
   - Unattached volumes report with idle time analysis
5. **S3 storage**: Uploads both CSV reports to the configured S3 bucket
6. **Notification**: Sends summary email via SNS with:
   - Total counts and breakdowns by type/region/age
   - Top idle unattached volumes by region
   - Links to detailed S3 reports

```
[EventBridge Daily] -> [Lambda Function] -> [All AWS Regions]
                                         -> [EC2/RDS/Backup APIs]
                                         -> [Process & Categorize]
                                         -> [Generate CSV Reports]
                                         -> [S3 Bucket Storage]
                                         -> [SNS Email Summary]
```

**Multi-Region Support**: The function automatically discovers and scans all available AWS regions, providing a comprehensive view across your entire AWS infrastructure.

## Sample Output

The application generates two types of reports:

### Email Summary Report
- Total snapshot count across all services and regions
- Regional breakdown with counts and storage sizes
- Breakdown by snapshot type (EBS, RDS, EFS)
- Age distribution categorization (7 days, 15 days, 30 days, 90 days, 180 days, 365 days, 730 days, >730 days)
- Unattached EBS volumes summary by region
- Top idle volumes with days unattached

### CSV Reports
1. **Snapshot Inventory** (`snapshot_inventory_{account}_{timestamp}.csv`):
   - Snapshot ID, Type, Region, Start Time, Size, Age (days), Age Group

2. **Unattached Volumes** (`unattached_volumes_{account}_{timestamp}.csv`):
   - Volume ID, Region, Size, State, Idle Days, Volume Type, Create Time

### Sample Email Content
```
Snapshot Inventory Summary for Account 123456789012
Generated on: 2024-02-10 17:01:22

Total Snapshots: 1,247

Regional Breakdown:
----------------------------------------

Region: eu-west-1
Total: 856 snapshots, 12,450.50 GB
By Type:
  - EBS: 720 snapshots, 8,900.25 GB
  - RDS: 136 snapshots, 3,550.25 GB

Unattached EBS Volumes Summary:
----------------------------------------
Total Unattached Volumes: 23

Region: eu-west-1
Volumes: 15, Total Size: 1,200 GB
Top Idle Volumes (by days unattached):
Volume ID: vol-0123456789abcdef0
  - Idle Days: 45
  - Size: 100 GB
  - Type: gp3
  - State: available
```

## Source Code Generation

The source code for this project was initially generated using Amazon Q, an AI-powered assistant for software development. However, it's important to note that the generated code has undergone human review and modifications to ensure its quality, security, and alignment with specific project requirements.

While Amazon Q provided a strong foundation for the project structure and core functionality, human expertise was applied to:
- Refine and optimize the code
- Ensure best practices and coding standards are followed
- Implement additional features and customizations
- Verify and enhance security measures
- Adapt the code to specific use cases and requirements

This combination of AI-generated code and human expertise allows for rapid development while maintaining high-quality, tailored solutions.

## Infrastructure

![Infrastructure diagram](./docs/infra.svg)

The project uses Terraform to define and manage the following AWS resources:

### Core Resources
- **Lambda Function** (`aws_lambda_function`):
  - Runtime: Python 3.9
  - Memory: 256 MB
  - Timeout: 300 seconds
  - Environment variables for S3 bucket and SNS topic

- **IAM Role & Policies** (`aws_iam_role`, `aws_iam_policy`):
  - **EC2**: `describe-snapshots`, `describe-volumes`, `describe-regions`
  - **RDS**: `describe-db-snapshots`
  - **AWS Backup**: `list-backup-jobs`
  - **S3**: `put-object` permissions for report storage
  - **SNS**: `publish` permissions for notifications
  - **CloudWatch**: Log group and stream management
  - **STS**: `get-caller-identity` for account ID

- **S3 Bucket** (`aws_s3_bucket`):
  - Versioning enabled
  - Server-side encryption
  - Stores CSV reports with timestamped filenames

- **SNS Topic & Subscription** (`aws_sns_topic`, `aws_sns_topic_subscription`):
  - Email notifications with summary reports
  - JSON message structure support

- **EventBridge Scheduling** (`aws_cloudwatch_event_rule`, `aws_cloudwatch_event_target`):
  - Daily execution schedule (`rate(1 day)`)
  - Lambda permission for EventBridge invocation

### File Structure
```
terraform/
├── data.tf          # Archive file for Lambda deployment package
├── eventbridge.tf   # Daily scheduling configuration
├── iam.tf          # IAM roles and policies
├── lambda.tf       # Lambda function configuration
├── outputs.tf      # Terraform outputs
├── providers.tf    # AWS provider configuration
├── s3.tf          # S3 bucket for report storage
├── sns.tf         # SNS topic and subscription
├── variables.tf   # Variable definitions
└── terraform.tfvars # Environment-specific values
```

All resources are tagged consistently using the `tags` variable for proper resource management and cost allocation.