#!/bin/bash
# Lambda deployment script
# Usage: ./deploy.sh <function-name> <s3-bucket> [region]
#
# Builds Lambda package using Docker to ensure Linux-compatible binaries
# Uses ARM64 (Graviton2) for better performance and lower cost

set -e

FUNCTION_NAME="${1:?Error: Lambda function name required}"
S3_BUCKET="${2:?Error: S3 bucket name required}"
REGION="${3:-us-east-1}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Building Lambda deployment package using Docker (arm64)..."

# Create temp directory
TEMP_DIR=$(mktemp -d)
mkdir -p "$TEMP_DIR/package"

# Build using Docker with Lambda Python runtime (arm64 for Graviton2)
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
