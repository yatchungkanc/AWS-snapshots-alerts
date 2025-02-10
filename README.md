# AWS Snapshot Inventory Generator

This project automates the process of generating and reporting AWS snapshot inventories across multiple services.

The AWS Snapshot Inventory Generator is a serverless application that creates comprehensive reports of snapshots from various AWS services, including EC2, RDS, and EFS. It calculates snapshot ages, categorizes them, and generates both detailed CSV reports and summary notifications. This tool is designed to help AWS administrators and DevOps teams maintain better visibility and control over their snapshot resources.

The application is built using AWS Lambda and is deployed using Terraform. It leverages several AWS services, including S3 for report storage, SNS for notifications, and EventBridge for scheduling. The solution is designed to be easily deployable and configurable across different environments.

## Repository Structure

```
.
├── cleanup.sh
├── deploy.sh
├── requirements-lambda.txt
├── setup.sh
├── src
│   └── lambda_function.py
├── terraform
│   ├── data.tf
│   ├── eventbridge.tf
│   ├── iam.tf
│   ├── lambda.tf
│   ├── outputs.tf
│   ├── providers.tf
│   ├── s3.tf
│   ├── sns.tf
│   └── variables.tf
└── test_snapshot_inventory.py
```

### Key Files:
- `src/lambda_function.py`: The main Lambda function that generates the snapshot inventory.
- `deploy.sh`: Script for deploying the application.
- `cleanup.sh`: Script for cleaning up resources.
- `setup.sh`: Script for setting up the project structure.
- `terraform/`: Directory containing Terraform configuration files for infrastructure provisioning.
- `test_snapshot_inventory.py`: Unit tests for the snapshot inventory functionality.

## Usage Instructions

### Installation

Prerequisites:
- AWS CLI (version 2.0 or later)
- Terraform (version 1.0 or later)
- Python 3.8 or later

Steps:
1. Clone the repository:
   ```
   git clone <repository-url>
   cd aws-snapshot-inventory-generator
   ```

2. Run the setup script:
   ```
   ./setup.sh
   ```

3. Install Python dependencies:
   ```
   pip install -r requirements-lambda.txt
   ```

### Deployment

To deploy the application:

1. Configure your AWS credentials:
   ```
   aws configure
   ```

2. Run the deployment script:
   ```
   ./deploy.sh -e nonprod -f
   ```

   Options:
   - `-e, --environment`: Specify the environment (nonprod or prod)
   - `-f, --full`: Perform a full deployment

### Configuration

The application can be configured through environment variables and Terraform variables. Key configurations include:

- `S3_BUCKET_NAME`: Name of the S3 bucket for storing reports
- `SNS_TOPIC_ARN`: ARN of the SNS topic for notifications

These can be set in the `terraform/variables.tf` file or overridden during deployment.

### Testing

To run the unit tests:

```
python -m unittest test_snapshot_inventory.py
```

### Troubleshooting

Common issues:

1. Deployment Failure
   - Error: "Error: NoSuchBucket: The specified bucket does not exist"
   - Solution: Ensure the S3 bucket name is unique and correctly specified in your Terraform configuration.

2. Lambda Function Timeout
   - Error: "Task timed out after X seconds"
   - Solution: Increase the Lambda function timeout in `terraform/lambda.tf`. Monitor CloudWatch logs for performance bottlenecks.

3. Insufficient Permissions
   - Error: "AccessDenied: User is not authorized to perform: ..."
   - Solution: Review and update the IAM roles in `terraform/iam.tf` to ensure necessary permissions are granted.

Debugging:
- Enable verbose logging in the Lambda function by setting the `LOG_LEVEL` environment variable to `DEBUG`.
- Check CloudWatch Logs for detailed error messages and stack traces.

## Data Flow

The AWS Snapshot Inventory Generator processes data through the following steps:

1. EventBridge triggers the Lambda function on a scheduled basis.
2. The Lambda function queries EC2, RDS, and EFS services for snapshot information.
3. Snapshot data is processed, categorized, and summarized.
4. A detailed CSV report is generated and uploaded to the specified S3 bucket.
5. A summary report is created and sent as a notification via SNS.

```
[EventBridge] -> [Lambda Function] -> [EC2/RDS/EFS APIs]
                                   -> [Process Data]
                                   -> [Generate Reports]
                                   -> [S3 Bucket]
                                   -> [SNS Topic]
```

Note: Ensure that the Lambda function has appropriate permissions to access the required AWS services and resources.

## Infrastructure

The project uses Terraform to define and manage the following AWS resources:

- Lambda:
  - `aws_lambda_function`: The main Lambda function for generating snapshot inventories.
- IAM:
  - `aws_iam_role`: IAM role for the Lambda function with necessary permissions.
  - `aws_iam_role_policy_attachment`: Attaches policies to the IAM role.
- S3:
  - `aws_s3_bucket`: Bucket for storing snapshot inventory reports.
- SNS:
  - `aws_sns_topic`: Topic for sending notifications about generated reports.
- EventBridge:
  - `aws_cloudwatch_event_rule`: Rule for scheduling the Lambda function execution.
  - `aws_cloudwatch_event_target`: Target linking the EventBridge rule to the Lambda function.

These resources are defined in the respective Terraform files within the `terraform/` directory.