# Overseer Lite

A lightweight media request system that generates RSS feeds compatible with Sonarr and Radarr. Users can search for TV shows and movies via TMDB and add them to request lists, which are then exposed as RSS feeds.

## Features

- **Simple Authentication**: Preshared password protection
- **TMDB Integration**: Search movies and TV shows using The Movie Database
- **RSS Feeds**: Sonarr and Radarr compatible RSS feeds for automated media acquisition
- **Modern UI**: Svelte-based responsive frontend
- **Docker Ready**: Full Docker Compose setup with optional SSL

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Browser   │────▶│    Nginx    │────▶│  Frontend   │
│             │     │  (Reverse   │     │  (Svelte)   │
└─────────────┘     │   Proxy)    │     └─────────────┘
                    │             │
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
   DOMAIN=your-domain.com
   EMAIL=your-email@example.com
   ```

4. Start the application:
   ```bash
   # Without SSL (development/local)
   docker compose up -d

   # With SSL (production)
   ./init-letsencrypt.sh
   docker compose -f docker-compose.ssl.yml up -d
   ```

5. Access the application at `http://localhost` (or `https://your-domain.com` with SSL)

## RSS Feeds

Once you've added media requests, the following RSS feeds are available:

| Feed | URL | Compatible With |
|------|-----|-----------------|
| Movies | `/rss/movies` | Radarr |
| TV Shows | `/rss/tv` | Sonarr |
| All | `/rss/all` | Both |

### Configuring Sonarr

1. Go to Settings → Import Lists
2. Add a new RSS List
3. Enter the TV RSS URL: `https://your-domain.com/rss/tv`
4. Configure your preferred settings

### Configuring Radarr

1. Go to Settings → Import Lists
2. Add a new RSS List
3. Enter the Movies RSS URL: `https://your-domain.com/rss/movies`
4. Configure your preferred settings

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/auth/verify` | POST | Verify password |
| `/api/search` | POST | Search TMDB |
| `/api/trending` | GET | Get trending media |
| `/api/request` | POST | Add a request |
| `/api/request/{type}/{id}` | DELETE | Remove a request |
| `/api/requests` | GET | List all requests |
| `/api/health` | GET | Health check |

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

| Variable | Description | Default |
|----------|-------------|---------|
| `APP_SECRET_KEY` | Application secret key | `change-me-in-production` |
| `PRESHARED_PASSWORD` | User access password | `changeme` |
| `TMDB_API_KEY` | TMDB API key | Required |
| `DOMAIN` | Your domain (for SSL) | Required for SSL |
| `EMAIL` | Email for Let's Encrypt | Required for SSL |
| `LETSENCRYPT_ENV` | `staging` or `production` | `production` |

## Project Structure

```
overseer-lite/
├── backend/
│   ├── main.py           # FastAPI application
│   ├── config.py         # Configuration
│   ├── database.py       # SQLite database
│   ├── tmdb.py           # TMDB API client
│   ├── rss.py            # RSS feed generation
│   ├── requirements.txt  # Python dependencies
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── lib/          # Stores and API client
│   │   └── routes/       # Svelte pages
│   ├── package.json
│   └── Dockerfile
├── nginx/
│   ├── nginx.conf        # Development config
│   └── nginx-ssl.conf    # Production SSL config
├── docker-compose.yml         # Development compose
├── docker-compose.ssl.yml     # Production compose with SSL
├── init-letsencrypt.sh        # SSL certificate setup
└── .env.example
```

## License

MIT
