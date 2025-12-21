# Overseer Lite

A lightweight media request system that generates feeds compatible with Sonarr and Radarr. Users can search for TV shows and movies via TMDB and add them to request lists, which are exposed as import list endpoints.

## Features

- **Simple Authentication**: Preshared password with PBKDF2 key derivation and signed session tokens
- **TMDB Integration**: Search movies and TV shows using The Movie Database
- **Sonarr/Radarr Import Lists**: Native JSON formats for direct import
- **Plex Webhook Integration**: Auto-mark requests as added when Plex downloads media
- **Library Sync**: Batch sync Plex library to show "In Library" badges
- **Feed Token Protection**: Optional token-based auth for feed endpoints
- **Missing ID Warnings**: UI indicators when external IDs (IMDB/TVDB) are missing
- **Large Series Warnings**: Visual indicator for TV shows with 7+ seasons
- **PWA Support**: Install as app on iOS/Android with proper icons
- **Modern UI**: Svelte-based responsive frontend with mobile optimizations
- **Multiple Deployment Options**:
  - Docker Compose with Caddy (auto HTTPS)
  - AWS Serverless (Lambda + DynamoDB + CloudFront)

## Deployment Options

### Option 1: Docker (Recommended for Self-Hosting)

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Browser   │────▶│    Caddy    │────▶│  Frontend   │
│             │     │  (Reverse   │     │  (Svelte)   │
└─────────────┘     │   Proxy +   │     └─────────────┘
                    │   HTTPS)    │     ┌─────────────┐
                    │             │────▶│   Backend   │
                    └─────────────┘     │  (FastAPI)  │
                                        └──────┬──────┘
                                        ┌──────▼──────┐
                                        │   SQLite    │
                                        └─────────────┘
```

### Option 2: AWS Serverless (Low Cost)

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Browser   │────▶│ CloudFront  │────▶│  S3 Bucket  │
│             │     │    (CDN)    │     │ (Frontend)  │
└─────────────┘     │             │     └─────────────┘
                    │             │     ┌─────────────┐
                    │             │────▶│   Lambda    │────▶ TMDB API
                    └─────────────┘     │  (FastAPI)  │
                                        └──────┬──────┘
                                        ┌──────▼──────┐
                                        │  DynamoDB   │
                                        │ (on-demand) │
                                        └─────────────┘
```

**AWS Cost: ~$0.50-1/month** (mostly Secrets Manager + Route53)

## Quick Start (Docker)

### Prerequisites

- Docker and Docker Compose
- TMDB API Key (free at https://www.themoviedb.org/settings/api)

### Setup

1. Clone and configure:
   ```bash
   git clone <repo-url>
   cd overseer-lite
   cp .env.example .env
   # Edit .env with your settings
   ```

2. Start the application:
   ```bash
   # Development (HTTP only)
   docker compose up -d

   # Production (automatic HTTPS via Caddy)
   docker compose -f docker-compose.prod.yml up -d
   ```

3. Access at `http://localhost` or `https://your-domain.com`

## AWS Serverless Deployment

### Prerequisites

- AWS CLI configured
- Terraform >= 1.0
- Route53 hosted zone for your domain
- TMDB API key

### Setup

1. Configure Terraform variables:
   ```bash
   cd terraform
   cp terraform.tfvars.example terraform.tfvars
   # Edit terraform.tfvars with your settings
   ```

2. Deploy infrastructure:
   ```bash
   terraform init
   terraform plan
   terraform apply
   ```

3. Deploy frontend to S3:
   ```bash
   cd ../frontend
   npm install && npm run build
   aws s3 sync build/ s3://$(terraform -chdir=../terraform output -raw frontend_bucket_name)
   aws cloudfront create-invalidation \
     --distribution-id $(terraform -chdir=../terraform output -raw cloudfront_distribution_id) \
     --paths "/*"
   ```

4. Deploy backend to Lambda:
   ```bash
   cd ../backend-lambda
   ./deploy.sh \
     $(terraform -chdir=../terraform output -raw lambda_function_name) \
     $(terraform -chdir=../terraform output -raw lambda_deployment_bucket)
   ```

### AWS Cost Estimate

| Service | Monthly Cost |
|---------|--------------|
| DynamoDB | $0 (free tier: 25GB + 25 WCU/RCU) |
| Lambda | $0 (free tier: 1M requests) |
| CloudFront | $0 (free tier: 1TB transfer) |
| S3 | $0 (free tier: 5GB) |
| Secrets Manager | ~$0.40 |
| Route53 | ~$0.50 (hosted zone) |
| **Total** | **~$0.50-1/month** |

## Import Lists for Sonarr/Radarr

### Radarr (Movies)

| Endpoint | Format | Description |
|----------|--------|-------------|
| `/list/radarr` | JSON | **Recommended** - StevenLu Custom format with IMDB IDs |
| `/rss/movies` | RSS | Alternative RSS format |

**Setup:** Settings → Import Lists → Custom Lists → StevenLu Custom

### Sonarr (TV Shows)

| Endpoint | Format | Description |
|----------|--------|-------------|
| `/list/sonarr` | JSON | **Recommended** - Custom List format with TVDB IDs |
| `/rss/tv` | RSS | Alternative RSS format |

**Setup:** Settings → Import Lists → Custom Lists

### Feed Token Protection

If `FEED_TOKEN` is set, append `?token=YOUR_TOKEN` to feed URLs.

## External ID Handling

The application fetches external IDs from TMDB when items are requested:
- **Movies**: IMDB ID (for Radarr)
- **TV Shows**: TVDB ID (for Sonarr)

Items missing these IDs will show a warning indicator and won't appear in the respective feeds.

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/auth/params` | GET | Get PBKDF2 iterations for login |
| `/api/auth/verify` | POST | Verify password, returns session token |
| `/api/search` | POST | Search TMDB |
| `/api/trending` | GET | Get trending media (cached 1hr via CloudFront) |
| `/api/request` | POST | Add a request |
| `/api/request/{type}/{id}` | DELETE | Remove a request |
| `/api/requests` | GET | List all requests |
| `/api/feeds` | GET | Get feed URLs and setup info |
| `/api/health` | GET | Health check |

### Feed Endpoints

| Endpoint | Format | For |
|----------|--------|-----|
| `/list/radarr` | JSON | Radarr StevenLu Custom |
| `/list/sonarr` | JSON | Sonarr Custom Lists |
| `/rss/movies` | RSS | Radarr RSS List |
| `/rss/tv` | RSS | Generic TV RSS |
| `/rss/all` | RSS | Combined RSS |

### Webhook & Sync Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/webhook/plex?token=XXX` | POST | Plex webhook - marks requests as added |
| `/sync/library?media_type=movie&token=XXX` | POST | Bulk sync library items |

## Plex Integration

### Webhook Setup

Configure Plex to send webhooks when new media is added:

1. In Plex: Settings → Webhooks → Add Webhook
2. URL: `https://your-domain.com/webhook/plex?token=YOUR_PLEX_WEBHOOK_TOKEN`
3. Overseer will auto-mark matching requests as "Added"

The webhook also adds items to the library table, enabling "In Library" badges on search results.

### Library Sync Script

For initial library population, use the sync script on your Plex server:

```bash
cd scripts
pip install -r requirements.txt
python plex-sync.py \
  --plex-url http://localhost:32400 \
  --plex-token YOUR_PLEX_TOKEN \
  --overseer-url https://your-domain.com \
  --sync-token YOUR_PLEX_WEBHOOK_TOKEN
```

This syncs all movies and TV shows from Plex, enabling "In Library" badges even for items added before the webhook was configured.

## Project Structure

```
overseer-lite/
├── backend/              # Docker backend (SQLite)
├── backend-lambda/       # AWS Lambda backend (DynamoDB)
├── frontend/             # Svelte SPA
├── caddy/                # Caddy configs
├── terraform/            # AWS infrastructure
│   ├── main.tf
│   ├── dynamodb.tf      # DynamoDB table
│   ├── lambda.tf        # Lambda function
│   ├── frontend.tf      # S3 + CloudFront
│   ├── secrets.tf       # Secrets Manager
│   ├── waf.tf           # AWS WAF (optional)
│   └── outputs.tf
├── docker-compose.yml
└── docker-compose.prod.yml
```

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `APP_SECRET_KEY` | Application secret key | Yes |
| `PRESHARED_PASSWORD` | User access password | Yes |
| `TMDB_API_KEY` | TMDB API key | Yes |
| `FEED_TOKEN` | Token for feed endpoint auth | No |
| `PLEX_WEBHOOK_TOKEN` | Token for Plex webhook/sync endpoints | No |
| `PLEX_SERVER_NAME` | Filter webhooks to specific Plex server | No |
| `TVDB_API_KEY` | TVDB API key (for episode→show resolution) | No |
| `DOMAIN` | Your domain (for HTTPS) | Production |

## Security

- **HTTPS everywhere** - TLS 1.2+ enforced via CloudFront
- **Signed session tokens** - HMAC-SHA256 with 30-day expiry
- **Secrets Manager** - API keys stored securely
- **Private S3** - Frontend only accessible via CloudFront
- **WAF (optional)** - Rate limiting and threat protection (~$8/month extra)

## Feed Format Details

### Radarr JSON (StevenLu Custom)
```json
[
  {"title": "Movie Name (2023)", "imdb_id": "tt1234567"},
  {"title": "Another Movie (2024)", "imdb_id": "tt7654321"}
]
```

### Sonarr JSON (Custom Lists)
```json
[
  {"tvdbId": "75837"},
  {"tvdbId": "77847"}
]
```

## Sources

- [Radarr StevenLu Custom Lists](https://wiki.servarr.com/radarr/supported)
- [Sonarr Custom Lists PR #5160](https://github.com/Sonarr/Sonarr/pull/5160)

## License

MIT
