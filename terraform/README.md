# Terraform Configuration for Stellarr

This Terraform configuration deploys Stellarr to AWS using a serverless architecture optimized for minimal cost.

## Architecture

```
                                    ┌─────────────────┐
                                    │   CloudFront    │
                                    │   Distribution  │
                                    └────────┬────────┘
                                             │
                        ┌────────────────────┼────────────────────┐
                        │                    │                    │
                        ▼                    ▼                    ▼
                 ┌─────────────┐      ┌─────────────┐      ┌─────────────┐
                 │  S3 Bucket  │      │   Lambda    │      │   Lambda    │
                 │  (Frontend) │      │   (/api/*)  │      │ (/rss,/list)│
                 └─────────────┘      └──────┬──────┘      └──────┬──────┘
                                             │                    │
                                             ▼                    │
                                      ┌─────────────┐             │
                                      │  DynamoDB   │◀────────────┘
                                      │  (Requests) │
                                      └─────────────┘
                                             │
                                             ▼
                                      ┌─────────────┐
                                      │   Secrets   │
                                      │   Manager   │
                                      └─────────────┘
```

## Cost Estimate

This architecture is optimized for minimal cost:

| Service | Monthly Cost |
|---------|--------------|
| DynamoDB | **$0** (free tier: 25GB + 25 WCU/RCU) |
| Lambda | **$0** (free tier: 1M requests/month) |
| CloudFront | **$0** (free tier: 1TB transfer/month) |
| S3 | **$0** (free tier: 5GB storage) |
| Secrets Manager | **~$0.40** (1 secret) |
| Route53 | **~$0.50** (hosted zone) |
| ACM Certificate | **$0** (free) |
| **Total** | **~$0.50-1/month** |

**Optional:** AWS WAF adds ~$8/month for rate limiting and threat protection.

## Prerequisites

- AWS CLI configured with appropriate credentials
- Terraform >= 1.0
- A Route53 hosted zone for your domain
- TMDB API key (free at https://www.themoviedb.org/settings/api)

## Quick Start

### 1. Configure Variables

```bash
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars`:

```hcl
# Required
domain_name        = "stellarr.example.com"
hosted_zone_id     = "Z1234567890ABC"
tmdb_api_key       = "your-tmdb-api-key"
preshared_password = "your-secure-password"

# Optional
environment  = "prod"
feed_token   = "optional-feed-protection-token"
enable_waf   = false  # Enable AWS WAF for rate limiting (~$8/month)
```

### 2. Initialize and Deploy

```bash
terraform init
terraform plan
terraform apply
```

### 3. Deploy Application Code

After infrastructure is created:

```bash
# Deploy frontend
cd ../frontend
npm install && npm run build
aws s3 sync build/ s3://$(terraform -chdir=../terraform output -raw frontend_bucket_name)
aws cloudfront create-invalidation \
  --distribution-id $(terraform -chdir=../terraform output -raw cloudfront_distribution_id) \
  --paths "/*"

# Deploy backend
cd ../backend-lambda
./deploy.sh \
  $(terraform -chdir=../terraform output -raw lambda_function_name) \
  $(terraform -chdir=../terraform output -raw lambda_deployment_bucket)
```

## Variables Reference

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `domain_name` | Domain for the application | - | Yes |
| `hosted_zone_id` | Route53 hosted zone ID | - | Yes |
| `tmdb_api_key` | TMDB API key | - | Yes |
| `preshared_password` | User authentication password | - | Yes |
| `aws_region` | AWS region | `us-east-1` | No |
| `environment` | Environment name (dev/staging/prod) | `prod` | No |
| `feed_token` | Token for RSS/list endpoint protection | `""` | No |
| `enable_waf` | Enable AWS WAF | `false` | No |
| `waf_rate_limit` | Requests per 5 min per IP | `100` | No |
| `lambda_memory` | Lambda memory (MB) | `512` | No |
| `lambda_timeout` | Lambda timeout (seconds) | `30` | No |

## Remote State (Recommended)

For production, store Terraform state remotely:

### 1. Create State Infrastructure

```bash
cd backend-setup
terraform init
terraform apply
```

### 2. Configure Backend

Uncomment the backend block in `main.tf`:

```hcl
backend "s3" {
  bucket         = "stellarr-terraform-state"
  key            = "stellarr/terraform.tfstate"
  region         = "us-east-1"
  encrypt        = true
  dynamodb_table = "stellarr-terraform-locks"
}
```

### 3. Migrate State

```bash
cd ..  # Back to main terraform directory
terraform init -migrate-state
```

## AWS WAF (Optional)

Enable WAF for additional security:

```hcl
enable_waf = true
```

WAF provides:
- **Rate limiting** - Blocks IPs exceeding request limits
- **AWS Managed Rules** - Protection against common exploits (SQLi, XSS)
- **IP Reputation** - Blocks known malicious IPs

**Cost:** ~$8/month base + $0.60/million requests

## Outputs

| Output | Description |
|--------|-------------|
| `website_url` | Full URL of the application |
| `cloudfront_distribution_id` | For cache invalidation |
| `frontend_bucket_name` | S3 bucket for frontend files |
| `lambda_function_name` | Lambda function name |
| `lambda_deployment_bucket` | S3 bucket for Lambda code uploads |
| `dynamodb_table_name` | DynamoDB table for requests |

## Security Features

- **HTTPS everywhere** - TLS 1.2+ enforced via CloudFront
- **Signed session tokens** - HMAC-SHA256 with 30-day expiry
- **Secrets Manager** - API keys and passwords stored securely
- **Private S3** - Frontend only accessible via CloudFront OAC
- **IAM least privilege** - Lambda has minimal required permissions
- **WAF (optional)** - Rate limiting and threat protection

## Destroying Infrastructure

```bash
# Remove frontend files first (versioned bucket)
aws s3 rm s3://$(terraform output -raw frontend_bucket_name) --recursive

# Destroy infrastructure
terraform destroy
```

## Troubleshooting

### Lambda cold starts
Increase `lambda_memory` for faster cold starts (more memory = more CPU).

### TMDB API timeouts
Lambda timeout defaults to 30 seconds. TMDB API calls should complete well within this.

### CloudFront 403 errors
Ensure S3 bucket policy allows CloudFront OAC access. Run `terraform apply` to fix.

### Feed URLs showing Lambda URL
Ensure `BASE_URL` environment variable is set on Lambda. Run `terraform apply` to update.

### WAF blocking legitimate requests
Check CloudWatch logs and adjust `waf_rate_limit` if needed.

## Files

| File | Description |
|------|-------------|
| `main.tf` | Provider configuration |
| `dynamodb.tf` | DynamoDB table for requests |
| `lambda.tf` | Lambda function and IAM roles |
| `frontend.tf` | S3, CloudFront, ACM, Route53 |
| `secrets.tf` | Secrets Manager for app config |
| `waf.tf` | Optional AWS WAF configuration |
| `variables.tf` | Input variables |
| `outputs.tf` | Output values |
