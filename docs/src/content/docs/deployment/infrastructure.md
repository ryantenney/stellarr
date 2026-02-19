---
title: Infrastructure Reference
description: AWS resource inventory, Terraform file map, and cost breakdown for Stellarr's serverless infrastructure.
---

Stellarr's AWS infrastructure is fully managed by Terraform. This page documents the resources, their configuration, and estimated costs.

## AWS Resource Inventory

### Compute

| Resource | Type | Configuration |
|----------|------|---------------|
| API Lambda | `aws_lambda_function` | Python 3.12, ARM64, 512 MB, 30s timeout |
| Cache Warmer Lambda | `aws_lambda_function` | Python 3.12, ARM64, 128 MB, 60s timeout |
| Dependencies Layer | `aws_lambda_layer_version` | cryptography library (ARM64) |
| Lambda Function URL | `aws_lambda_function_url` | Public, CORS configured |

### Storage

| Resource | Type | Purpose |
|----------|------|---------|
| Frontend Bucket | `aws_s3_bucket` | SPA static files (versioned) |
| Trending Bucket | `aws_s3_bucket` | Trending JSON files |
| Lambda Deploy Bucket | `aws_s3_bucket` | Lambda packages (versioned) |
| DynamoDB Table | `aws_dynamodb_table` | Requests, library, rate limits (on-demand) |

### Networking & CDN

| Resource | Type | Purpose |
|----------|------|---------|
| CloudFront Distribution | `aws_cloudfront_distribution` | CDN with 3 origins |
| ACM Certificate | `aws_acm_certificate` | TLS for CloudFront (us-east-1) |
| Route53 Record | `aws_route53_record` | DNS A record (alias to CloudFront) |
| Origin Access Controls | `aws_cloudfront_origin_access_control` | S3 access for frontend + trending |

### Security & Configuration

| Resource | Type | Purpose |
|----------|------|---------|
| Lambda IAM Role | `aws_iam_role` | Execution role for both Lambdas |
| Secrets Manager | `aws_secretsmanager_secret` | App config (API keys, passwords) |
| WAF (optional) | `aws_wafv2_web_acl` | Rate limiting and threat protection |
| CloudWatch Log Groups | `aws_cloudwatch_log_group` | Lambda logs (14d / 7d retention) |

### Scheduling

| Resource | Type | Purpose |
|----------|------|---------|
| EventBridge Rule | `aws_cloudwatch_event_rule` | Daily cache warmer trigger |
| EventBridge Target | `aws_cloudwatch_event_target` | Links rule to cache warmer Lambda |

## Terraform File Map

| File | Resources |
|------|-----------|
| `main.tf` | Provider config, random suffix, locals |
| `lambda.tf` | Lambda functions, IAM role/policies, Layer, EventBridge, CloudWatch logs |
| `frontend.tf` | S3 buckets, CloudFront, ACM certificate, Route53, OAC |
| `dynamodb.tf` | DynamoDB table (on-demand, TTL enabled) |
| `secrets.tf` | Secrets Manager, VAPID key generation |
| `waf.tf` | WAF Web ACL, rules, logging (conditional on `enable_waf`) |
| `variables.tf` | Input variable definitions |
| `outputs.tf` | Output values (bucket names, function names, URLs) |

### Backend Setup (`terraform/backend-setup/`)

| File | Purpose |
|------|---------|
| `main.tf` | S3 bucket + DynamoDB table for Terraform remote state |

## CloudFront Origins

The CloudFront distribution routes to three origins:

| Origin ID | Type | Source |
|-----------|------|--------|
| `s3-frontend` | S3 (OAC) | Frontend static files |
| `s3-trending` | S3 (OAC) | Trending JSON files |
| `lambda-api` | Custom (HTTPS) | Lambda Function URL |

### Cache Behaviors

| Priority | Path Pattern | Origin | Cache TTL | Methods |
|----------|-------------|--------|-----------|---------|
| — | `/*` (default) | s3-frontend | 1 hour | GET, HEAD |
| 1 | `/trending-*.json` | s3-trending | 1 hour | GET, HEAD |
| 2 | `/api/*` | lambda-api | None | ALL |
| 3 | `/list/*` | lambda-api | 5 min | GET, HEAD |
| 4 | `/webhook/*` | lambda-api | None | ALL |
| 5 | `/sync/*` | lambda-api | None | ALL |

## DynamoDB Schema

Single table design with on-demand billing:

| Attribute | Type | Key |
|-----------|------|-----|
| `media_type` | String | Partition Key |
| `tmdb_id` | Number | Sort Key |
| `ttl` | Number | TTL attribute |

Access patterns:

| Operation | Key Pattern |
|-----------|-------------|
| Get/set movie request | PK=`movie`, SK=`{tmdb_id}` |
| Get/set TV request | PK=`tv`, SK=`{tmdb_id}` |
| List all movies | PK=`movie`, Scan |
| Rate limit check | PK=`RATELIMIT#{ip}`, SK=`0` |
| Push subscription | PK=`PUSH#{endpoint}`, SK=`0` |
| Plex GUID cache | PK=`PLEX_GUID#{guid}`, SK=`0` |

## IAM Permissions

The Lambda execution role has these policies:

| Policy | Permissions |
|--------|-------------|
| `AWSLambdaBasicExecutionRole` | CloudWatch Logs (managed policy) |
| `lambda-secrets` | `secretsmanager:GetSecretValue` on app config secret |
| `lambda-dynamodb` | Full DynamoDB access on the requests table |
| `lambda-trending-s3` | `s3:PutObject` on trending bucket |

## Cost Breakdown

### Base Cost (~$0.50-1/month)

| Service | Monthly Cost | Notes |
|---------|-------------|-------|
| Secrets Manager | ~$0.40 | 1 secret × $0.40/secret |
| Route53 | ~$0.50 | Hosted zone fee |
| DynamoDB | $0 | Free tier: 25 GB + 25 WCU/RCU |
| Lambda | $0 | Free tier: 1M requests |
| CloudFront | $0 | Free tier: 1 TB transfer |
| S3 | $0 | Free tier: 5 GB storage |
| CloudWatch | $0 | Free tier: 5 GB logs |
| **Total** | **~$0.90** | |

### Optional Add-ons

| Service | Monthly Cost | Notes |
|---------|-------------|-------|
| WAF | ~$8 | $5 Web ACL + $1/rule × 5 rules |
| Provisioned Concurrency | ~$3+ | Eliminates cold starts |

### After Free Tier

| Service | Pricing | Typical Cost |
|---------|---------|-------------|
| Lambda | $0.20/1M requests | < $0.01/month |
| DynamoDB | $0.25/1M writes | < $0.01/month |
| CloudFront | $0.085/GB | < $0.10/month |
| S3 | $0.023/GB | < $0.01/month |

## Terraform Outputs

After `terraform apply`, these outputs are available:

| Output | Description |
|--------|-------------|
| `website_url` | `https://your-domain.com` |
| `cloudfront_distribution_id` | For cache invalidation |
| `frontend_bucket_name` | S3 bucket for frontend deploys |
| `lambda_function_name` | API Lambda function name |
| `lambda_deployment_bucket` | S3 bucket for Lambda packages |
| `lambda_function_url` | Direct Lambda Function URL |
| `dynamodb_table_name` | DynamoDB table name |
| `app_secret_arn` | Secrets Manager ARN |
| `cache_warmer_function_name` | Cache warmer Lambda name |
