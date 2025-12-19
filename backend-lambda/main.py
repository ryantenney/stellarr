from fastapi import FastAPI, HTTPException, Depends, Request, Response, Query, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from contextlib import asynccontextmanager
from mangum import Mangum
import secrets
import hmac
import hashlib
import base64
import time
import logging
import os

print("DEBUG: Starting main.py module load...", flush=True)

from config import get_settings
print("DEBUG: Config module imported", flush=True)

from database import init_db, add_request, remove_request, get_all_requests, is_requested
print("DEBUG: Database module imported", flush=True)
from tmdb import tmdb_client
from rss import (
    generate_movie_rss,
    generate_tv_rss,
    generate_combined_rss,
    generate_radarr_json,
    generate_sonarr_json,
)


settings = get_settings()

# Initialize database once at module load (not on every request)
_db_initialized = False

def ensure_db_initialized():
    """Initialize database tables once per Lambda instance."""
    global _db_initialized
    if not _db_initialized:
        print("DEBUG: Initializing database (first time for this Lambda instance)...", flush=True)
        start = time.time()
        try:
            init_db()
            print(f"DEBUG: Database initialized successfully in {time.time() - start:.2f}s", flush=True)
            _db_initialized = True
        except Exception as e:
            print(f"DEBUG: Database initialization failed after {time.time() - start:.2f}s: {type(e).__name__}: {e}", flush=True)
            raise

# Session duration: 30 days in seconds
SESSION_DURATION_SECONDS = 30 * 24 * 60 * 60


def create_session_token() -> str:
    """Create a signed session token with timestamp."""
    timestamp = str(int(time.time()))
    signature = hmac.new(
        settings.app_secret_key.encode(),
        timestamp.encode(),
        hashlib.sha256
    ).digest()
    sig_b64 = base64.urlsafe_b64encode(signature).decode().rstrip("=")
    return f"{timestamp}.{sig_b64}"


def verify_session_token(authorization: str | None = Header(None, alias="Authorization")) -> bool:
    """Verify the session token from Authorization header."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")

    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid authorization format")

    token = parts[1]

    try:
        timestamp_str, sig_b64 = token.split(".", 1)
        timestamp = int(timestamp_str)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=401, detail="Invalid token format")

    if time.time() - timestamp > SESSION_DURATION_SECONDS:
        raise HTTPException(status_code=401, detail="Session expired")

    expected_sig = hmac.new(
        settings.app_secret_key.encode(),
        timestamp_str.encode(),
        hashlib.sha256
    ).digest()
    expected_b64 = base64.urlsafe_b64encode(expected_sig).decode().rstrip("=")

    if not secrets.compare_digest(sig_b64, expected_b64):
        raise HTTPException(status_code=401, detail="Invalid token")

    return True


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan handler - DB init moved to module level for Lambda."""
    yield


app = FastAPI(
    title="Overseer Lite",
    description="A lightweight media request system with RSS feeds for Sonarr/Radarr",
    version="1.0.0",
    lifespan=lifespan
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    print(f"DEBUG: REQUEST START - {request.method} {request.url.path}", flush=True)
    try:
        response = await call_next(request)
        duration = time.time() - start_time
        print(f"DEBUG: REQUEST END - {request.method} {request.url.path} - Status: {response.status_code} - Duration: {duration:.2f}s", flush=True)
        return response
    except Exception as e:
        duration = time.time() - start_time
        print(f"DEBUG: REQUEST ERROR - {request.method} {request.url.path} - Error: {type(e).__name__}: {e} - Duration: {duration:.2f}s", flush=True)
        raise


# --- Auth Helpers ---

def get_base_url(request: Request) -> str:
    """Get the base URL from environment variable (set by Terraform) or fallback."""
    # Use BASE_URL env var set by Terraform (preferred for CloudFront)
    base_url = os.environ.get("BASE_URL")
    if base_url:
        return base_url.rstrip("/")
    return str(request.base_url).rstrip("/")


def verify_feed_token(token: str | None = Query(None, alias="token")):
    """Verify the feed token for RSS/list endpoints."""
    if not settings.feed_token:
        return True

    if not token:
        raise HTTPException(
            status_code=401,
            detail="Feed token required. Add ?token=YOUR_TOKEN to the URL."
        )

    if not secrets.compare_digest(token, settings.feed_token):
        raise HTTPException(status_code=401, detail="Invalid feed token")

    return True


# --- Auth ---

class PasswordCheck(BaseModel):
    password: str


@app.post("/api/auth/verify")
def verify_auth(data: PasswordCheck):
    """Verify the preshared password and return a session token."""
    if secrets.compare_digest(data.password, settings.preshared_password):
        token = create_session_token()
        return {"valid": True, "token": token}
    raise HTTPException(status_code=401, detail="Invalid password")


# --- Search ---

class SearchQuery(BaseModel):
    query: str
    media_type: str | None = None
    page: int = 1


@app.post("/api/search")
async def search(data: SearchQuery, _: bool = Depends(verify_session_token)):
    """Search TMDB for movies and TV shows."""
    try:
        if data.media_type == "movie":
            results = await tmdb_client.search_movie(data.query, data.page)
        elif data.media_type == "tv":
            results = await tmdb_client.search_tv(data.query, data.page)
        else:
            results = await tmdb_client.search_multi(data.query, data.page)

        filtered_results = []
        for item in results.get("results", []):
            if item.get("media_type") == "person":
                continue

            media_type = item.get("media_type", data.media_type or "movie")
            tmdb_id = item.get("id")

            if media_type == "tv":
                title = item.get("name", "Unknown")
                year = item.get("first_air_date", "")[:4] if item.get("first_air_date") else None
            else:
                title = item.get("title", "Unknown")
                year = item.get("release_date", "")[:4] if item.get("release_date") else None

            requested = is_requested(tmdb_id, media_type)

            filtered_results.append({
                "id": tmdb_id,
                "title": title,
                "year": int(year) if year else None,
                "overview": item.get("overview"),
                "poster_path": item.get("poster_path"),
                "media_type": media_type,
                "vote_average": item.get("vote_average"),
                "requested": requested
            })

        return {
            "results": filtered_results,
            "page": results.get("page", 1),
            "total_pages": results.get("total_pages", 1),
            "total_results": results.get("total_results", 0)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- Requests ---

class MediaRequest(BaseModel):
    tmdb_id: int
    media_type: str


@app.post("/api/request")
async def create_request(data: MediaRequest, _: bool = Depends(verify_session_token)):
    """Add a media item to the request list."""
    try:
        if data.media_type == "movie":
            details = await tmdb_client.get_movie(data.tmdb_id)
            title = details.get("title", "Unknown")
            year = details.get("release_date", "")[:4] if details.get("release_date") else None
            imdb_id = details.get("external_ids", {}).get("imdb_id")
            tvdb_id = None
        else:
            details = await tmdb_client.get_tv(data.tmdb_id)
            title = details.get("name", "Unknown")
            year = details.get("first_air_date", "")[:4] if details.get("first_air_date") else None
            imdb_id = details.get("external_ids", {}).get("imdb_id")
            tvdb_id = details.get("external_ids", {}).get("tvdb_id")

        success = add_request(
            tmdb_id=data.tmdb_id,
            media_type=data.media_type,
            title=title,
            year=int(year) if year else None,
            overview=details.get("overview"),
            poster_path=details.get("poster_path"),
            imdb_id=imdb_id,
            tvdb_id=tvdb_id
        )

        if success:
            return {"success": True, "message": f"Added {title} to requests"}
        else:
            return {"success": False, "message": "Item may already be requested"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/request/{media_type}/{tmdb_id}")
def delete_request(media_type: str, tmdb_id: int, _: bool = Depends(verify_session_token)):
    """Remove a media item from the request list."""
    success = remove_request(tmdb_id, media_type)
    if success:
        return {"success": True, "message": "Request removed"}
    raise HTTPException(status_code=404, detail="Request not found")


@app.get("/api/requests")
def list_requests(media_type: str | None = None, _: bool = Depends(verify_session_token)):
    """Get all requests, optionally filtered by media type."""
    requests = get_all_requests(media_type)
    return {"requests": requests}


# --- Trending/Popular ---

@app.get("/api/trending")
async def get_trending(media_type: str = "all", _: bool = Depends(verify_session_token)):
    """Get trending movies/TV shows."""
    try:
        results = await tmdb_client.get_trending(media_type)

        items = []
        for item in results.get("results", []):
            item_type = item.get("media_type", media_type if media_type != "all" else "movie")
            tmdb_id = item.get("id")

            if item_type == "tv":
                title = item.get("name", "Unknown")
                year = item.get("first_air_date", "")[:4] if item.get("first_air_date") else None
            else:
                title = item.get("title", "Unknown")
                year = item.get("release_date", "")[:4] if item.get("release_date") else None

            requested = is_requested(tmdb_id, item_type)

            items.append({
                "id": tmdb_id,
                "title": title,
                "year": int(year) if year else None,
                "overview": item.get("overview"),
                "poster_path": item.get("poster_path"),
                "media_type": item_type,
                "vote_average": item.get("vote_average"),
                "requested": requested
            })

        return {"results": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- RSS Feeds ---

@app.get("/rss/movies")
def rss_movies(request: Request, _: bool = Depends(verify_feed_token)):
    """RSS feed for movie requests (Radarr compatible)."""
    base_url = get_base_url(request)
    xml = generate_movie_rss(base_url)
    return Response(content=xml, media_type="application/rss+xml")


@app.get("/rss/tv")
def rss_tv(request: Request, _: bool = Depends(verify_feed_token)):
    """RSS feed for TV show requests."""
    base_url = get_base_url(request)
    xml = generate_tv_rss(base_url)
    return Response(content=xml, media_type="application/rss+xml")


@app.get("/rss/all")
def rss_all(request: Request, _: bool = Depends(verify_feed_token)):
    """Combined RSS feed for all requests."""
    base_url = get_base_url(request)
    xml = generate_combined_rss(base_url)
    return Response(content=xml, media_type="application/rss+xml")


# --- JSON Lists ---

@app.get("/list/radarr")
def list_radarr(_: bool = Depends(verify_feed_token)):
    """Radarr StevenLu Custom list format (JSON)."""
    return generate_radarr_json()


@app.get("/list/sonarr")
def list_sonarr(_: bool = Depends(verify_feed_token)):
    """Sonarr Custom List format (JSON)."""
    return generate_sonarr_json()


# --- Feed Info ---

@app.get("/api/feeds")
def get_feed_info(request: Request):
    """Get information about available feeds and their URLs."""
    base_url = get_base_url(request)
    token_required = bool(settings.feed_token)
    token_param = "?token=YOUR_FEED_TOKEN" if token_required else ""

    return {
        "token_required": token_required,
        "feeds": {
            "radarr": {
                "name": "Radarr (Movies)",
                "description": "StevenLu Custom JSON format - RECOMMENDED for Radarr",
                "url": f"{base_url}/list/radarr{token_param}",
                "format": "json",
                "setup": "Settings -> Import Lists -> Custom Lists -> StevenLu Custom"
            },
            "radarr_rss": {
                "name": "Radarr RSS (Movies)",
                "description": "RSS format with IMDB IDs",
                "url": f"{base_url}/rss/movies{token_param}",
                "format": "rss",
                "setup": "Settings -> Import Lists -> Custom Lists -> RSS List"
            },
            "sonarr": {
                "name": "Sonarr (TV Shows)",
                "description": "Custom List JSON format with TVDB IDs - RECOMMENDED for Sonarr",
                "url": f"{base_url}/list/sonarr{token_param}",
                "format": "json",
                "setup": "Settings -> Import Lists -> Add -> Custom Lists"
            },
            "tv_rss": {
                "name": "TV Shows RSS",
                "description": "RSS format for TV shows",
                "url": f"{base_url}/rss/tv{token_param}",
                "format": "rss"
            },
            "all_rss": {
                "name": "All Media RSS",
                "description": "Combined RSS feed for all requests",
                "url": f"{base_url}/rss/all{token_param}",
                "format": "rss"
            }
        }
    }


# --- Health Check ---

@app.get("/api/health")
def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "overseer-lite"}


# Initialize database once per Lambda instance (at module load, not per request)
print("DEBUG: About to initialize database at module load time...", flush=True)
ensure_db_initialized()
print("DEBUG: Module load complete, handler ready", flush=True)

# Lambda handler - lifespan="off" since we handle init at module level
handler = Mangum(app, lifespan="off")
