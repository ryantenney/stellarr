# Terraform Configuration for Overseer Lite

This Terraform configuration deploys Overseer Lite to AWS using a serverless architecture.

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
                                             ▼                    ▼
                                      ┌─────────────┐      ┌─────────────┐
                                      │   Aurora    │      │   Secrets   │
                                      │ Serverless  │      │   Manager   │
                                      │ PostgreSQL  │      └─────────────┘
                                      └─────────────┘
```

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
domain_name        = "overseer.example.com"
hosted_zone_id     = "Z1234567890ABC"
tmdb_api_key       = "your-tmdb-api-key"
preshared_password = "your-secure-password"

# Optional
environment  = "prod"
feed_token   = "optional-feed-protection-token"
enable_waf   = true  # Enable AWS WAF for rate limiting
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
  your-deployment-bucket
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
| `waf_auth_rate_limit` | Auth requests per 5 min per IP | `100` | No |
| `db_min_capacity` | Aurora min ACU | `0.5` | No |
| `db_max_capacity` | Aurora max ACU | `2` | No |
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
  bucket         = "overseer-lite-terraform-state"
  key            = "overseer-lite/terraform.tfstate"
  region         = "us-east-1"
  encrypt        = true
  dynamodb_table = "overseer-lite-terraform-locks"
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
- **CloudWatch logging** - Logs blocked requests

**Cost:** ~$6-8/month base + $0.60/million requests

## Outputs

| Output | Description |
|--------|-------------|
| `cloudfront_domain` | CloudFront distribution domain |
| `cloudfront_distribution_id` | For cache invalidation |
| `frontend_bucket_name` | S3 bucket for frontend files |
| `lambda_function_name` | Lambda function name |
| `lambda_function_url` | Direct Lambda URL (internal) |

## Cost Estimate

Minimal usage (~100 requests/day):

| Service | Estimated Cost |
|---------|----------------|
| Aurora Serverless v2 | ~$15-30/month (scales to near-zero when idle) |
| Lambda | Free tier (1M requests/month) |
| CloudFront | ~$1-5/month |
| S3 | < $1/month |
| Secrets Manager | ~$1/month |
| WAF (if enabled) | ~$6-8/month |

**Total:** ~$20-50/month depending on usage

## Security Features

- **HTTPS everywhere** - TLS 1.2+ enforced
- **Signed session tokens** - HMAC-SHA256 with 30-day expiry
- **Secrets Manager** - Credentials stored securely
- **Private VPC** - Aurora only accessible from Lambda
- **S3 private** - Frontend only accessible via CloudFront OAC
- **WAF (optional)** - Rate limiting and threat protection

## Destroying Infrastructure

```bash
# Remove frontend files first (versioned bucket)
aws s3 rm s3://$(terraform output -raw frontend_bucket_name) --recursive

# Destroy infrastructure
terraform destroy
```

**Note:** Aurora with `skip_final_snapshot = false` (prod) will create a final snapshot.

## Troubleshooting

### Lambda cold starts
Increase `lambda_memory` for faster cold starts (more memory = more CPU).

### Aurora connection issues
Check Lambda security group allows outbound to Aurora security group on port 5432.

### CloudFront 403 errors
Ensure S3 bucket policy allows CloudFront OAC access. Run `terraform apply` to fix.

### WAF blocking legitimate requests
Check CloudWatch logs (`aws-waf-logs-*`) and adjust rules or add exclusions.
