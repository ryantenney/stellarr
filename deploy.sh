#!/bin/bash
#
# Unified deployment script for Stellarr
#
# Usage:
#   ./deploy.sh              # Deploy everything (terraform + backend + frontend + invalidate)
#   ./deploy.sh --skip-tf    # Skip terraform, deploy backend + frontend + invalidate
#   ./deploy.sh --backend    # Deploy backend only
#   ./deploy.sh --frontend   # Deploy frontend only + invalidate
#   ./deploy.sh --terraform  # Run terraform only
#   ./deploy.sh --invalidate # Invalidate CloudFront cache only
#
# Options can be combined:
#   ./deploy.sh --backend --frontend  # Deploy both without terraform
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default: deploy everything
DO_TERRAFORM=false
DO_BACKEND=false
DO_FRONTEND=false
DO_INVALIDATE=false
SKIP_TERRAFORM=false

# Parse arguments
if [ $# -eq 0 ]; then
    # No args = deploy everything
    DO_TERRAFORM=true
    DO_BACKEND=true
    DO_FRONTEND=true
    DO_INVALIDATE=true
else
    while [[ $# -gt 0 ]]; do
        case $1 in
            --skip-tf|--skip-terraform)
                SKIP_TERRAFORM=true
                DO_BACKEND=true
                DO_FRONTEND=true
                DO_INVALIDATE=true
                shift
                ;;
            --terraform|--tf)
                DO_TERRAFORM=true
                shift
                ;;
            --backend|--lambda)
                DO_BACKEND=true
                shift
                ;;
            --frontend|--fe)
                DO_FRONTEND=true
                DO_INVALIDATE=true
                shift
                ;;
            --invalidate|--inv)
                DO_INVALIDATE=true
                shift
                ;;
            --help|-h)
                echo "Usage: ./deploy.sh [options]"
                echo ""
                echo "Options:"
                echo "  (no args)      Deploy everything (terraform + backend + frontend + invalidate)"
                echo "  --skip-tf      Skip terraform, deploy backend + frontend + invalidate"
                echo "  --terraform    Run terraform apply only"
                echo "  --backend      Deploy Lambda backend only"
                echo "  --frontend     Deploy frontend to S3 + invalidate cache"
                echo "  --invalidate   Invalidate CloudFront cache only"
                echo ""
                echo "Options can be combined: ./deploy.sh --backend --frontend"
                exit 0
                ;;
            *)
                echo -e "${RED}Unknown option: $1${NC}"
                exit 1
                ;;
        esac
    done
fi

# Get terraform outputs (needed for most operations)
get_tf_outputs() {
    echo -e "${BLUE}Fetching terraform outputs...${NC}"
    cd "$SCRIPT_DIR/terraform"

    FRONTEND_BUCKET=$(terraform output -raw frontend_bucket_name 2>/dev/null) || true
    LAMBDA_FUNCTION=$(terraform output -raw lambda_function_name 2>/dev/null) || true
    LAMBDA_BUCKET=$(terraform output -raw lambda_deployment_bucket 2>/dev/null) || true
    CLOUDFRONT_ID=$(terraform output -raw cloudfront_distribution_id 2>/dev/null) || true
    CACHE_WARMER_FUNCTION=$(terraform output -raw cache_warmer_function_name 2>/dev/null) || true
    APP_NAME=$(terraform output -raw app_name 2>/dev/null) || APP_NAME="Stellarr"

    cd "$SCRIPT_DIR"

    if [ -z "$FRONTEND_BUCKET" ] || [ -z "$LAMBDA_FUNCTION" ]; then
        echo -e "${YELLOW}Warning: Could not get terraform outputs. Run terraform first.${NC}"
        return 1
    fi
    return 0
}

# Step 1: Terraform
deploy_terraform() {
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  Step 1: Terraform Apply${NC}"
    echo -e "${GREEN}========================================${NC}"

    cd "$SCRIPT_DIR/terraform"
    terraform init -upgrade
    terraform apply -auto-approve
    cd "$SCRIPT_DIR"

    echo -e "${GREEN}Terraform complete!${NC}"
}

# Step 2: Backend (Lambda)
deploy_backend() {
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  Step 2: Deploy Backend (Lambda)${NC}"
    echo -e "${GREEN}========================================${NC}"

    if [ -z "$LAMBDA_FUNCTION" ] || [ -z "$LAMBDA_BUCKET" ]; then
        echo -e "${RED}Error: Missing Lambda configuration. Run terraform first.${NC}"
        exit 1
    fi

    cd "$SCRIPT_DIR/backend-lambda"
    ./deploy.sh "$LAMBDA_FUNCTION" "$LAMBDA_BUCKET"

    # Also update cache warmer Lambda (same code package)
    if [ -n "$CACHE_WARMER_FUNCTION" ]; then
        echo "Updating cache warmer Lambda..."
        aws lambda update-function-code \
            --function-name "$CACHE_WARMER_FUNCTION" \
            --s3-bucket "$LAMBDA_BUCKET" \
            --s3-key "lambda/stellarr.zip" \
            --region us-east-1 \
            > /dev/null

        # Invoke cache warmer to populate S3 trending data
        echo "Warming trending cache..."
        aws lambda invoke \
            --function-name "$CACHE_WARMER_FUNCTION" \
            --region us-east-1 \
            /tmp/cache-warmer-output.json > /dev/null
        cat /tmp/cache-warmer-output.json
        rm -f /tmp/cache-warmer-output.json
        echo ""
    fi

    cd "$SCRIPT_DIR"

    echo -e "${GREEN}Backend deployment complete!${NC}"
}

# Step 3: Frontend
deploy_frontend() {
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  Step 3: Deploy Frontend${NC}"
    echo -e "${GREEN}========================================${NC}"

    if [ -z "$FRONTEND_BUCKET" ]; then
        echo -e "${RED}Error: Missing frontend bucket. Run terraform first.${NC}"
        exit 1
    fi

    cd "$SCRIPT_DIR/frontend"

    echo "Installing dependencies..."
    npm ci

    echo "Building frontend..."
    VITE_APP_NAME="$APP_NAME" npm run build

    echo "Uploading to S3..."
    aws s3 sync build/ "s3://$FRONTEND_BUCKET" --delete

    cd "$SCRIPT_DIR"

    echo -e "${GREEN}Frontend deployment complete!${NC}"
}

# Step 4: Cache Invalidation
invalidate_cache() {
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  Step 4: Invalidate CloudFront Cache${NC}"
    echo -e "${GREEN}========================================${NC}"

    if [ -z "$CLOUDFRONT_ID" ]; then
        echo -e "${RED}Error: Missing CloudFront distribution ID. Run terraform first.${NC}"
        exit 1
    fi

    echo "Creating cache invalidation..."
    INVALIDATION_ID=$(aws cloudfront create-invalidation \
        --distribution-id "$CLOUDFRONT_ID" \
        --paths "/*" \
        --query 'Invalidation.Id' \
        --output text)

    echo "Invalidation created: $INVALIDATION_ID"
    echo "Waiting for invalidation to complete..."

    aws cloudfront wait invalidation-completed \
        --distribution-id "$CLOUDFRONT_ID" \
        --id "$INVALIDATION_ID"

    echo -e "${GREEN}Cache invalidation complete!${NC}"
}

# Main execution
echo -e "${BLUE}Stellarr Deployment${NC}"
echo -e "${BLUE}========================${NC}"

# Run terraform if requested
if [ "$DO_TERRAFORM" = true ] && [ "$SKIP_TERRAFORM" = false ]; then
    deploy_terraform
fi

# Get outputs for other steps
if [ "$DO_BACKEND" = true ] || [ "$DO_FRONTEND" = true ] || [ "$DO_INVALIDATE" = true ]; then
    get_tf_outputs || {
        if [ "$DO_TERRAFORM" = false ]; then
            echo -e "${RED}Error: Terraform outputs not available. Run with --terraform first.${NC}"
            exit 1
        fi
    }
fi

# Deploy backend
if [ "$DO_BACKEND" = true ]; then
    deploy_backend
fi

# Deploy frontend
if [ "$DO_FRONTEND" = true ]; then
    deploy_frontend
fi

# Invalidate cache
if [ "$DO_INVALIDATE" = true ]; then
    invalidate_cache
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Deployment Complete!${NC}"
echo -e "${GREEN}========================================${NC}"

if [ -n "$CLOUDFRONT_ID" ]; then
    WEBSITE_URL=$(cd "$SCRIPT_DIR/terraform" && terraform output -raw website_url 2>/dev/null) || true
    if [ -n "$WEBSITE_URL" ]; then
        echo -e "Site: ${BLUE}$WEBSITE_URL${NC}"
    fi
fi
