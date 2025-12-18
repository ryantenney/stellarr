# Overseer Lite

A lightweight media request system that generates feeds compatible with Sonarr and Radarr. Users can search for TV shows and movies via TMDB and add them to request lists, which are exposed as import list endpoints.

## Features

- **Simple Authentication**: Preshared password protection for the web UI
- **TMDB Integration**: Search movies and TV shows using The Movie Database
- **Sonarr/Radarr Import Lists**: Native JSON formats for direct import
- **Feed Token Protection**: Optional token-based auth for feed endpoints
- **Missing ID Warnings**: UI indicators when external IDs (IMDB/TVDB) are missing
- **Modern UI**: Svelte-based responsive frontend
- **Multiple Deployment Options**:
  - Docker Compose with Caddy (auto HTTPS)
  - AWS Serverless (Lambda + Aurora Serverless + CloudFront)

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

### Option 2: AWS Serverless

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Browser   │────▶│ CloudFront  │────▶│  S3 Bucket  │
│             │     │    (CDN)    │     │ (Frontend)  │
└─────────────┘     │             │     └─────────────┘
                    │             │     ┌─────────────┐
                    │             │────▶│   Lambda    │
                    └─────────────┘     │  (FastAPI)  │
                                        └──────┬──────┘
                                        ┌──────▼──────┐
                                        │   Aurora    │
                                        │ Serverless  │
                                        │ PostgreSQL  │
                                        └─────────────┘
```

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

### Setup

1. Configure Terraform variables:
   ```bash
   cd terraform
   cp terraform.tfvars.example terraform.tfvars
   # Edit terraform.tfvars
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
   aws cloudfront create-invalidation --distribution-id $(terraform -chdir=../terraform output -raw cloudfront_distribution_id) --paths "/*"
   ```

4. Deploy backend to Lambda:
   ```bash
   cd ../backend-lambda
   ./deploy.sh $(terraform -chdir=../terraform output -raw lambda_function_name) your-deployment-bucket
   ```

### AWS Cost Estimate

With minimal usage:
- **Aurora Serverless v2**: ~$0.12/ACU-hour (scales to near-zero when idle)
- **Lambda**: Free tier covers most small deployments
- **CloudFront**: ~$0.085/GB transfer
- **S3**: Negligible for static hosting

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
| `/api/auth/verify` | POST | Verify password |
| `/api/search` | POST | Search TMDB |
| `/api/trending` | GET | Get trending media |
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

## Project Structure

```
overseer-lite/
├── backend/              # Docker backend (SQLite)
├── backend-lambda/       # AWS Lambda backend (PostgreSQL)
├── frontend/             # Svelte SPA
├── caddy/                # Caddy configs
├── terraform/            # AWS infrastructure
│   ├── main.tf
│   ├── vpc.tf           # VPC for Aurora
│   ├── aurora.tf        # Aurora Serverless v2
│   ├── lambda.tf        # Lambda function
│   ├── frontend.tf      # S3 + CloudFront
│   ├── secrets.tf       # Secrets Manager
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
| `DOMAIN` | Your domain (for HTTPS) | Production |

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
