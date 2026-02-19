---
title: Architecture Overview
description: System overview, component inventory, and data flow for Stellarr's dual backend architecture.
---

Stellarr is a lightweight media request system built around a dual backend architecture, serving a static SvelteKit SPA via CloudFront.

## System Overview

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Browser   │────▶│ CloudFront  │────▶│  S3 Bucket  │  (Frontend SPA)
│             │     │    (CDN)    │     └─────────────┘
└─────────────┘     │             │     ┌─────────────┐
                    │             │────▶│  S3 Bucket  │  (Trending JSON)
                    │             │     └─────────────┘
                    │             │     ┌─────────────┐
                    │             │────▶│   Lambda    │────▶ TMDB / TVDB APIs
                    └─────────────┘     │  (FastAPI)  │
                                        └──────┬──────┘
                                        ┌──────▼──────┐
                                        │  DynamoDB   │
                                        └─────────────┘

┌─────────────┐
│ EventBridge │─── (daily) ──▶ Cache Warmer Lambda ──▶ S3 (trending JSON)
└─────────────┘

┌─────────────┐
│    Plex     │─── (webhook) ──▶ Lambda /webhook/plex ──▶ DynamoDB
└─────────────┘

┌─────────────┐
│ Sonarr /    │─── (poll) ──▶ Lambda /list/radarr, /list/sonarr
│ Radarr      │
└─────────────┘
```

## Component Inventory

### Frontend

| Component | Technology | Purpose |
|-----------|-----------|---------|
| SPA | SvelteKit 2 + static adapter | Search, request, and browse media |
| Build | Vite 5 | Module bundling and optimization |
| Hosting | S3 + CloudFront | Static file serving with CDN |

The frontend is a pure static SPA — no server-side rendering or Node.js runtime required. It's built once and deployed as HTML/JS/CSS files to S3.

### Backend (AWS)

| Component | Technology | Purpose |
|-----------|-----------|---------|
| API server | FastAPI + Mangum | HTTP endpoints via Lambda Function URL |
| Runtime | Python 3.12, ARM64 (Graviton2) | Request handling |
| Database | DynamoDB (on-demand) | Request and library storage |
| DynamoDB client | Custom httpx + SigV4 | Lightweight alternative to boto3 |
| Secrets | AWS Secrets Manager | Configuration storage |
| Heavy deps | Lambda Layer (cryptography) | Web Push notification signing |

### Backend (Docker)

| Component | Technology | Purpose |
|-----------|-----------|---------|
| API server | FastAPI + Uvicorn | HTTP endpoints |
| Database | SQLite (aiosqlite) | Request and library storage |
| Reverse proxy | Caddy | HTTPS termination, routing |

### Supporting Services

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Cache warmer | Separate Lambda (128 MB) | Daily TMDB trending fetch → S3 |
| Scheduler | EventBridge | Triggers cache warmer every 24 hours |
| CDN | CloudFront | Routes requests to S3/Lambda origins |
| DNS | Route53 | Domain resolution |
| TLS | ACM | SSL certificates for CloudFront |
| WAF (optional) | AWS WAFv2 | Rate limiting and threat protection |

## Dual Backend Pattern

Both backends (`backend/` for Docker, `backend-lambda/` for AWS) expose identical FastAPI endpoints. They share the same application logic but differ in:

| Aspect | Docker (`backend/`) | Lambda (`backend-lambda/`) |
|--------|--------------------|-----------------------------|
| Database | SQLite via aiosqlite | DynamoDB via custom client |
| Entry point | Uvicorn ASGI server | Mangum Lambda handler |
| Config | `.env` file | Secrets Manager |
| Async model | Fully async | Sync (Lambda single-request) |
| Rate limiting | Not implemented | DynamoDB TTL entries |

Shared modules (`tmdb.py`, `plex.py`, `tvdb.py`) are duplicated in both backend directories and must be kept in sync.

## Data Flow

### Search and Request

1. User authenticates → receives signed session token
2. User searches → `/api/search` proxies to TMDB API
3. Results are enriched with library/request status from DynamoDB
4. User requests an item → stored in DynamoDB
5. Sonarr/Radarr polls `/list/sonarr` or `/list/radarr` on a schedule
6. \*arr application downloads the media

### Trending Display

1. EventBridge triggers cache warmer Lambda daily
2. Cache warmer fetches trending movies/TV from TMDB API
3. Results are written to S3 as `trending-{type}-{locale}.json`
4. CloudFront serves these files with a 1-hour cache
5. Frontend fetches trending data (no Lambda invocation needed)
6. Library/request status is hydrated client-side from cached data

### Plex Integration

1. Plex detects new media → sends `library.new` webhook
2. Lambda parses the payload and extracts TMDB/TVDB IDs
3. Multi-strategy matching: TMDB ID → TVDB ID → Plex GUID cache → TVDB API lookup
4. If matched: marks `added_at` timestamp, sends push notification
5. Frontend shows "In Library" / "Added" badges

## CloudFront Routing

CloudFront distributes requests across three origins based on path patterns:

| Pattern | Origin | Cache TTL | Purpose |
|---------|--------|-----------|---------|
| `/trending-*.json` | S3 (trending) | 1 hour | Trending data |
| `/api/*` | Lambda URL | None | API endpoints |
| `/list/*` | Lambda URL | 5 minutes | Feed endpoints |
| `/webhook/*`, `/sync/*` | Lambda URL | None | Webhook/sync |
| `/*` (default) | S3 (frontend) | 1 hour | SPA static files |

The frontend S3 bucket has custom error responses (403/404 → `/index.html`) to support SPA client-side routing.

## Key File Map

```
backend/                 # Docker backend
├── main.py              # FastAPI app (SQLite)
├── database.py          # SQLite CRUD
├── tmdb.py              # TMDB API client (shared)
├── plex.py              # Plex webhook parsing (shared)
└── tvdb.py              # TVDB episode lookup (shared)

backend-lambda/          # AWS Lambda backend
├── main.py              # FastAPI app (DynamoDB)
├── dynamodb_lite.py     # Custom DynamoDB client
├── aws_sigv4.py         # AWS Signature V4 signing
├── cache_warmer.py      # Trending cache Lambda handler
├── deploy.sh            # Lambda deployment script
├── requirements.txt     # Main dependencies
└── requirements-layer.txt  # Layer dependencies (cryptography)

frontend/                # SvelteKit SPA
├── src/routes/          # Page components
├── src/lib/api.js       # HTTP client
└── src/lib/stores.js    # Auth state, library cache

terraform/               # AWS infrastructure
├── main.tf              # Provider, backend config
├── lambda.tf            # Lambda functions, IAM, EventBridge
├── frontend.tf          # S3, CloudFront, ACM, Route53
├── dynamodb.tf          # DynamoDB table
├── secrets.tf           # Secrets Manager
├── waf.tf               # WAF (optional)
├── variables.tf         # Input variables
└── outputs.tf           # Terraform outputs
```
