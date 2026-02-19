---
title: CI/CD Pipeline
description: GitHub Actions workflows, OIDC authentication, and deployment automation for Stellarr.
---

Stellarr uses GitHub Actions for automated deployment to AWS. There are separate workflows for the application, documentation, and marketing website.

## Workflows Overview

| Workflow | Trigger | Deploys To |
|----------|---------|-----------|
| `deploy-docs.yml` | `docs/**` changes | `stellarr.dev/docs/` (S3/CloudFront) |
| `deploy-website.yml` | `website/**` changes | `stellarr.dev` (S3/CloudFront) |

All workflows also support `workflow_dispatch` for manual triggers.

## OIDC Authentication

Workflows authenticate to AWS using OpenID Connect (OIDC) — no long-lived AWS credentials are stored in GitHub.

### How It Works

1. GitHub Actions requests a short-lived OIDC token from GitHub's identity provider
2. The workflow presents this token to AWS STS via `aws-actions/configure-aws-credentials`
3. AWS validates the token against the configured OIDC provider and returns temporary credentials
4. The workflow uses these credentials (valid ~1 hour) to interact with AWS services

### IAM Configuration

The OIDC trust is configured in `website/terraform/github-oidc.tf`:

- **Identity Provider:** `token.actions.githubusercontent.com`
- **IAM Role:** Scoped to the specific GitHub repository
- **Permissions:** S3 sync, CloudFront invalidation

## Required Secrets

Configure these in GitHub repository settings (Settings → Secrets and variables → Actions):

| Secret | Description | Used By |
|--------|-------------|---------|
| `WEBSITE_DEPLOY_ROLE_ARN` | IAM role ARN for OIDC auth | Docs + Website |
| `WEBSITE_S3_BUCKET` | S3 bucket name for stellarr.dev | Docs + Website |
| `WEBSITE_CLOUDFRONT_ID` | CloudFront distribution ID | Docs + Website |

## Documentation Workflow

**File:** `.github/workflows/deploy-docs.yml`

**Triggers:** Changes to `docs/**` on the `main` branch

**Steps:**

1. Checkout repository
2. Configure AWS credentials via OIDC
3. Set up Node.js 20 with npm cache
4. `npm ci` — Install dependencies
5. `npm run build` — Build Starlight static site
6. `aws s3 sync dist/ s3://bucket/docs/ --delete` — Upload to S3 under `/docs/` prefix
7. CloudFront invalidation for `/docs/*`

**Caching:** Documentation files use `Cache-Control: public, max-age=3600` (1 hour).

**Concurrency:** The `deploy-docs` group ensures only one docs deployment runs at a time.

## Website Workflow

**File:** `.github/workflows/deploy-website.yml`

**Triggers:** Changes to `website/**` on the `main` branch

**Steps:**

1. Checkout repository
2. Configure AWS credentials via OIDC
3. Sync non-HTML assets with 24-hour cache
4. Sync HTML files with 1-hour cache
5. CloudFront invalidation for `/*`

Both S3 sync commands exclude the `docs/` prefix and `terraform/` directory to avoid interfering with the documentation site.

**Concurrency:** The `deploy-website` group ensures only one website deployment runs at a time.

## Trigger Paths

Each workflow only runs when relevant files change:

| Workflow | Trigger Paths |
|----------|--------------|
| Docs | `docs/**`, `.github/workflows/deploy-docs.yml` |
| Website | `website/**`, `.github/workflows/deploy-website.yml` |

This prevents unnecessary deployments when unrelated files change.

## Manual Deployment

All workflows support `workflow_dispatch` for manual triggers:

1. Go to the repository's **Actions** tab
2. Select the workflow
3. Click **Run workflow**
4. Select the branch and click **Run workflow**

## Deployment Independence

The documentation and website deployments are fully independent:

- **Docs deploy** only writes to `s3://bucket/docs/*` — does not affect the marketing site
- **Website deploy** excludes `docs/*` from S3 sync — does not affect documentation
- Both share the same CloudFront distribution but invalidate different path patterns
