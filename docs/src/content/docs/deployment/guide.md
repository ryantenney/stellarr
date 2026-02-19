---
title: Deployment Guide
description: Step-by-step guide for deploying Stellarr to AWS using Terraform and the unified deploy script.
---

This guide walks through deploying Stellarr to AWS from scratch, including infrastructure provisioning with Terraform and application deployment.

## Prerequisites

- AWS CLI configured with admin-level permissions
- Terraform >= 1.0
- Docker (for building Lambda packages)
- Node.js >= 20 (for building the frontend)
- A Route53 hosted zone for your domain

## Step 1: Set Up Terraform Backend (Optional)

For production, use remote state storage to prevent state file conflicts:

```bash
cd terraform/backend-setup
terraform init
terraform apply
```

This creates:
- S3 bucket for Terraform state (`stellarr-terraform-state`)
- DynamoDB table for state locking (`stellarr-terraform-locks`)

Then uncomment the `backend "s3"` block in `terraform/main.tf` and run `terraform init` to migrate.

## Step 2: Configure Terraform Variables

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars`:

```hcl
# Required
aws_region       = "us-east-1"
domain_name      = "stellarr.example.com"
hosted_zone_id   = "Z1234567890ABC"      # Your Route53 zone ID
tmdb_api_key     = "your-tmdb-api-key"
preshared_password = "your-password"

# Optional
feed_token         = "your-feed-token"
plex_webhook_token = "your-webhook-token"
tvdb_api_key       = ""
plex_server_name   = ""

# Infrastructure tuning
lambda_memory = 512       # MB (default: 512)
lambda_timeout = 30       # seconds (default: 30)
enable_waf = false        # Adds ~$8/month
enable_rate_limiting = true
```

## Step 3: Deploy Infrastructure

```bash
terraform init
terraform plan    # Review changes
terraform apply   # Create resources
```

This provisions all AWS resources. The Lambda functions will have placeholder code until the application is deployed.

## Step 4: Deploy Application

The unified `deploy.sh` script handles backend and frontend deployment:

```bash
cd /path/to/stellarr
./deploy.sh --skip-tf
```

This runs:
1. **Backend** — Builds Lambda package in Docker (ARM64), creates Layer, uploads to S3, updates Lambda functions
2. **Frontend** — Runs `npm ci && npm run build`, syncs to S3
3. **Cache** — Invokes cache warmer Lambda to populate trending data
4. **Invalidation** — Creates CloudFront invalidation for all paths

### Deploy Script Flags

| Flag | Action |
|------|--------|
| (no args) | Full deploy: Terraform + backend + frontend + invalidation |
| `--skip-tf` | Skip Terraform, deploy backend + frontend + invalidation |
| `--backend` | Backend Lambda only |
| `--frontend` | Frontend + CloudFront invalidation only |
| `--terraform` | Terraform apply only |
| `--invalidate` | CloudFront cache invalidation only |

Flags can be combined:

```bash
./deploy.sh --backend --frontend  # Both without Terraform
```

## Step 5: Verify Deployment

1. Visit `https://your-domain.com` — you should see the Stellarr login page
2. Log in with your `PRESHARED_PASSWORD`
3. Search for a movie or TV show
4. Check the health endpoint: `https://your-domain.com/api/health`

## Updating

### Code Changes Only

```bash
./deploy.sh --skip-tf    # Backend + frontend
./deploy.sh --backend    # Backend only
./deploy.sh --frontend   # Frontend only
```

### Infrastructure Changes

```bash
./deploy.sh              # Full deploy (Terraform + code)
```

Or separately:

```bash
cd terraform && terraform apply
./deploy.sh --skip-tf
```

## Website Deployment

The marketing website at `stellarr.dev` is deployed separately. See `website/terraform/` for its infrastructure and `.github/workflows/deploy-website.yml` for CI/CD.

The documentation site at `stellarr.dev/docs/` is built from the `docs/` directory and deployed via `.github/workflows/deploy-docs.yml`.

## Cleanup

To destroy all AWS resources:

```bash
cd terraform
terraform destroy
```

:::caution
This permanently deletes all data including the DynamoDB table and S3 buckets. There is no undo.
:::
