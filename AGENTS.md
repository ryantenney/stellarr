# AGENTS.md

This file provides guidance to AI coding assistants working with this repository.

## Project Overview

Overseer Lite is a lightweight media request system for searching TV shows and movies via TMDB and exposing requests as RSS feeds and JSON endpoints compatible with Sonarr and Radarr.

## Development Commands

### Frontend (Svelte)
```bash
cd frontend
npm install
npm run dev      # Vite dev server at localhost:5173, proxies /api to localhost:8000
npm run build    # Build static SPA to build/
```

### Backend (Docker - legacy)
```bash
docker compose up -d                          # Start all services (backend, frontend, Caddy)
docker compose -f docker-compose.prod.yml up -d  # Production with HTTPS
```

### Backend (AWS Lambda)
```bash
cd backend-lambda
./deploy.sh {lambda_function_name} {deployment_bucket}  # ARM64 build + deploy
```

### Unified Deployment
```bash
./deploy.sh              # Deploy everything (terraform, backend, frontend, invalidate)
./deploy.sh --skip-tf    # Skip terraform
./deploy.sh --backend    # Backend only
./deploy.sh --frontend   # Frontend + cache invalidation
```

### Terraform (AWS Infrastructure)
```bash
cd terraform
terraform init && terraform plan && terraform apply
```

## Architecture

### Cloud Provider Abstraction

The codebase uses a provider-based architecture to support multiple cloud platforms:

```
shared/              # Cloud-agnostic application logic
├── app.py           # FastAPI routes + provider registry
├── config.py        # Base Settings model (Pydantic)
├── database.py      # Database Protocol (interface definition)
├── tmdb.py          # TMDB API client
├── plex.py          # Plex webhook parsing
├── tvdb.py          # TVDB API client (episode→show lookup)
└── webpush.py       # Web Push notifications

providers/           # Cloud-specific implementations
├── aws/             # AWS Lambda + DynamoDB + Secrets Manager
│   ├── handler.py   # Lambda entry point (Mangum)
│   ├── database.py  # DynamoDB implementation
│   ├── config.py    # AWS Secrets Manager config loading
│   ├── aws_sigv4.py # SigV4 signing (replaces boto3)
│   ├── dynamodb_lite.py  # Lightweight DynamoDB client
│   └── cache_warmer.py   # EventBridge-triggered trending cache
├── gcp/             # GCP Cloud Run + Firestore + Secret Manager (stubs)
│   ├── handler.py   # Cloud Run/Functions entry point
│   ├── database.py  # Firestore implementation
│   └── config.py    # GCP Secret Manager config loading
└── azure/           # Azure Functions + Cosmos DB + Key Vault (stubs)
    ├── handler.py   # Azure Functions entry point
    ├── database.py  # Cosmos DB implementation
    └── config.py    # Azure Key Vault config loading
```

### Provider Registry Pattern

`shared/app.py` uses a registry pattern for dependency injection:

```python
from shared.app import registry

# Provider's handler registers implementations at startup:
registry.configure(
    settings_fn=get_settings,     # Config loader
    database=provider_database,    # Database module
    tmdb_client=tmdb_instance,     # TMDB client
    plex_module=plex_module,       # Plex parser
    tvdb_module=tvdb_module,       # TVDB client
    webpush_module=webpush_module, # Push notifications
)
```

All routes in `shared/app.py` access providers via `get_database()`, `get_settings()`, etc. which read from the registry.

### Database Interface

All cloud providers must implement the functions defined in `shared/database.py` (Protocol class). Current implementations:
- **AWS**: DynamoDB via custom SigV4 HTTP client (no boto3)
- **GCP**: Firestore (stub - not yet implemented)
- **Azure**: Cosmos DB (stub - not yet implemented)

### Legacy Backends

| Path | Database | Status |
|------|----------|--------|
| `backend/` | SQLite (aiosqlite) | Legacy Docker/self-hosted |
| `backend-lambda/` | DynamoDB (flat files) | Legacy - migrated to providers/aws/ |

The `backend-lambda/` directory still contains `deploy.sh` and `requirements*.txt` for Lambda packaging. The actual source code now lives in `shared/` and `providers/aws/`.

**Frontend** is a static SPA (SvelteKit with static adapter) - no Node.js server needed in production.

### Key Endpoints
- `/api/auth/params` - Returns PBKDF2 iterations for client-side key derivation
- `/api/auth/verify` - Password authentication, returns HMAC-SHA256 signed token
- `/api/search` - TMDB search with media type filter
- `/trending-{all,movie,tv}.json` - Trending media (public, served from S3 via CloudFront, 1hr cache)
- `/api/library-status` - Library IDs + pending requests (authenticated)
- `/api/request`, `/api/requests` - Add/list/remove requests
- `/api/feeds` - Get feed URLs for UI
- `/list/radarr`, `/list/sonarr` - JSON feeds for import lists
- `/webhook/plex?token=XXX` - Plex webhook (marks requests added, updates library)
- `/sync/library?media_type=X&token=XXX` - Bulk library sync
- `/api/push/*` - Web push notification subscription management

### Authentication
- Preshared password → PBKDF2 key derivation (client-side) → HMAC-SHA256 signed token (30-day expiry)
- Token sent via Authorization: Bearer header
- Feed endpoints protected by optional FEED_TOKEN query param
- Webhook/sync endpoints protected by PLEX_WEBHOOK_TOKEN query param

## Key Files

**Shared (cloud-agnostic):** `shared/app.py` (FastAPI routes + registry), `shared/database.py` (interface), `shared/tmdb.py` (TMDB client), `shared/plex.py` (webhook parsing), `shared/tvdb.py` (episode→show lookup), `shared/webpush.py` (push notifications), `shared/config.py` (base settings model)

**AWS Provider:** `providers/aws/handler.py` (Lambda entry point), `providers/aws/database.py` (DynamoDB CRUD), `providers/aws/config.py` (Secrets Manager loading), `providers/aws/dynamodb_lite.py` + `providers/aws/aws_sigv4.py` (lightweight DynamoDB without boto3), `providers/aws/cache_warmer.py` (trending cache Lambda)

**GCP/Azure Providers:** Stub implementations in `providers/gcp/` and `providers/azure/` - see handler.py files for implementation guidance.

**Frontend:** `src/routes/+page.svelte` (search/home), `src/routes/requests/+page.svelte` (request list), `src/routes/+layout.svelte` (nav, feeds modal, PWA setup), `src/lib/api.js` (HTTP client), `src/lib/stores.js` (auth state, library status cache)

**Scripts:** `scripts/plex-sync.py` (bulk library sync)

## Environment Variables

Required: `APP_SECRET_KEY`, `PRESHARED_PASSWORD`, `TMDB_API_KEY`
Optional: `FEED_TOKEN` (protects feed endpoints), `PLEX_WEBHOOK_TOKEN` (protects webhook/sync), `PLEX_SERVER_NAME` (filter webhooks), `TVDB_API_KEY` (episode→show resolution), `DATABASE_PATH` (Docker only)

AWS-specific: `APP_SECRET_ARN`, `DYNAMODB_TABLE`, `AWS_REGION_NAME`, `RATE_LIMIT_ENABLED`, `RATE_LIMIT_MAX_ATTEMPTS`, `RATE_LIMIT_WINDOW_SECONDS`, `ALLOWED_ORIGIN`, `BASE_URL`, `VAPID_PUBLIC_KEY`, `TRENDING_S3_BUCKET`

## Important Patterns

- Database functions are synchronous (suitable for serverless cold starts)
- The provider registry in `shared/app.py` enables lazy initialization for cold start optimization
- AWS provider uses lazy imports and bytecode precompilation for cold start optimization
- Vite dev server proxies `/api`, `/rss`, `/list`, `/webhook`, `/sync` to `localhost:8000`
- Library table tracks items in Plex; populated via webhook (incremental) or sync endpoint (bulk)
- Plex webhook logs use `WEBHOOK:` prefix; sync logs use `SYNC:` prefix (for CloudWatch filtering)
- Frontend is a PWA with iOS/Android home screen support

### Adding a New Cloud Provider

To add support for a new cloud provider:

1. Create `providers/{provider}/` directory
2. Implement `database.py` with all functions from `shared/database.py` Protocol
3. Implement `config.py` with a `get_settings()` function returning a `shared.config.Settings` instance
4. Implement `handler.py` that:
   - Calls `shared.app.registry.configure(...)` with provider implementations
   - Exposes the ASGI app for the serverless platform
5. Add infrastructure-as-code (Terraform) for the provider's resources
6. Update `backend-lambda/deploy.sh` or create a new deploy script

### Trending Cache Architecture
- Trending data is served as static JSON files from S3 via CloudFront (no Lambda invocation)
- EventBridge triggers a cache warmer Lambda daily to fetch TMDB trending and write to S3
- S3 objects have `Cache-Control: max-age=3600` (1 hour), CloudFront serves `/trending-*.json` from S3
- Frontend fetches library/request status on login via `/api/library-status`
- Library status is cached in localStorage and used to hydrate trending/search results with user-specific status
- This architecture ensures: (a) trending is fast and cheap (pure CDN), (b) private status stays protected, (c) data refreshes daily, cache revalidates hourly
