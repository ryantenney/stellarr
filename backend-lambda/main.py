from fastapi import FastAPI, HTTPException, Depends, Request, Response, Query, Header, Form
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

# =============================================================================
# Lazy imports for cold start optimization
# These modules are only loaded when their endpoints are first called
# =============================================================================
_settings = None
_database = None
_tmdb_client = None
_rss_module = None
_plex_module = None
_tvdb_module = None


def get_settings_lazy():
    """Lazy load settings from Secrets Manager on first use."""
    global _settings
    if _settings is None:
        print("DEBUG: Lazy loading settings...", flush=True)
        from config import get_settings
        _settings = get_settings()
    return _settings


def get_database():
    """Lazy load database module on first use."""
    global _database
    if _database is None:
        print("DEBUG: Lazy loading database...", flush=True)
        import database
        _database = database
    return _database


def get_tmdb_client():
    """Lazy load TMDB client on first use."""
    global _tmdb_client
    if _tmdb_client is None:
        print("DEBUG: Lazy loading TMDB client...", flush=True)
        from tmdb import tmdb_client
        _tmdb_client = tmdb_client
    return _tmdb_client


def get_rss_module():
    """Lazy load RSS module on first use."""
    global _rss_module
    if _rss_module is None:
        print("DEBUG: Lazy loading RSS module...", flush=True)
        import rss
        _rss_module = rss
    return _rss_module


def get_plex_module():
    """Lazy load Plex module on first use."""
    global _plex_module
    if _plex_module is None:
        print("DEBUG: Lazy loading Plex module...", flush=True)
        import plex
        _plex_module = plex
    return _plex_module


def get_tvdb_module():
    """Lazy load TVDB module on first use."""
    global _tvdb_module
    if _tvdb_module is None:
        print("DEBUG: Lazy loading TVDB module...", flush=True)
        import tvdb
        _tvdb_module = tvdb
    return _tvdb_module


# Rate limiting config (from Terraform env vars)
RATE_LIMIT_ENABLED = os.environ.get('RATE_LIMIT_ENABLED', 'false').lower() == 'true'
RATE_LIMIT_MAX_ATTEMPTS = int(os.environ.get('RATE_LIMIT_MAX_ATTEMPTS', '5'))
RATE_LIMIT_WINDOW_SECONDS = int(os.environ.get('RATE_LIMIT_WINDOW_SECONDS', '900'))

# CORS config
ALLOWED_ORIGIN = os.environ.get('ALLOWED_ORIGIN', '*')

# Session duration: 30 days in seconds
SESSION_DURATION_SECONDS = 30 * 24 * 60 * 60


def create_session_token() -> str:
    """Create a signed session token with timestamp."""
    settings = get_settings_lazy()
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

    settings = get_settings_lazy()
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
    allow_origins=[ALLOWED_ORIGIN] if ALLOWED_ORIGIN != "*" else ["*"],
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

def get_client_ip(request: Request) -> str:
    """Get client IP, accounting for CloudFront/proxy forwarding."""
    # CloudFront adds the real client IP to X-Forwarded-For
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        # X-Forwarded-For can be a comma-separated list; first is the client
        return forwarded_for.split(",")[0].strip()
    # Fallback to direct client IP
    return request.client.host if request.client else "unknown"


def get_base_url(request: Request) -> str:
    """Get the base URL from environment variable (set by Terraform) or fallback."""
    # Use BASE_URL env var set by Terraform (preferred for CloudFront)
    base_url = os.environ.get("BASE_URL")
    if base_url:
        return base_url.rstrip("/")
    return str(request.base_url).rstrip("/")


def verify_feed_token(token: str | None = Query(None, alias="token")):
    """Verify the feed token for RSS/list endpoints."""
    settings = get_settings_lazy()
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


def verify_plex_webhook_token(token: str | None = Query(None, alias="token")):
    """Verify the Plex webhook token."""
    settings = get_settings_lazy()

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

# Maximum allowed time skew for challenge-response auth (5 minutes)
AUTH_TIME_WINDOW_SECONDS = 300

# PBKDF2 iterations (single source of truth - frontend fetches this)
PBKDF2_ITERATIONS = 100000


class AuthChallenge(BaseModel):
    origin: str      # The origin URL (e.g., "https://overseer.example.com")
    timestamp: int   # Unix timestamp when hash was generated
    hash: str        # SHA256(PBKDF2(password, origin):timestamp)
    name: str        # User's display name


def verify_challenge_hash(origin: str, timestamp: int, provided_hash: str) -> bool:
    """Verify the challenge-response hash with PBKDF2 key derivation."""
    settings = get_settings_lazy()
    # 1. Derive key using PBKDF2 (makes brute-force attacks expensive)
    derived_key = hashlib.pbkdf2_hmac(
        'sha256',
        settings.preshared_password.encode(),
        origin.encode(),
        PBKDF2_ITERATIONS,
        dklen=32  # 256 bits
    )
    derived_key_hex = derived_key.hex()

    # 2. Compute expected hash: SHA256(derived_key:timestamp)
    challenge_string = f"{derived_key_hex}:{timestamp}"
    expected_hash = hashlib.sha256(challenge_string.encode()).hexdigest()

    return secrets.compare_digest(provided_hash, expected_hash)


@app.get("/api/auth/params")
def get_auth_params():
    """Return auth parameters (PBKDF2 iterations) for frontend."""
    return {"iterations": PBKDF2_ITERATIONS}


@app.post("/api/auth/verify")
def verify_auth(data: AuthChallenge, request: Request):
    """Verify challenge-response auth and return a session token."""
    client_ip = get_client_ip(request)

    # Check rate limit BEFORE expensive PBKDF2 computation
    if RATE_LIMIT_ENABLED:
        db = get_database()
        allowed, remaining = db.check_rate_limit(
            client_ip, RATE_LIMIT_MAX_ATTEMPTS, RATE_LIMIT_WINDOW_SECONDS
        )
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail=f"Too many failed attempts. Try again in {RATE_LIMIT_WINDOW_SECONDS // 60} minutes."
            )

    current_time = int(time.time())

    # Check timestamp is within allowed window
    time_diff = abs(current_time - data.timestamp)
    if time_diff > AUTH_TIME_WINDOW_SECONDS:
        raise HTTPException(
            status_code=401,
            detail=f"Timestamp expired. Please try again. (skew: {time_diff}s)"
        )

    # Verify the hash
    if not verify_challenge_hash(data.origin, data.timestamp, data.hash):
        # Record failed attempt for rate limiting
        if RATE_LIMIT_ENABLED:
            db = get_database()
            db.record_failed_attempt(client_ip, RATE_LIMIT_WINDOW_SECONDS)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Validate name
    name = data.name.strip()
    if not name or len(name) > 50:
        raise HTTPException(status_code=400, detail="Name is required (max 50 chars)")

    # Clear rate limit on successful auth
    if RATE_LIMIT_ENABLED:
        db = get_database()
        db.clear_rate_limit(client_ip)

    token = create_session_token()
    return {"valid": True, "token": token, "name": name}


# --- Search ---

class SearchQuery(BaseModel):
    query: str
    media_type: str | None = None
    page: int = 1


@app.post("/api/search")
async def search(data: SearchQuery, _: bool = Depends(verify_session_token)):
    """Search TMDB for movies and TV shows."""
    tmdb = get_tmdb_client()
    db = get_database()
    try:
        if data.media_type == "movie":
            results = await tmdb.search_movie(data.query, data.page)
        elif data.media_type == "tv":
            results = await tmdb.search_tv(data.query, data.page)
        else:
            results = await tmdb.search_multi(data.query, data.page)

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

            requested = db.is_requested(tmdb_id, media_type)

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
    requested_by: str | None = None  # Name of person who requested


@app.post("/api/request")
async def create_request(data: MediaRequest, _: bool = Depends(verify_session_token)):
    """Add a media item to the request list."""
    tmdb = get_tmdb_client()
    db = get_database()
    try:
        if data.media_type == "movie":
            details = await tmdb.get_movie(data.tmdb_id)
            title = details.get("title", "Unknown")
            year = details.get("release_date", "")[:4] if details.get("release_date") else None
            imdb_id = details.get("external_ids", {}).get("imdb_id")
            tvdb_id = None
        else:
            details = await tmdb.get_tv(data.tmdb_id)
            title = details.get("name", "Unknown")
            year = details.get("first_air_date", "")[:4] if details.get("first_air_date") else None
            imdb_id = details.get("external_ids", {}).get("imdb_id")
            tvdb_id = details.get("external_ids", {}).get("tvdb_id")

        success = db.add_request(
            tmdb_id=data.tmdb_id,
            media_type=data.media_type,
            title=title,
            year=int(year) if year else None,
            overview=details.get("overview"),
            poster_path=details.get("poster_path"),
            imdb_id=imdb_id,
            tvdb_id=tvdb_id,
            requested_by=data.requested_by
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
    db = get_database()
    success = db.remove_request(tmdb_id, media_type)
    if success:
        return {"success": True, "message": "Request removed"}
    raise HTTPException(status_code=404, detail="Request not found")


@app.get("/api/requests")
def list_requests(media_type: str | None = None, _: bool = Depends(verify_session_token)):
    """Get all requests, optionally filtered by media type."""
    db = get_database()
    requests = db.get_all_requests(media_type)
    return {"requests": requests}


# --- Trending/Popular ---

@app.get("/api/trending")
async def get_trending(media_type: str = "all", _: bool = Depends(verify_session_token)):
    """Get trending movies/TV shows."""
    tmdb = get_tmdb_client()
    db = get_database()
    try:
        results = await tmdb.get_trending(media_type)

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

            requested = db.is_requested(tmdb_id, item_type)

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
    rss = get_rss_module()
    base_url = get_base_url(request)
    xml = rss.generate_movie_rss(base_url)
    return Response(content=xml, media_type="application/rss+xml")


@app.get("/rss/tv")
def rss_tv(request: Request, _: bool = Depends(verify_feed_token)):
    """RSS feed for TV show requests."""
    rss = get_rss_module()
    base_url = get_base_url(request)
    xml = rss.generate_tv_rss(base_url)
    return Response(content=xml, media_type="application/rss+xml")


@app.get("/rss/all")
def rss_all(request: Request, _: bool = Depends(verify_feed_token)):
    """Combined RSS feed for all requests."""
    rss = get_rss_module()
    base_url = get_base_url(request)
    xml = rss.generate_combined_rss(base_url)
    return Response(content=xml, media_type="application/rss+xml")


# --- JSON Lists ---

@app.get("/list/radarr")
def list_radarr(_: bool = Depends(verify_feed_token)):
    """Radarr StevenLu Custom list format (JSON)."""
    rss = get_rss_module()
    return rss.generate_radarr_json()


@app.get("/list/sonarr")
def list_sonarr(_: bool = Depends(verify_feed_token)):
    """Sonarr Custom List format (JSON)."""
    rss = get_rss_module()
    return rss.generate_sonarr_json()


# --- Feed Info ---

@app.get("/api/feeds")
def get_feed_info(request: Request):
    """Get information about available feeds and their URLs."""
    settings = get_settings_lazy()
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
    """Health check endpoint - no dependencies, fastest possible response."""
    return {"status": "healthy", "service": "overseer-lite"}


# --- Plex Webhook ---

@app.post("/webhook/plex")
def plex_webhook(
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
    import json

    settings = get_settings_lazy()
    db = get_database()
    plex = get_plex_module()

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
    media = plex.parse_plex_payload(data)

    if not media:
        return {"status": "ignored", "reason": "Unsupported media type"}

    # Try to match and update request using our matching strategy
    matched = False
    matched_request = None

    # 1. Try TMDB ID (most reliable for movies and shows)
    if media.tmdb_id:
        matched = db.mark_as_added(media.tmdb_id, media.media_type)
        if matched:
            # If we matched and have a plex_guid, cache it for future
            if media.plex_guid:
                db.update_plex_guid(media.tmdb_id, media.media_type, media.plex_guid)

    # 2. Try TVDB ID (common for TV shows)
    if not matched and media.tvdb_id and media.media_type == 'tv':
        matched_request = db.find_by_tvdb_id(media.tvdb_id, media.media_type)
        if matched_request:
            matched = db.mark_as_added(matched_request['tmdb_id'], media.media_type)
            if matched and media.plex_guid:
                db.update_plex_guid(matched_request['tmdb_id'], media.media_type, media.plex_guid)

    # 3. Try Plex GUID (for episodes/seasons using cached show GUID)
    if not matched and media.plex_guid:
        matched_request = db.find_by_plex_guid(media.plex_guid)
        if matched_request:
            matched = db.mark_as_added(matched_request['tmdb_id'], matched_request['media_type'])

    # 4. Try TVDB reverse lookup (episode TVDB ID → show TVDB ID)
    if not matched and media.episode_tvdb_id:
        import asyncio
        tvdb = get_tvdb_module()
        show_tvdb_id = asyncio.get_event_loop().run_until_complete(
            tvdb.get_series_id_from_episode(media.episode_tvdb_id)
        )
        if show_tvdb_id:
            matched_request = db.find_by_tvdb_id(show_tvdb_id, 'tv')
            if matched_request:
                matched = db.mark_as_added(matched_request['tmdb_id'], 'tv')
                if matched and media.plex_guid:
                    db.update_plex_guid(matched_request['tmdb_id'], 'tv', media.plex_guid)

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


print("DEBUG: Module load complete, handler ready", flush=True)

# Lambda handler - lifespan="off" since we handle init lazily
handler = Mangum(app, lifespan="off")
