#!/bin/bash
# Lambda deployment script
# Usage: ./deploy.sh <function-name> <s3-bucket> [region]
#
# Builds Lambda package using Docker to ensure Linux-compatible binaries

set -e

FUNCTION_NAME="${1:?Error: Lambda function name required}"
S3_BUCKET="${2:?Error: S3 bucket name required}"
REGION="${3:-us-east-1}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Building Lambda deployment package using Docker..."

# Create temp directory
TEMP_DIR=$(mktemp -d)
mkdir -p "$TEMP_DIR/package"

# Build using Docker with Lambda Python runtime (x86_64 for Lambda compatibility)
docker run --rm --platform linux/amd64 \
    --entrypoint /bin/bash \
    -v "$SCRIPT_DIR":/var/task \
    -v "$TEMP_DIR/package":/var/package \
    public.ecr.aws/lambda/python:3.12 \
    -c "pip install -r /var/task/requirements.txt -t /var/package --quiet && cp /var/task/*.py /var/package/"

# Create zip
cd "$TEMP_DIR/package"
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
