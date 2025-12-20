# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

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
- `/api/auth/verify` - Password authentication, returns HMAC-SHA256 signed token
- `/api/search` - TMDB search with media type filter
- `/api/request`, `/api/requests` - Add/list/remove requests
- `/list/radarr`, `/list/sonarr` - JSON feeds for import lists
- `/rss/movies`, `/rss/tv`, `/rss/all` - RSS feeds

### Authentication
- Preshared password → HMAC-SHA256 signed token (30-day expiry, hardcoded)
- Token sent via Authorization: Bearer header
- Feed endpoints are public (optional FEED_TOKEN query param protection)

## Key Files

**Backend:** `main.py` (FastAPI app), `database.py` (CRUD), `tmdb.py` (API client), `rss.py` (feed generation), `config.py` (Pydantic settings)

**Lambda-specific:** `dynamodb_lite.py` + `aws_sigv4.py` (lightweight DynamoDB without boto3 for cold start optimization)

**Frontend:** `src/routes/+page.svelte` (search/home), `src/routes/requests/+page.svelte` (request list), `src/lib/api.js` (HTTP client), `src/lib/stores.js` (auth state)

## Environment Variables

Required: `APP_SECRET_KEY`, `PRESHARED_PASSWORD`, `TMDB_API_KEY`
Optional: `FEED_TOKEN` (protects feed endpoints), `DATABASE_PATH`

## Important Patterns

- All database operations are async
- Items can exist in requests without IMDB/TVDB IDs but won't appear in respective feeds (UI shows warnings)
- Lambda uses lazy imports and bytecode precompilation for cold start optimization
- Vite dev server proxies `/api` and `/rss` to `localhost:8000` for local development
