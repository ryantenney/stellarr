---
sidebar_position: 2
title: AWS Deployment
---

# AWS Serverless Deployment

Deploy Stellarr to AWS using Lambda, DynamoDB, and CloudFront for a low-cost, highly available setup.

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
domain_name      = "stellarr.example.com"
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

### 3. Deploy Application

```bash
cd ..
./deploy.sh --skip-tf   # Backend + frontend (skip terraform since we just ran it)
```

**Other deploy options:**

```bash
./deploy.sh              # Full deploy (terraform + backend + frontend)
./deploy.sh --backend    # Backend Lambda only
./deploy.sh --frontend   # Frontend + CloudFront invalidation only
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
- Caching for frontend assets and trending data (1 hour)
- Gzip/Brotli compression

## Updating

```bash
./deploy.sh --backend    # Backend changes only
./deploy.sh --frontend   # Frontend changes only
./deploy.sh --skip-tf    # Both backend + frontend
./deploy.sh              # Full deploy including terraform
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
