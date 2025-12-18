from fastapi import FastAPI, HTTPException, Depends, Request, Response, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from contextlib import asynccontextmanager
import secrets

from config import get_settings
from database import init_db, add_request, remove_request, get_all_requests, is_requested
from tmdb import tmdb_client
from rss import (
    generate_movie_rss,
    generate_tv_rss,
    generate_combined_rss,
    generate_radarr_json,
    generate_sonarr_json,
)


settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup."""
    await init_db()
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


# --- Auth Helpers ---

def verify_feed_token(token: str | None = Query(None, alias="token")):
    """Verify the feed token for RSS/list endpoints."""
    if not settings.feed_token:
        # No token configured, allow access
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
async def verify_auth(data: PasswordCheck):
    """Verify the preshared password."""
    if secrets.compare_digest(data.password, settings.preshared_password):
        return {"valid": True}
    raise HTTPException(status_code=401, detail="Invalid password")


# --- Search ---

class SearchQuery(BaseModel):
    query: str
    media_type: str | None = None  # "movie", "tv", or None for multi
    page: int = 1


@app.post("/api/search")
async def search(data: SearchQuery):
    """Search TMDB for movies and TV shows."""
    try:
        if data.media_type == "movie":
            results = await tmdb_client.search_movie(data.query, data.page)
        elif data.media_type == "tv":
            results = await tmdb_client.search_tv(data.query, data.page)
        else:
            results = await tmdb_client.search_multi(data.query, data.page)

        # Filter out person results and add requested status
        filtered_results = []
        for item in results.get("results", []):
            if item.get("media_type") == "person":
                continue

            media_type = item.get("media_type", data.media_type or "movie")
            tmdb_id = item.get("id")

            # Determine title and year
            if media_type == "tv":
                title = item.get("name", "Unknown")
                year = item.get("first_air_date", "")[:4] if item.get("first_air_date") else None
            else:
                title = item.get("title", "Unknown")
                year = item.get("release_date", "")[:4] if item.get("release_date") else None

            requested = await is_requested(tmdb_id, media_type)

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
    media_type: str  # "movie" or "tv"


@app.post("/api/request")
async def create_request(data: MediaRequest):
    """Add a media item to the request list."""
    try:
        # Get full details from TMDB
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

        success = await add_request(
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
async def delete_request(media_type: str, tmdb_id: int):
    """Remove a media item from the request list."""
    success = await remove_request(tmdb_id, media_type)
    if success:
        return {"success": True, "message": "Request removed"}
    raise HTTPException(status_code=404, detail="Request not found")


@app.get("/api/requests")
async def list_requests(media_type: str | None = None):
    """Get all requests, optionally filtered by media type."""
    requests = await get_all_requests(media_type)
    return {"requests": requests}


# --- Trending/Popular ---

@app.get("/api/trending")
async def get_trending(media_type: str = "all"):
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

            requested = await is_requested(tmdb_id, item_type)

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


# --- RSS Feeds (protected by token) ---

@app.get("/rss/movies")
async def rss_movies(request: Request, _: bool = Depends(verify_feed_token)):
    """
    RSS feed for movie requests (Radarr compatible).

    Add ?token=YOUR_FEED_TOKEN if FEED_TOKEN is configured.
    """
    base_url = str(request.base_url).rstrip("/")
    xml = await generate_movie_rss(base_url)
    return Response(content=xml, media_type="application/rss+xml")


@app.get("/rss/tv")
async def rss_tv(request: Request, _: bool = Depends(verify_feed_token)):
    """
    RSS feed for TV show requests.

    NOTE: Sonarr does not support RSS import lists natively.
    Consider using /list/radarr for Radarr's StevenLu Custom format.
    """
    base_url = str(request.base_url).rstrip("/")
    xml = await generate_tv_rss(base_url)
    return Response(content=xml, media_type="application/rss+xml")


@app.get("/rss/all")
async def rss_all(request: Request, _: bool = Depends(verify_feed_token)):
    """Combined RSS feed for all requests."""
    base_url = str(request.base_url).rstrip("/")
    xml = await generate_combined_rss(base_url)
    return Response(content=xml, media_type="application/rss+xml")


# --- JSON Lists (for Radarr StevenLu Custom format) ---

@app.get("/list/radarr")
async def list_radarr(_: bool = Depends(verify_feed_token)):
    """
    Radarr StevenLu Custom list format (JSON).

    This is the RECOMMENDED format for Radarr import lists.
    Uses IMDB IDs for accurate matching.

    In Radarr: Settings -> Import Lists -> Add -> Custom Lists -> StevenLu Custom
    URL: https://your-domain.com/list/radarr?token=YOUR_TOKEN
    """
    return await generate_radarr_json()


@app.get("/list/sonarr")
async def list_sonarr(_: bool = Depends(verify_feed_token)):
    """
    Sonarr Custom List format (JSON).

    Uses TVDB IDs for accurate matching.
    See: https://github.com/Sonarr/Sonarr/pull/5160

    In Sonarr: Settings -> Import Lists -> Add -> Custom Lists
    URL: https://your-domain.com/list/sonarr?token=YOUR_TOKEN
    """
    return await generate_sonarr_json()


# --- Feed Info Endpoint ---

@app.get("/api/feeds")
async def get_feed_info(request: Request):
    """Get information about available feeds and their URLs."""
    base_url = str(request.base_url).rstrip("/")
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
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "overseer-lite"}
