from fastapi import FastAPI, HTTPException, Depends, Request, Response, Query, Header, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from contextlib import asynccontextmanager
import asyncio
import secrets
import hmac
import hashlib
import base64
import time

from config import get_settings
from database import (
    init_db, add_request, remove_request, get_all_requests, is_requested,
    mark_as_added, find_by_tvdb_id, find_by_plex_guid, update_plex_guid,
    sync_library, is_in_library
)
import json
from tmdb import tmdb_client
from rss import (
    generate_movie_rss,
    generate_tv_rss,
    generate_combined_rss,
    generate_radarr_json,
    generate_sonarr_json,
)


settings = get_settings()

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

    # Expect "Bearer <token>"
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid authorization format")

    token = parts[1]

    try:
        timestamp_str, sig_b64 = token.split(".", 1)
        timestamp = int(timestamp_str)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=401, detail="Invalid token format")

    # Check if expired
    if time.time() - timestamp > SESSION_DURATION_SECONDS:
        raise HTTPException(status_code=401, detail="Session expired")

    # Verify signature
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


def verify_plex_webhook_token(token: str | None = Query(None, alias="token")):
    """Verify the Plex webhook token."""
    if not settings.plex_webhook_token:
        # No token configured - reject all requests for security
        raise HTTPException(
            status_code=401,
            detail="Plex webhook not configured"
        )

    if not token:
        raise HTTPException(
            status_code=401,
            detail="Webhook token required. Add ?token=YOUR_TOKEN to the URL."
        )

    if not secrets.compare_digest(token, settings.plex_webhook_token):
        raise HTTPException(status_code=401, detail="Invalid webhook token")

    return True


# --- Auth ---

class PasswordCheck(BaseModel):
    password: str


@app.post("/api/auth/verify")
async def verify_auth(data: PasswordCheck):
    """Verify the preshared password and return a session token."""
    if secrets.compare_digest(data.password, settings.preshared_password):
        token = create_session_token()
        return {"valid": True, "token": token}
    raise HTTPException(status_code=401, detail="Invalid password")


# --- Search ---

class SearchQuery(BaseModel):
    query: str
    media_type: str | None = None  # "movie", "tv", or None for multi
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

        # Filter out person results and prepare items
        items = []
        tv_shows_to_fetch = []  # (index, tmdb_id) for TV shows needing season count

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
            in_library = await is_in_library(tmdb_id, media_type)

            item_data = {
                "id": tmdb_id,
                "title": title,
                "year": int(year) if year else None,
                "overview": item.get("overview"),
                "poster_path": item.get("poster_path"),
                "media_type": media_type,
                "vote_average": item.get("vote_average"),
                "requested": requested,
                "in_library": in_library,
                "number_of_seasons": None
            }
            items.append(item_data)

            # Track TV shows that aren't already requested/in_library for season fetch
            if media_type == "tv" and not requested and not in_library:
                tv_shows_to_fetch.append((len(items) - 1, tmdb_id))

        # Fetch season counts for TV shows in parallel
        if tv_shows_to_fetch:
            async def fetch_seasons(idx, show_id):
                try:
                    details = await tmdb_client.get_tv(show_id)
                    return idx, details.get("number_of_seasons")
                except Exception:
                    return idx, None

            season_results = await asyncio.gather(
                *[fetch_seasons(idx, show_id) for idx, show_id in tv_shows_to_fetch]
            )
            for idx, num_seasons in season_results:
                items[idx]["number_of_seasons"] = num_seasons

        return {
            "results": items,
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
async def create_request(data: MediaRequest, _: bool = Depends(verify_session_token)):
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
async def delete_request(media_type: str, tmdb_id: int, _: bool = Depends(verify_session_token)):
    """Remove a media item from the request list."""
    success = await remove_request(tmdb_id, media_type)
    if success:
        return {"success": True, "message": "Request removed"}
    raise HTTPException(status_code=404, detail="Request not found")


@app.get("/api/requests")
async def list_requests(media_type: str | None = None, _: bool = Depends(verify_session_token)):
    """Get all requests, optionally filtered by media type."""
    requests = await get_all_requests(media_type)
    return {"requests": requests}


# --- Trending/Popular ---

@app.get("/api/trending")
async def get_trending(media_type: str = "all", _: bool = Depends(verify_session_token)):
    """Get trending movies/TV shows."""
    try:
        results = await tmdb_client.get_trending(media_type)

        items = []
        tv_shows_to_fetch = []  # (index, tmdb_id) for TV shows needing season count

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
            in_library = await is_in_library(tmdb_id, item_type)

            item_data = {
                "id": tmdb_id,
                "title": title,
                "year": int(year) if year else None,
                "overview": item.get("overview"),
                "poster_path": item.get("poster_path"),
                "media_type": item_type,
                "vote_average": item.get("vote_average"),
                "requested": requested,
                "in_library": in_library,
                "number_of_seasons": None
            }
            items.append(item_data)

            # Track TV shows that aren't already requested/in_library for season fetch
            if item_type == "tv" and not requested and not in_library:
                tv_shows_to_fetch.append((len(items) - 1, tmdb_id))

        # Fetch season counts for TV shows in parallel
        if tv_shows_to_fetch:
            async def fetch_seasons(idx, show_id):
                try:
                    details = await tmdb_client.get_tv(show_id)
                    return idx, details.get("number_of_seasons")
                except Exception:
                    return idx, None

            season_results = await asyncio.gather(
                *[fetch_seasons(idx, show_id) for idx, show_id in tv_shows_to_fetch]
            )
            for idx, num_seasons in season_results:
                items[idx]["number_of_seasons"] = num_seasons

        return Response(
            content=json.dumps({"results": items}),
            media_type="application/json",
            headers={"Cache-Control": "public, max-age=3600"}  # 1 hour
        )
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


# --- Plex Webhook ---

@app.post("/webhook/plex")
async def plex_webhook(
    payload: str = Form(...),
    _: bool = Depends(verify_plex_webhook_token)
):
    """
    Handle Plex webhook notifications.

    Plex sends webhooks as multipart/form-data with:
    - payload: JSON string containing the event data
    - thumb: (optional) thumbnail image

    Configure in Plex: Settings -> Webhooks -> Add
    URL: https://your-domain.com/webhook/plex?token=YOUR_PLEX_WEBHOOK_TOKEN
    """
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # Check event type - only process library.new
    event = data.get('event', '')
    if event != 'library.new':
        return {"status": "ignored", "reason": f"Event type '{event}' not processed"}

    # Validate server name if configured
    if settings.plex_server_name:
        server_title = data.get('Server', {}).get('title', '')
        if server_title != settings.plex_server_name:
            return {"status": "ignored", "reason": "Server name mismatch"}

    # Parse the payload
    from plex import parse_plex_payload
    media = parse_plex_payload(data)

    if not media:
        return {"status": "ignored", "reason": "Unsupported media type"}

    # Try to match and update request using our matching strategy
    matched = False
    matched_request = None

    # 1. Try TMDB ID (most reliable for movies and shows)
    if media.tmdb_id:
        matched = await mark_as_added(media.tmdb_id, media.media_type)
        if matched:
            # If we matched and have a plex_guid, cache it for future
            if media.plex_guid:
                await update_plex_guid(media.tmdb_id, media.media_type, media.plex_guid)

    # 2. Try TVDB ID (common for TV shows)
    if not matched and media.tvdb_id and media.media_type == 'tv':
        matched_request = await find_by_tvdb_id(media.tvdb_id, media.media_type)
        if matched_request:
            matched = await mark_as_added(matched_request['tmdb_id'], media.media_type)
            if matched and media.plex_guid:
                await update_plex_guid(matched_request['tmdb_id'], media.media_type, media.plex_guid)

    # 3. Try Plex GUID (for episodes/seasons using cached show GUID)
    if not matched and media.plex_guid:
        matched_request = await find_by_plex_guid(media.plex_guid)
        if matched_request:
            matched = await mark_as_added(matched_request['tmdb_id'], matched_request['media_type'])

    # 4. Try TVDB reverse lookup (episode TVDB ID → show TVDB ID)
    if not matched and media.episode_tvdb_id:
        from tvdb import get_series_id_from_episode
        show_tvdb_id = await get_series_id_from_episode(media.episode_tvdb_id)
        if show_tvdb_id:
            matched_request = await find_by_tvdb_id(show_tvdb_id, 'tv')
            if matched_request:
                matched = await mark_as_added(matched_request['tmdb_id'], 'tv')
                if matched and media.plex_guid:
                    await update_plex_guid(matched_request['tmdb_id'], 'tv', media.plex_guid)

    if matched:
        return {
            "status": "success",
            "matched": True,
            "title": media.title,
            "media_type": media.media_type,
            "tmdb_id": media.tmdb_id or (matched_request['tmdb_id'] if matched_request else None)
        }
    else:
        return {
            "status": "success",
            "matched": False,
            "reason": "No matching request found",
            "title": media.title,
            "media_type": media.media_type
        }


# --- Library Sync ---

@app.post("/sync/library")
async def sync_library_endpoint(
    request: Request,
    media_type: str = Query(..., description="Media type: 'movie' or 'tv'"),
    clear: bool = Query(False, description="Clear existing library items before syncing"),
    _: bool = Depends(verify_plex_webhook_token)
):
    """
    Sync Plex library contents for a media type.

    Receives a JSON array of library items and updates the local library cache.
    Also marks any matching requests as added.

    Configure sync script to POST to:
    https://your-domain.com/sync/library?media_type=movie&token=YOUR_PLEX_WEBHOOK_TOKEN

    Add &clear=true on first batch to clear existing items.
    """
    if media_type not in ('movie', 'tv'):
        raise HTTPException(status_code=400, detail="media_type must be 'movie' or 'tv'")

    try:
        data = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    if not isinstance(data, list):
        raise HTTPException(status_code=400, detail="Body must be a JSON array")

    # Sync the library
    count = await sync_library(data, media_type, clear_first=clear)

    # Mark any matching requests as added
    marked = 0
    for item in data:
        tmdb_id = item.get('tmdb_id')
        if tmdb_id:
            if await mark_as_added(tmdb_id, media_type):
                marked += 1

    return {
        "status": "success",
        "synced": count,
        "marked_as_added": marked,
        "media_type": media_type
    }
