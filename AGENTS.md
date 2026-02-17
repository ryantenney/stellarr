# AGENTS.md

This file provides guidance to AI coding assistants working with this repository.

## Project Overview

Stellarr is a lightweight media request system for searching TV shows and movies via TMDB and exposing requests as RSS feeds and JSON endpoints compatible with Sonarr and Radarr.

## Development Commands

### Frontend (Svelte)
```bash
cd frontend
npm install
npm run dev      # Vite dev server at localhost:5173, proxies /api to localhost:8000
npm run build    # Build static SPA to build/
```

### Backend (Docker)
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

**Two parallel backend implementations exist:**

| Path | Database | Use Case |
|------|----------|----------|
| `backend/` | SQLite (aiosqlite) | Docker/self-hosted |
| `backend-lambda/` | DynamoDB (custom client, no boto3) | AWS serverless |

Both backends expose the same FastAPI endpoints. Changes to API structure must be made in both `backend/main.py` and `backend-lambda/main.py`.

**Shared modules** (`tmdb.py`, `rss.py`) are duplicated in both backend directories - keep them synced.

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
- `/rss/movies`, `/rss/tv`, `/rss/all` - RSS feeds
- `/webhook/plex?token=XXX` - Plex webhook (marks requests added, updates library)
- `/sync/library?media_type=X&token=XXX` - Bulk library sync

### Authentication
- Preshared password → PBKDF2 key derivation (client-side) → HMAC-SHA256 signed token (30-day expiry)
- Token sent via Authorization: Bearer header
- Feed endpoints protected by optional FEED_TOKEN query param
- Webhook/sync endpoints protected by PLEX_WEBHOOK_TOKEN query param

## Key Files

**Backend:** `main.py` (FastAPI app), `database.py` (CRUD), `tmdb.py` (API client), `rss.py` (feed generation), `plex.py` (webhook parsing), `tvdb.py` (episode→show lookup), `config.py` (Pydantic settings)

**Lambda-specific:** `dynamodb_lite.py` + `aws_sigv4.py` (lightweight DynamoDB without boto3 for cold start optimization)

**Frontend:** `src/routes/+page.svelte` (search/home), `src/routes/requests/+page.svelte` (request list), `src/routes/+layout.svelte` (nav, feeds modal, PWA setup), `src/lib/api.js` (HTTP client), `src/lib/stores.js` (auth state, library status cache)

**Cache Warmer:** `cache_warmer.py` (Lambda triggered by EventBridge every hour to fetch TMDB trending and write to S3)

**Scripts:** `scripts/plex-sync.py` (bulk library sync)

## Environment Variables

Required: `APP_SECRET_KEY`, `PRESHARED_PASSWORD`, `TMDB_API_KEY`
Optional: `FEED_TOKEN` (protects feed endpoints), `PLEX_WEBHOOK_TOKEN` (protects webhook/sync), `PLEX_SERVER_NAME` (filter webhooks), `TVDB_API_KEY` (episode→show resolution), `DATABASE_PATH`

## Important Patterns

- All database operations are async (SQLite) or sync (DynamoDB in Lambda)
- Items can exist in requests without IMDB/TVDB IDs but won't appear in respective feeds (UI shows warnings)
- Lambda uses lazy imports and bytecode precompilation for cold start optimization
- Vite dev server proxies `/api`, `/rss`, `/list`, `/webhook`, `/sync` to `localhost:8000`
- Library table tracks items in Plex; populated via webhook (incremental) or sync endpoint (bulk)
- Plex webhook logs use `WEBHOOK:` prefix; sync logs use `SYNC:` prefix (for CloudWatch filtering)
- Frontend is a PWA with iOS/Android home screen support

### Trending Cache Architecture
- Trending data is served as static JSON files from S3 via CloudFront (no Lambda invocation)
- EventBridge triggers a cache warmer Lambda daily to fetch TMDB trending and write to S3
- S3 objects have `Cache-Control: max-age=3600` (1 hour), CloudFront serves `/trending-*.json` from S3
- Frontend fetches library/request status on login via `/api/library-status`
- Library status is cached in localStorage and used to hydrate trending/search results with user-specific status
- This architecture ensures: (a) trending is fast and cheap (pure CDN), (b) private status stays protected, (c) data refreshes daily, cache revalidates hourly
