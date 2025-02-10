#!/bin/bash
# cleanup.sh

# Function to show usage
show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo "Options:"
    echo "  -e, --environment     Specify environment (nonprod/prod)"
    echo "  -f, --force          Force cleanup without confirmation"
    echo "  --s3-only            Clean up only S3 contents"
    echo "  -h, --help           Show this help message"
}

# Function to check if AWS CLI is configured
check_aws_cli() {
    if ! command -v aws &> /dev/null; then
        echo "AWS CLI is not installed"
        exit 1
    fi
}

# Function to check if Terraform is installed
check_terraform() {
    if ! command -v terraform &> /dev/null; then
        echo "Terraform is not installed"
        exit 1
    fi
}

# Function to empty and delete S3 bucket
empty_s3_bucket() {
    local bucket_name=$1
    echo "Emptying S3 bucket: $bucket_name"
    
    # Check if bucket exists
    if ! aws s3api head-bucket --bucket "$bucket_name" 2>/dev/null; then
        echo "Bucket does not exist: $bucket_name"
        return 0
    fi

    echo "Removing all objects and versions..."
    
    # Delete all object versions (including delete markers)
    local versions
    versions=$(aws s3api list-object-versions \
        --bucket "$bucket_name" \
        --output json \
        --query '{Objects: Versions[].{Key:Key,VersionId:VersionId}}' 2>/dev/null)
    
    if [ "$versions" != "null" ] && [ -n "$versions" ]; then
        echo "Deleting object versions..."
        echo "$versions" | jq -c '.Objects[]' | while read -r object; do
            key=$(echo "$object" | jq -r '.Key')
            version_id=$(echo "$object" | jq -r '.VersionId')
            aws s3api delete-object \
                --bucket "$bucket_name" \
                --key "$key" \
                --version-id "$version_id"
        done
    fi

    # Delete all delete markers
    local delete_markers
    delete_markers=$(aws s3api list-object-versions \
        --bucket "$bucket_name" \
        --output json \
        --query '{Objects: DeleteMarkers[].{Key:Key,VersionId:VersionId}}' 2>/dev/null)
    
    if [ "$delete_markers" != "null" ] && [ -n "$delete_markers" ]; then
        echo "Deleting delete markers..."
        echo "$delete_markers" | jq -c '.Objects[]' | while read -r marker; do
            key=$(echo "$marker" | jq -r '.Key')
            version_id=$(echo "$marker" | jq -r '.VersionId')
            aws s3api delete-object \
                --bucket "$bucket_name" \
                --key "$key" \
                --version-id "$version_id"
        done
    fi

    # Delete remaining current objects (if any)
    echo "Removing any remaining objects..."
    aws s3 rm "s3://$bucket_name" --recursive

    echo "S3 bucket emptied successfully"
}

# Function to perform full cleanup with retries
perform_full_cleanup() {
    local function_name=$1
    local bucket_name=$2
    local max_retries=3
    local retry_count=0
    
    echo "Starting full cleanup..."
    
    # Empty S3 bucket first
    empty_s3_bucket "$bucket_name"
    
    # Remove build artifacts
    rm -rf build/
    
    # Run Terraform destroy with retries
    cd terraform
    echo "Running Terraform destroy..."
    
    while [ $retry_count -lt $max_retries ]; do
        if terraform init && terraform destroy -var-file="terraform.tfvars" -auto-approve; then
            echo "Terraform destroy successful"
            break
        else
            retry_count=$((retry_count + 1))
            if [ $retry_count -lt $max_retries ]; then
                echo "Terraform destroy failed, retrying in 10 seconds... (Attempt $retry_count of $max_retries)"
                sleep 10
                
                # Try to empty the bucket again before retry
                empty_s3_bucket "$bucket_name"
            else
                echo "Failed to destroy resources after $max_retries attempts"
                exit 1
            fi
        fi
    done
    
    # Clean up Terraform files
    rm -rf .terraform/
    rm -f .terraform.lock.hcl
    rm -f terraform.tfstate*
    cd ..
    
    # Clean up CloudWatch log groups
    echo "Cleaning up CloudWatch log groups..."
    aws logs delete-log-group --log-group-name "/aws/lambda/$function_name" 2>/dev/null || true
    
    echo "Cleanup completed successfully"
}

# Function to remove Lambda versions and aliases
cleanup_lambda_versions() {
    local function_name=$1
    echo "Cleaning up Lambda versions for: $function_name"
    
    # First, list all aliases and delete them
    aliases=$(aws lambda list-aliases \
        --function-name "$function_name" \
        --query "Aliases[].Name" \
        --output text)
    
    for alias in $aliases; do
        echo "Deleting alias: $alias"
        aws lambda delete-alias \
            --function-name "$function_name" \
            --name "$alias"
    done
    
    # Get all versions except $LATEST
    versions=$(aws lambda list-versions-by-function \
        --function-name "$function_name" \
        --query "Versions[?Version!='$LATEST'].Version" \
        --output text)
    
    # Delete each version
    for version in $versions; do
        if [ "$version" != "\$LATEST" ]; then
            echo "Deleting version: $version"
            aws lambda delete-function \
                --function-name "$function_name" \
                --qualifier "$version"
        fi
    done
}

# Function to perform full cleanup
perform_full_cleanup() {
    local function_name=$1
    local bucket_name=$2
    
    echo "Starting full cleanup..."
    
    # Empty S3 bucket first (required before Terraform can delete it)
    empty_s3_bucket "$bucket_name"
    
    # Remove build artifacts
    rm -rf build/
    
    # Run Terraform destroy
    cd terraform
    echo "Running Terraform destroy..."
    terraform init
    terraform destroy -var-file="terraform.tfvars" -auto-approve
    
    # Clean up Terraform files
    rm -rf .terraform/
    rm -f .terraform.lock.hcl
    rm -f terraform.tfstate*
    cd ..
    
    # Clean up CloudWatch log groups (in case Terraform missed them)
    echo "Cleaning up CloudWatch log groups..."
    aws logs delete-log-group --log-group-name "/aws/lambda/$function_name" 2>/dev/null || true
    
    echo "Cleanup completed successfully"
}

# Function to get resource names from Terraform state
get_resource_names() {
    cd terraform
    FUNCTION_NAME=$(terraform output -raw lambda_function_name 2>/dev/null || echo "")
    BUCKET_NAME=$(terraform output -raw s3_bucket_name 2>/dev/null || echo "")
    cd ..
    
    if [ -z "$FUNCTION_NAME" ] || [ -z "$BUCKET_NAME" ]; then
        echo "Failed to get resource names from Terraform output"
        exit 1
    fi
}

# Default values
ENVIRONMENT="nonprod"
FORCE=false
S3_ONLY=false

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -e|--environment)
            ENVIRONMENT="$2"
            shift 2
            ;;
        -f|--force)
            FORCE=true
            shift
            ;;
        --s3-only)
            S3_ONLY=true
            shift
            ;;
        -h|--help)
            show_usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
done

# Validate environment
if [[ ! "$ENVIRONMENT" =~ ^(nonprod|prod)$ ]]; then
    echo "Invalid environment. Must be dev, staging, or prod"
    exit 1
fi

# Check required tools
check_aws_cli
check_terraform

# Get resource names
get_resource_names

# Confirm cleanup unless forced
if [ "$FORCE" = false ]; then
    echo "This will remove all resources for environment: $ENVIRONMENT"
    echo "Resources to be removed:"
    echo "- Lambda function: $FUNCTION_NAME"
    echo "- S3 bucket: $BUCKET_NAME"
    echo "- Associated IAM roles and policies"
    echo "- CloudWatch log groups"
    echo "- EventBridge rules"
    echo "- SNS topics"
    
    read -p "Are you sure you want to proceed? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Cleanup cancelled"
        exit 1
    fi
fi

# Perform cleanup
if [ "$S3_ONLY" = true ]; then
    # Clean up only S3 contents
    empty_s3_bucket "$BUCKET_NAME"
else
    # Full cleanup
    echo "Starting full cleanup for environment: $ENVIRONMENT"
    
    # Full cleanup with retries
    perform_full_cleanup "$FUNCTION_NAME" "$BUCKET_NAME"
fi

# Final confirmation
echo "Cleanup process finished"
if [ "$S3_ONLY" = true ]; then
    echo "S3 bucket contents have been removed"
else
    echo "All resources have been removed"
fi