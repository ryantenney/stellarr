---
title: Docker Deployment
description: Self-host Stellarr with Docker Compose for both development and production.
---

The easiest way to self-host Stellarr is with Docker Compose. This guide covers both development and production setups.

## Prerequisites

- Docker and Docker Compose
- TMDB API Key (free at [themoviedb.org](https://www.themoviedb.org/settings/api))

## Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/ryantenney/stellarr.git
cd stellarr
```

### 2. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` with your settings:

```bash
# Required
APP_SECRET_KEY=your-secret-key-here      # Generate with: openssl rand -hex 32
PRESHARED_PASSWORD=your-password          # Password users will enter
TMDB_API_KEY=your-tmdb-api-key

# Optional
FEED_TOKEN=your-feed-token                # Protect list endpoints
PLEX_WEBHOOK_TOKEN=your-webhook-token     # Protect Plex webhook
```

### 3. Start the Application

**Development (HTTP only):**

```bash
docker compose up -d
```

Access at `http://localhost`

**Production (with automatic HTTPS):**

```bash
# Set your domain in .env
DOMAIN=stellarr.example.com

docker compose -f docker-compose.prod.yml up -d
```

Caddy will automatically obtain and renew SSL certificates via Let's Encrypt.

## Docker Compose Files

### Development (`docker-compose.yml`)

- HTTP only on port 80
- Hot reload for development
- SQLite database in `./data`

### Production (`docker-compose.prod.yml`)

- Automatic HTTPS via Caddy
- SSL certificate management
- Production-ready configuration

## Directory Structure

After starting, the following directories are created:

```
stellarr/
├── data/
│   └── stellarr.db     # SQLite database
└── caddy_data/          # SSL certificates (production)
```

## Updating

```bash
git pull
docker compose down
docker compose up -d --build
```

## Troubleshooting

### Port 80/443 Already in Use

Check for other services:

```bash
sudo lsof -i :80
sudo lsof -i :443
```

### Permission Issues with Data Directory

```bash
sudo chown -R 1000:1000 ./data
```

### View Logs

```bash
docker compose logs -f backend
docker compose logs -f caddy
```

## Next Steps

- [Configure environment variables](/docs/guides/configuration/)
- [Set up Plex integration](/docs/integrations/plex/)
- [Configure Sonarr & Radarr](/docs/integrations/sonarr-radarr/)
