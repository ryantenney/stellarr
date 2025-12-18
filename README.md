# Overseer Lite

A lightweight media request system that generates feeds compatible with Sonarr and Radarr. Users can search for TV shows and movies via TMDB and add them to request lists, which are exposed as import list endpoints.

## Features

- **Simple Authentication**: Preshared password protection for the web UI
- **TMDB Integration**: Search movies and TV shows using The Movie Database
- **Sonarr/Radarr Import Lists**: Native JSON formats for direct import
- **Feed Token Protection**: Optional token-based auth for feed endpoints
- **Modern UI**: Svelte-based responsive frontend
- **Docker Ready**: Full Docker Compose setup with automatic HTTPS via Caddy

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Browser   │────▶│    Caddy    │────▶│  Frontend   │
│             │     │  (Reverse   │     │  (Svelte)   │
└─────────────┘     │   Proxy +   │     └─────────────┘
                    │   HTTPS)    │
                    │             │     ┌─────────────┐
                    │             │────▶│   Backend   │
                    └─────────────┘     │  (FastAPI)  │
                                        └──────┬──────┘
                                               │
                                        ┌──────▼──────┐
                                        │   SQLite    │
                                        │  Database   │
                                        └─────────────┘
```

## Quick Start

### Prerequisites

- Docker and Docker Compose
- TMDB API Key (get one free at https://www.themoviedb.org/settings/api)

### Setup

1. Clone the repository:
   ```bash
   git clone <repo-url>
   cd overseer-lite
   ```

2. Create your environment file:
   ```bash
   cp .env.example .env
   ```

3. Edit `.env` with your settings:
   ```env
   APP_SECRET_KEY=your-random-secret-key
   PRESHARED_PASSWORD=your-password
   TMDB_API_KEY=your-tmdb-api-key
   FEED_TOKEN=your-feed-token      # Optional: protects feed endpoints
   DOMAIN=your-domain.com          # For production with HTTPS
   ```

4. Start the application:
   ```bash
   # Development (HTTP only)
   docker compose up -d

   # Production (automatic HTTPS via Caddy)
   docker compose -f docker-compose.prod.yml up -d
   ```

5. Access the application at `http://localhost` (or `https://your-domain.com` in production)

## Import Lists for Sonarr/Radarr

The recommended endpoints use native JSON formats supported by Sonarr and Radarr:

### Radarr (Movies)

| Endpoint | Format | Description |
|----------|--------|-------------|
| `/list/radarr` | JSON | **Recommended** - StevenLu Custom format with IMDB IDs |
| `/rss/movies` | RSS | Alternative RSS format |

**Setup in Radarr:**
1. Go to Settings → Import Lists → Add
2. Select "Custom Lists" → "StevenLu Custom"
3. Enter URL: `https://your-domain.com/list/radarr?token=YOUR_TOKEN`

### Sonarr (TV Shows)

| Endpoint | Format | Description |
|----------|--------|-------------|
| `/list/sonarr` | JSON | **Recommended** - Custom List format with TVDB IDs |
| `/rss/tv` | RSS | Alternative RSS format |

**Setup in Sonarr:**
1. Go to Settings → Import Lists → Add
2. Select "Custom Lists"
3. Enter URL: `https://your-domain.com/list/sonarr?token=YOUR_TOKEN`

### Feed Token

If `FEED_TOKEN` is set in your environment, all feed endpoints require authentication:
```
/list/radarr?token=YOUR_FEED_TOKEN
/list/sonarr?token=YOUR_FEED_TOKEN
/rss/movies?token=YOUR_FEED_TOKEN
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/auth/verify` | POST | Verify password |
| `/api/search` | POST | Search TMDB |
| `/api/trending` | GET | Get trending media |
| `/api/request` | POST | Add a request |
| `/api/request/{type}/{id}` | DELETE | Remove a request |
| `/api/requests` | GET | List all requests |
| `/api/feeds` | GET | Get feed URLs and info |
| `/api/health` | GET | Health check |

### Import List Endpoints

| Endpoint | Format | For |
|----------|--------|-----|
| `/list/radarr` | JSON | Radarr StevenLu Custom |
| `/list/sonarr` | JSON | Sonarr Custom Lists |
| `/rss/movies` | RSS | Radarr RSS List |
| `/rss/tv` | RSS | Generic TV RSS |
| `/rss/all` | RSS | Combined RSS |

## Development

### Backend Development

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

### Frontend Development

```bash
cd frontend
npm install
npm run dev
```

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `APP_SECRET_KEY` | Application secret key | Yes |
| `PRESHARED_PASSWORD` | User access password | Yes |
| `TMDB_API_KEY` | TMDB API key | Yes |
| `FEED_TOKEN` | Token for feed endpoint auth | No |
| `DOMAIN` | Your domain (for HTTPS) | Production |

## Project Structure

```
overseer-lite/
├── backend/
│   ├── main.py           # FastAPI application
│   ├── config.py         # Configuration
│   ├── database.py       # SQLite database
│   ├── tmdb.py           # TMDB API client
│   ├── rss.py            # Feed generation
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── lib/          # Stores and API client
│   │   └── routes/       # Svelte pages
│   ├── package.json
│   └── Dockerfile
├── caddy/
│   ├── Caddyfile         # Production config (auto HTTPS)
│   └── Caddyfile.dev.json # Development config
├── docker-compose.yml         # Development
├── docker-compose.prod.yml    # Production with HTTPS
└── .env.example
```

## Feed Format Details

### Radarr JSON Format (StevenLu Custom)
```json
[
  {"title": "Movie Name (2023)", "imdb_id": "tt1234567"},
  {"title": "Another Movie (2024)", "imdb_id": "tt7654321"}
]
```

### Sonarr JSON Format (Custom Lists)
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
