#!/bin/bash
# deploy.sh

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$SCRIPT_DIR"
SRC_DIR="$PROJECT_ROOT/src"
TERRAFORM_DIR="$PROJECT_ROOT/terraform"
BUILD_DIR="$PROJECT_ROOT/build"

# Function to show usage
show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo "Options:"
    echo "  -e, --environment     Specify environment (nonprod/prod)"
    echo "  -l, --lambda-only     Update only the Lambda function code"
    echo "  -f, --full           Full deployment"
    echo "  -r, --rolling        Perform rolling deployment (with canary testing)"
    echo "  -w, --weight         Traffic weight for new version (default: 10)"
    echo "  --promote            Promote canary to full production"
    echo "  --rollback          Rollback to previous version"
    echo "  -h, --help           Show this help message"
}

# Function to get function name from Terraform output
get_function_name() {
    cd terraform
    FUNCTION_NAME=$(terraform output -raw lambda_function_name)
    cd ..
    echo $FUNCTION_NAME
}

# Function to update lambda function
update_lambda_function() {
    local function_name=$1
    echo "Updating Lambda function: $function_name"
    
    # Create new deployment package
    create_deployment_package
    
    # Update function code directly using AWS CLI
    aws lambda update-function-code \
        --function-name "$function_name" \
        --zip-file fileb://"$BUILD_DIR/lambda_function.zip" \
        --publish \
        || { echo "Failed to update Lambda function"; exit 1; }
    
    echo "Lambda function updated successfully"
}

# Function to create deployment package
create_deployment_package() {
    echo "Creating deployment package..."
    
    # Ensure source directory exists
    if [ ! -f "$SRC_DIR/lambda_function.py" ]; then
        echo "Error: Lambda function file not found at $SRC_DIR/lambda_function.py"
        exit 1
    fi
    
    # Clean and create build directory
    rm -rf "$BUILD_DIR"
    mkdir -p "$BUILD_DIR/lambda"
    
    # Copy lambda function code
    cp "$SRC_DIR/lambda_function.py" "$BUILD_DIR/lambda/"
    
    # Install dependencies if requirements file exists
    if [ -f "$PROJECT_ROOT/requirements-lambda.txt" ]; then
        echo "Installing dependencies..."
        pip install -r "$PROJECT_ROOT/requirements-lambda.txt" --target "$BUILD_DIR/lambda"
        
        # Remove unnecessary files to reduce package size
        find "$BUILD_DIR/lambda" -type d -name "__pycache__" -exec rm -rf {} +
        find "$BUILD_DIR/lambda" -type d -name "*.dist-info" -exec rm -rf {} +
        find "$BUILD_DIR/lambda" -type d -name "*.egg-info" -exec rm -rf {} +
    fi
    
    # Create zip file
    echo "Creating ZIP file..."
    cd "$BUILD_DIR/lambda"
    zip -r ../lambda_function.zip . -q
    cd "$PROJECT_ROOT"
    
    # Copy zip file to terraform directory
    cp "$BUILD_DIR/lambda_function.zip" "$TERRAFORM_DIR/"
    
    echo "Deployment package created at $TERRAFORM_DIR/lambda_function.zip"
}

# Function to perform rolling deployment
do_rolling_deployment() {
    local function_name=$1
    local weight=$2
    
    echo "Starting rolling deployment with ${weight}% traffic weight..."
    
    # Create new deployment package
    create_deployment_package
    
    # Update function code and publish new version
    VERSION=$(aws lambda update-function-code \
        --function-name "$function_name" \
        --zip-file fileb://build/lambda_function.zip \
        --publish \
        --query 'Version' \
        --output text)
    
    echo "Published new version: $VERSION"
    
    # Get current production version
    CURRENT_VERSION=$(aws lambda get-alias \
        --function-name "$function_name" \
        --name "$ALIAS_NAME" \
        --query 'FunctionVersion' \
        --output text 2>/dev/null || echo "1")
    
    # Update alias with weighted routing
    aws lambda update-alias \
        --function-name "$function_name" \
        --name "$ALIAS_NAME" \
        --function-version "$CURRENT_VERSION" \
        --routing-config AdditionalVersionWeights={"$VERSION"=$weight}
    
    echo "Deployment completed. Monitor the new version before promoting."
}

# Function to promote canary to production
promote_to_production() {
    local function_name=$1
    
    # Get the version with partial traffic
    VERSION=$(aws lambda get-alias \
        --function-name "$function_name" \
        --name "$ALIAS_NAME" \
        --query 'RoutingConfig.AdditionalVersionWeights[0].FunctionVersion' \
        --output text)
    
    if [ -z "$VERSION" ]; then
        echo "No canary version found to promote"
        exit 1
    fi
    
    # Update alias to point entirely to new version
    aws lambda update-alias \
        --function-name "$function_name" \
        --name "$ALIAS_NAME" \
        --function-version "$VERSION" \
        --routing-config AdditionalVersionWeights={}
    
    echo "Version $VERSION promoted to production"
}

# Function to rollback deployment
do_rollback() {
    local function_name=$1
    
    # Get previous version
    PREVIOUS_VERSION=$(aws lambda list-versions-by-function \
        --function-name "$function_name" \
        --query 'reverse(sort_by(Versions, &to_number(Version)))[1].Version' \
        --output text)
    
    # Update alias to point to previous version
    aws lambda update-alias \
        --function-name "$function_name" \
        --name "$ALIAS_NAME" \
        --function-version "$PREVIOUS_VERSION" \
        --routing-config AdditionalVersionWeights={}
    
    echo "Rolled back to version $PREVIOUS_VERSION"
}

# Default values
DEPLOY_TYPE="full"
WEIGHT=10
ALIAS_NAME="production"
ENVIRONMENT="nonprod"

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -e|--environment)
            ENVIRONMENT="$2"
            shift 2
            ;;
        -l|--lambda-only)
            DEPLOY_TYPE="lambda"
            shift
            ;;
        -f|--full)
            DEPLOY_TYPE="full"
            shift
            ;;
        -r|--rolling)
            DEPLOY_TYPE="rolling"
            shift
            ;;
        -w|--weight)
            WEIGHT="$2"
            shift 2
            ;;
        --promote)
            DEPLOY_TYPE="promote"
            shift
            ;;
        --rollback)
            DEPLOY_TYPE="rollback"
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
    echo "Invalid environment. Must be nonprod, or prod"
    exit 1
fi

# Check if terraform is installed
if ! command -v terraform &> /dev/null; then
    echo "Terraform is not installed"
    exit 1
fi

# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
    echo "AWS CLI is not installed"
    exit 1
fi

# Main deployment logic
FUNCTION_NAME=$(get_function_name)
# Main deployment logic
case $DEPLOY_TYPE in
    "lambda")
        echo "Performing Lambda-only update..."
        create_deployment_package
        update_lambda_function "$FUNCTION_NAME"
        ;;
    "full")
        echo "Performing full deployment..."
        create_deployment_package
        cd "$TERRAFORM_DIR"
        terraform init
        terraform plan -var-file="terraform.tfvars"
        terraform apply -var-file="terraform.tfvars" -auto-approve
        cd "$PROJECT_ROOT"
        ;;
    "rolling")
        do_rolling_deployment "$FUNCTION_NAME" "$WEIGHT"
        ;;
    "promote")
        promote_to_production "$FUNCTION_NAME"
        ;;
    "rollback")
        do_rollback "$FUNCTION_NAME"
        ;;
    *)
        echo "Invalid deployment type"
        show_usage
        exit 1
        ;;
esac

echo "Deployment completed successfully"
