#!/bin/bash
# setup.sh

# Create project structure
mkdir -p src
mkdir -p terraform
mkdir -p build

# Move existing files to correct locations
if [ -f "lambda_function.py" ]; then
    mv lambda_function.py src/
fi

# Create necessary files if they don't exist
touch src/lambda_function.py
touch requirements.txt
touch requirements-lambda.txt

# Make scripts executable
chmod +x deploy.sh
chmod +x cleanup.sh

echo "Project structure created successfully"
