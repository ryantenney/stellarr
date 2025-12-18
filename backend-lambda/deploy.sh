#!/bin/bash
# Lambda deployment script
# Usage: ./deploy.sh <function-name> <s3-bucket> [region]

set -e

FUNCTION_NAME="${1:?Error: Lambda function name required}"
S3_BUCKET="${2:?Error: S3 bucket name required}"
REGION="${3:-us-east-1}"

echo "Building Lambda deployment package..."

# Create temp directory
TEMP_DIR=$(mktemp -d)
PACKAGE_DIR="$TEMP_DIR/package"
mkdir -p "$PACKAGE_DIR"

# Install dependencies
pip install -r requirements.txt -t "$PACKAGE_DIR" --quiet

# Copy source files
cp *.py "$PACKAGE_DIR/"

# Create zip
cd "$PACKAGE_DIR"
zip -r "$TEMP_DIR/lambda.zip" . -q

echo "Uploading to S3..."
aws s3 cp "$TEMP_DIR/lambda.zip" "s3://$S3_BUCKET/lambda/overseer-lite.zip" --region "$REGION"

echo "Updating Lambda function..."
aws lambda update-function-code \
    --function-name "$FUNCTION_NAME" \
    --s3-bucket "$S3_BUCKET" \
    --s3-key "lambda/overseer-lite.zip" \
    --region "$REGION"

# Clean up
rm -rf "$TEMP_DIR"

echo "Deployment complete!"
