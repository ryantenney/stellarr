<div align="center">

# Stellarr

**A lightweight media request system for Sonarr & Radarr — no open ports required.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/Docker-Supported-2496ED?logo=docker&logoColor=white)](docker-compose.yml)
[![AWS Lambda](https://img.shields.io/badge/AWS-Serverless-FF9900?logo=amazonaws&logoColor=white)](terraform/)
[![Plex](https://img.shields.io/badge/Plex-Integrated-E5A00D?logo=plex&logoColor=white)](README.md#plex-integration)

</div>

---

A self-hosted alternative to Overseerr that keeps things simple. Search TMDB for movies and TV shows, add them to request lists, and let Sonarr/Radarr pull them in via native import list endpoints. Runs fully serverless on AWS for under a dollar a month — no servers to maintain, no ports to open. A Docker Compose option is also available for local or self-hosted setups.

### Highlights

- **No open ports** — Caddy auto-HTTPS or CloudFront handles TLS, nothing exposed
- **Native import lists** — Sonarr and Radarr pull directly, no webhooks or middleware
- **Plex integration** — auto-marks requests as added, syncs "In Library" badges
- **Push notifications** — web push alerts when requested media lands in your library
- **PWA support** — installable on iOS and Android with proper icons
- **Localized** — English, Spanish, French, German (auto-detects browser language)
- **Two deployment paths** — Docker Compose or AWS serverless (Lambda + DynamoDB + CloudFront)

---

## Deployment Options

<details>
<summary><strong>Architecture: Docker</strong></summary>

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

</details>

<details>
<summary><strong>Architecture: AWS Serverless (Low Cost)</strong></summary>

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

</details>

---

## Quick Start: AWS Serverless

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

3. Deploy application:
   ```bash
   cd ..
   ./deploy.sh              # Deploy everything (terraform, backend, frontend)
   ./deploy.sh --skip-tf    # Skip terraform, deploy backend + frontend only
   ./deploy.sh --backend    # Backend Lambda only
   ./deploy.sh --frontend   # Frontend + CloudFront invalidation only
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

---

## Quick Start: Docker

### Prerequisites

- Docker and Docker Compose
- TMDB API Key (free at https://www.themoviedb.org/settings/api)

### Setup

1. Clone and configure:
   ```bash
   git clone <repo-url>
   cd stellarr
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

---

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

### External ID Handling

The application fetches external IDs from TMDB when items are requested:
- **Movies**: IMDB ID (for Radarr)
- **TV Shows**: TVDB ID (for Sonarr)

Items missing these IDs will show a warning indicator and won't appear in the respective feeds.

---

## Plex Integration

### Webhook Setup

Configure Plex to send webhooks when new media is added:

1. In Plex: Settings → Webhooks → Add Webhook
2. URL: `https://your-domain.com/webhook/plex?token=YOUR_PLEX_WEBHOOK_TOKEN`
3. Stellarr will auto-mark matching requests as "Added"

The webhook also adds items to the library table, enabling "In Library" badges on search results.

### Library Sync Script

For initial library population, use the sync script on your Plex server:

```bash
cd scripts
pip install -r requirements.txt
python plex-sync.py \
  --plex-url http://localhost:32400 \
  --plex-token YOUR_PLEX_TOKEN \
  --stellarr-url https://your-domain.com \
  --sync-token YOUR_PLEX_WEBHOOK_TOKEN
```

This syncs all movies and TV shows from Plex, enabling "In Library" badges even for items added before the webhook was configured.

---

## Security

- **HTTPS everywhere** — TLS 1.2+ enforced via CloudFront
- **Signed session tokens** — HMAC-SHA256 with 30-day expiry
- **Secrets Manager** — API keys stored securely
- **Private S3** — Frontend only accessible via CloudFront
- **WAF (optional)** — Rate limiting and threat protection (~$8/month extra)

---

<details>
<summary><strong>API Reference</strong></summary>

### Core Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/auth/params` | GET | Get PBKDF2 iterations for login |
| `/api/auth/verify` | POST | Verify password, returns session token |
| `/api/search` | POST | Search TMDB |
| `/api/library-status` | GET | Get library IDs and pending requests |
| `/api/request` | POST | Add a request |
| `/api/request/{type}/{id}` | DELETE | Remove a request |
| `/api/requests` | GET | List all requests |
| `/api/feeds` | GET | Get feed URLs and setup info |
| `/api/health` | GET | Health check |
| `/trending-{type}-{locale}.json` | GET | Trending media (static S3, 1hr cache) |

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

</details>

<details>
<summary><strong>Environment Variables</strong></summary>

| Variable | Description | Required |
|----------|-------------|----------|
| `APP_SECRET_KEY` | Application secret key | Yes |
| `PRESHARED_PASSWORD` | User access password | Yes |
| `TMDB_API_KEY` | TMDB API key | Yes |
| `FEED_TOKEN` | Token for feed endpoint auth | No |
| `PLEX_WEBHOOK_TOKEN` | Token for Plex webhook/sync endpoints | No |
| `PLEX_SERVER_NAME` | Filter webhooks to specific Plex server | No |
| `TVDB_API_KEY` | TVDB API key (resolves episode webhooks to parent show) | No |
| `DOMAIN` | Your domain (for HTTPS) | Production |

</details>

<details>
<summary><strong>Project Structure</strong></summary>

```
stellarr/
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

</details>

<details>
<summary><strong>Feed Format Details</strong></summary>

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

</details>

---

## Sources

- [Radarr StevenLu Custom Lists](https://wiki.servarr.com/radarr/supported)
- [Sonarr Custom Lists PR #5160](https://github.com/Sonarr/Sonarr/pull/5160)

## License

MIT
