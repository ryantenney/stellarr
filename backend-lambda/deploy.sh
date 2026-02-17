#!/bin/bash
# Lambda deployment script
# Usage: ./deploy.sh <function-name> <s3-bucket> [region]
#
# Builds Lambda package using Docker to ensure Linux-compatible binaries
# Uses ARM64 (Graviton2) for better performance and lower cost
#
# Also builds a Lambda Layer for heavy dependencies (cryptography)

set -e

FUNCTION_NAME="${1:?Error: Lambda function name required}"
S3_BUCKET="${2:?Error: S3 bucket name required}"
REGION="${3:-us-east-1}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Create temp directory
TEMP_DIR=$(mktemp -d)
mkdir -p "$TEMP_DIR/package"
mkdir -p "$TEMP_DIR/layer/python"

echo "Building Lambda Layer (cryptography) using Docker (arm64)..."

# Build layer with heavy dependencies
docker run --rm --platform linux/arm64 \
    --entrypoint /bin/bash \
    -v "$SCRIPT_DIR":/var/task \
    -v "$TEMP_DIR/layer/python":/var/layer \
    public.ecr.aws/lambda/python:3.12 \
    -c '
        pip install -r /var/task/requirements-layer.txt -t /var/layer --quiet && \
        python -m compileall -b -q /var/layer && \
        find /var/layer -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    '

# Create layer zip
cd "$TEMP_DIR/layer"
zip -r "$TEMP_DIR/layer.zip" . -q
LAYER_SIZE=$(du -h "$TEMP_DIR/layer.zip" | cut -f1)
echo "Layer size: $LAYER_SIZE"

echo "Building Lambda deployment package using Docker (arm64)..."

# Build main package (without layer dependencies)
docker run --rm --platform linux/arm64 \
    --entrypoint /bin/bash \
    -v "$SCRIPT_DIR":/var/task \
    -v "$TEMP_DIR/package":/var/package \
    public.ecr.aws/lambda/python:3.12 \
    -c '
        pip install -r /var/task/requirements.txt -t /var/package --quiet && \
        cp /var/task/*.py /var/package/ && \
        python -m compileall -b -q /var/package && \
        python -c "
import os
import shutil
from pathlib import Path

pkg = Path(\"/var/package\")

# Remove __pycache__ directories
for p in pkg.rglob(\"__pycache__\"):
    if p.is_dir():
        shutil.rmtree(p)

# Remove top-level .py files (our source code)
for p in pkg.glob(\"*.py\"):
    p.unlink()

# Remove .py from pure-Python packages (no .so files)
for d in pkg.iterdir():
    if d.is_dir() and not any(d.rglob(\"*.so\")):
        for p in d.rglob(\"*.py\"):
            p.unlink()
"
    '

# Create function zip
cd "$TEMP_DIR/package"
zip -r "$TEMP_DIR/lambda.zip" . -q
LAMBDA_SIZE=$(du -h "$TEMP_DIR/lambda.zip" | cut -f1)
echo "Lambda size: $LAMBDA_SIZE"

echo "Uploading to S3..."
aws s3 cp "$TEMP_DIR/lambda.zip" "s3://$S3_BUCKET/lambda/stellarr.zip" --region "$REGION"
aws s3 cp "$TEMP_DIR/layer.zip" "s3://$S3_BUCKET/lambda/stellarr-layer.zip" --region "$REGION"

# Derive layer name from function name (same prefix)
LAYER_NAME="${FUNCTION_NAME%-api}-deps"

echo "Publishing new layer version..."
LAYER_VERSION=$(aws lambda publish-layer-version \
    --layer-name "$LAYER_NAME" \
    --content S3Bucket="$S3_BUCKET",S3Key="lambda/stellarr-layer.zip" \
    --compatible-runtimes python3.12 \
    --compatible-architectures arm64 \
    --region "$REGION" \
    --query 'Version' \
    --output text)
echo "Layer version: $LAYER_VERSION"

LAYER_ARN="arn:aws:lambda:$REGION:$(aws sts get-caller-identity --query Account --output text):layer:$LAYER_NAME:$LAYER_VERSION"

echo "Updating Lambda function..."
aws lambda update-function-code \
    --function-name "$FUNCTION_NAME" \
    --s3-bucket "$S3_BUCKET" \
    --s3-key "lambda/stellarr.zip" \
    --region "$REGION" \
    > /dev/null

echo "Waiting for function update..."
aws lambda wait function-updated --function-name "$FUNCTION_NAME" --region "$REGION"

echo "Updating Lambda to use new layer version..."
aws lambda update-function-configuration \
    --function-name "$FUNCTION_NAME" \
    --layers "$LAYER_ARN" \
    --region "$REGION" > /dev/null

# Clean up
rm -rf "$TEMP_DIR"

echo "Deployment complete!"
