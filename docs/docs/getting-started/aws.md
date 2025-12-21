---
sidebar_position: 2
title: AWS Deployment
---

# AWS Serverless Deployment

Deploy Overseer Lite to AWS using Lambda, DynamoDB, and CloudFront for a low-cost, highly available setup.

## Prerequisites

- AWS CLI configured with appropriate permissions
- Terraform >= 1.0
- Route53 hosted zone for your domain
- TMDB API key

## Cost Estimate

| Service | Monthly Cost |
|---------|--------------|
| DynamoDB | $0 (free tier: 25GB + 25 WCU/RCU) |
| Lambda | $0 (free tier: 1M requests) |
| CloudFront | $0 (free tier: 1TB transfer) |
| S3 | $0 (free tier: 5GB) |
| Secrets Manager | ~$0.40 |
| Route53 | ~$0.50 (hosted zone) |
| **Total** | **~$0.50-1/month** |

## Deployment Steps

### 1. Configure Terraform

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars`:

```hcl
aws_region       = "us-east-1"
domain_name      = "overseer.example.com"
route53_zone_id  = "Z1234567890ABC"

# Secrets (will be stored in AWS Secrets Manager)
tmdb_api_key        = "your-tmdb-api-key"
app_secret_key      = "your-secret-key"          # openssl rand -hex 32
preshared_password  = "your-password"
feed_token          = "your-feed-token"          # optional
plex_webhook_token  = "your-webhook-token"       # optional
tvdb_api_key        = "your-tvdb-api-key"        # optional
```

### 2. Deploy Infrastructure

```bash
terraform init
terraform plan
terraform apply
```

This creates:
- DynamoDB table
- Lambda function (ARM64)
- S3 bucket for frontend
- CloudFront distribution with HTTPS
- Route53 DNS records
- Secrets Manager secret

### 3. Deploy Backend

```bash
cd ../backend-lambda
./deploy.sh \
  $(terraform -chdir=../terraform output -raw lambda_function_name) \
  $(terraform -chdir=../terraform output -raw lambda_deployment_bucket)
```

### 4. Deploy Frontend

```bash
cd ../frontend
npm install
npm run build
aws s3 sync build/ s3://$(terraform -chdir=../terraform output -raw frontend_bucket_name)
```

### 5. Invalidate CloudFront Cache

```bash
aws cloudfront create-invalidation \
  --distribution-id $(terraform -chdir=../terraform output -raw cloudfront_distribution_id) \
  --paths "/*"
```

## Unified Deployment Script

After initial setup, use the unified deploy script:

```bash
# Deploy everything
./deploy.sh

# Skip Terraform (just redeploy code)
./deploy.sh --skip-tf

# Backend only
./deploy.sh --backend

# Frontend only (with cache invalidation)
./deploy.sh --frontend
```

## Infrastructure Details

### Lambda Function

- Runtime: Python 3.12 (ARM64)
- Memory: 256MB (configurable)
- Timeout: 30 seconds
- Cold start optimization via lazy imports

### DynamoDB Table

- On-demand capacity (pay per request)
- Primary key: `media_type` (partition) + `tmdb_id` (sort)
- TTL enabled for rate limit entries

### CloudFront

- HTTPS only (TLS 1.2+)
- Caching for frontend assets and `/api/trending` (1 hour)
- Gzip/Brotli compression

## Updating

### Backend Changes

```bash
cd backend-lambda
./deploy.sh $(terraform -chdir=../terraform output -raw lambda_function_name) \
  $(terraform -chdir=../terraform output -raw lambda_deployment_bucket)
```

### Frontend Changes

```bash
cd frontend
npm run build
aws s3 sync build/ s3://$(terraform -chdir=../terraform output -raw frontend_bucket_name)
aws cloudfront create-invalidation \
  --distribution-id $(terraform -chdir=../terraform output -raw cloudfront_distribution_id) \
  --paths "/*"
```

### Infrastructure Changes

```bash
cd terraform
terraform plan
terraform apply
```

## Monitoring

### CloudWatch Logs

Lambda logs are available in CloudWatch. Filter webhook events:

```
fields @timestamp, @message
| filter @message like /WEBHOOK:/
| sort @timestamp desc
| limit 100
```

### CloudWatch Metrics

Key metrics to monitor:
- Lambda invocations and errors
- DynamoDB consumed capacity
- CloudFront cache hit ratio

## Cleanup

To destroy all resources:

```bash
cd terraform
terraform destroy
```

:::warning
This will delete all data including the DynamoDB table. Export your requests first if needed.
:::

## Next Steps

- [Configure environment variables](/configuration)
- [Set up Plex integration](/plex-integration)
- [Configure Sonarr & Radarr](/sonarr-radarr)
