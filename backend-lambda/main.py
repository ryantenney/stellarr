from fastapi import FastAPI, HTTPException, Depends, Request, Response, Query, Header, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from contextlib import asynccontextmanager
from mangum import Mangum
import asyncio
import json
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


_webpush_module = None

def get_webpush_module():
    """Lazy load WebPush module on first use."""
    global _webpush_module
    if _webpush_module is None:
        print("DEBUG: Lazy loading WebPush module...", flush=True)
        import webpush
        _webpush_module = webpush
    return _webpush_module


# Rate limiting config (from Terraform env vars)
RATE_LIMIT_ENABLED = os.environ.get('RATE_LIMIT_ENABLED', 'false').lower() == 'true'
RATE_LIMIT_MAX_ATTEMPTS = int(os.environ.get('RATE_LIMIT_MAX_ATTEMPTS', '5'))
RATE_LIMIT_WINDOW_SECONDS = int(os.environ.get('RATE_LIMIT_WINDOW_SECONDS', '900'))

# CORS config
ALLOWED_ORIGIN = os.environ.get('ALLOWED_ORIGIN', '*')

# Session duration: 30 days in seconds
SESSION_DURATION_SECONDS = 30 * 24 * 60 * 60


def create_session_token(name: str = "") -> str:
    """Create a signed session token with timestamp and optional name."""
    settings = get_settings_lazy()
    timestamp = str(int(time.time()))
    # Include name in the signed payload
    name_b64 = base64.urlsafe_b64encode(name.encode()).decode().rstrip("=") if name else ""
    payload = f"{timestamp}.{name_b64}"
    signature = hmac.new(
        settings.app_secret_key.encode(),
        payload.encode(),
        hashlib.sha256
    ).digest()
    sig_b64 = base64.urlsafe_b64encode(signature).decode().rstrip("=")
    return f"{payload}.{sig_b64}"


def verify_session_token(authorization: str | None = Header(None, alias="Authorization")) -> bool:
    """Verify the session token from Authorization header."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")

    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid authorization format")

    token = parts[1]
    token_parts = token.split(".")

    # New format: timestamp.name_b64.signature (3 parts)
    # Old format: timestamp.signature (2 parts) - backwards compatible
    if len(token_parts) == 3:
        timestamp_str, name_b64, sig_b64 = token_parts
        payload = f"{timestamp_str}.{name_b64}"
    elif len(token_parts) == 2:
        timestamp_str, sig_b64 = token_parts
        payload = timestamp_str
    else:
        raise HTTPException(status_code=401, detail="Invalid token format")

    try:
        timestamp = int(timestamp_str)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid token format")

    if time.time() - timestamp > SESSION_DURATION_SECONDS:
        raise HTTPException(status_code=401, detail="Session expired")

    settings = get_settings_lazy()
    expected_sig = hmac.new(
        settings.app_secret_key.encode(),
        payload.encode(),
        hashlib.sha256
    ).digest()
    expected_b64 = base64.urlsafe_b64encode(expected_sig).decode().rstrip("=")

    if not secrets.compare_digest(sig_b64, expected_b64):
        raise HTTPException(status_code=401, detail="Invalid token")

    return True


def get_user_from_token(authorization: str | None = Header(None, alias="Authorization")) -> str | None:
    """Extract user name from session token. Returns None if not available."""
    if not authorization:
        return None

    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None

    token = parts[1]
    token_parts = token.split(".")

    # New format: timestamp.name_b64.signature (3 parts)
    if len(token_parts) == 3:
        _, name_b64, _ = token_parts
        if name_b64:
            try:
                # Restore padding for base64 decode
                padding = 4 - (len(name_b64) % 4)
                if padding != 4:
                    name_b64 += '=' * padding
                return base64.urlsafe_b64decode(name_b64).decode('utf-8')
            except Exception:
                return None

    return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan handler - DB init moved to module level for Lambda."""
    yield


app = FastAPI(
    title="Overseer Lite",
    description="A lightweight media request system for Sonarr/Radarr",
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

    token = create_session_token(name)
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

        # Filter out person results and prepare items
        items = []
        tv_shows_to_fetch = []  # (index, tmdb_id) for TV shows needing season count

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
            in_library = db.is_in_library(tmdb_id, media_type)

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
                    details = await tmdb.get_tv(show_id)
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

def verify_trending_key(key: str | None = Query(None, alias="key")):
    """Verify the trending API key (security-by-obscurity)."""
    db = get_database()
    stored_key = db.get_trending_key()

    if not stored_key:
        # No key configured yet - reject
        raise HTTPException(status_code=404, detail="Not found")

    if not key:
        raise HTTPException(status_code=404, detail="Not found")

    if not secrets.compare_digest(key, stored_key):
        raise HTTPException(status_code=404, detail="Not found")

    return True


@app.get("/api/trending")
async def get_trending(
    media_type: str = "all",
    _: bool = Depends(verify_trending_key)
):
    """
    Get trending movies/TV shows.
    Public endpoint protected by obscure key (for CloudFront caching).
    Returns pure TMDB data - no user-specific status.
    """
    tmdb = get_tmdb_client()
    try:
        results = await tmdb.get_trending(media_type)

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

            item_data = {
                "id": tmdb_id,
                "title": title,
                "year": int(year) if year else None,
                "overview": item.get("overview"),
                "poster_path": item.get("poster_path"),
                "media_type": item_type,
                "vote_average": item.get("vote_average"),
                "number_of_seasons": None
            }
            items.append(item_data)

            # Track TV shows for season fetch
            if item_type == "tv":
                tv_shows_to_fetch.append((len(items) - 1, tmdb_id))

        # Fetch season counts for TV shows in parallel
        if tv_shows_to_fetch:
            async def fetch_seasons(idx, show_id):
                try:
                    details = await tmdb.get_tv(show_id)
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
            headers={"Cache-Control": "public, max-age=86400"}  # 24 hours
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- Library Status (for frontend caching) ---

@app.get("/api/library-status")
def get_library_status(_: bool = Depends(verify_session_token)):
    """
    Get library and request status for frontend caching.
    Returns trending key so frontend can fetch public trending endpoint.
    """
    db = get_database()

    # Get all library TMDB IDs (just IDs, not full objects)
    library = db.get_all_library_tmdb_ids()

    # Get all pending requests (full objects for display)
    all_requests = db.get_all_requests()
    # Filter to only pending (not yet added)
    pending_requests = [r for r in all_requests if not r.get('added_at')]

    # Get or create trending key
    trending_key = db.get_or_create_trending_key()

    return {
        "library": library,
        "requests": pending_requests,
        "trending_key": trending_key
    }


# --- Push Notifications ---

class PushSubscription(BaseModel):
    endpoint: str
    keys: dict  # {'p256dh': '...', 'auth': '...'}


@app.get("/api/push/vapid-public-key")
def get_vapid_public_key(_: bool = Depends(verify_session_token)):
    """Get VAPID public key for push subscription."""
    # Public key is passed via environment variable (generated by Terraform)
    # This avoids loading the cryptography library just for the public key
    public_key = os.environ.get('VAPID_PUBLIC_KEY')
    if not public_key:
        raise HTTPException(status_code=501, detail="Push notifications not configured")

    return {"public_key": public_key}


@app.post("/api/push/subscribe")
def subscribe_push(
    subscription: PushSubscription,
    user_name: str = Depends(get_user_from_token)
):
    """Subscribe to push notifications."""
    if not user_name:
        raise HTTPException(status_code=401, detail="User name required for push subscription")

    db = get_database()
    success = db.save_push_subscription(user_name, {
        'endpoint': subscription.endpoint,
        'keys': subscription.keys
    })

    if not success:
        raise HTTPException(status_code=500, detail="Failed to save subscription")

    print(f"PUSH: Subscribed user '{user_name}'", flush=True)
    return {"status": "subscribed"}


@app.delete("/api/push/subscribe")
def unsubscribe_push(user_name: str = Depends(get_user_from_token)):
    """Unsubscribe from push notifications."""
    if not user_name:
        raise HTTPException(status_code=401, detail="User name required")

    db = get_database()
    db.delete_push_subscription(user_name)
    print(f"PUSH: Unsubscribed user '{user_name}'", flush=True)
    return {"status": "unsubscribed"}


@app.get("/api/push/status")
def get_push_status(user_name: str = Depends(get_user_from_token)):
    """Check if user has an active push subscription."""
    if not user_name:
        return {"subscribed": False}

    db = get_database()
    subscription = db.get_push_subscription(user_name)
    return {"subscribed": subscription is not None}


def send_fulfillment_notification(request_data: dict) -> bool:
    """
    Send a push notification when a request is fulfilled.
    request_data should have: requested_by, title, poster_path, media_type.
    Returns True if notification sent successfully.
    """
    settings = get_settings_lazy()
    if not settings.vapid_private_key:
        return False

    requested_by = request_data.get('requested_by')
    if not requested_by:
        print("PUSH: No requested_by in request, skipping notification", flush=True)
        return False

    db = get_database()
    subscription = db.get_push_subscription(requested_by)
    if not subscription:
        print(f"PUSH: No subscription for user '{requested_by}', skipping notification", flush=True)
        return False

    title = request_data.get('title', 'Unknown')
    media_type = request_data.get('media_type', 'media')
    poster_path = request_data.get('poster_path')

    # Build notification payload
    type_label = "Movie" if media_type == "movie" else "TV Show"
    notification = {
        "title": f"{type_label} Available",
        "body": f"{title} has been added to the library!",
        "tag": f"fulfilled-{media_type}-{request_data.get('tmdb_id', 0)}",
    }

    # Add poster image if available
    if poster_path:
        notification["image"] = f"https://image.tmdb.org/t/p/w300{poster_path}"
        notification["icon"] = f"https://image.tmdb.org/t/p/w92{poster_path}"

    try:
        webpush = get_webpush_module()
        success = webpush.send_push(
            subscription=subscription,
            data=notification,
            vapid_private_key=settings.vapid_private_key,
            vapid_claims={"sub": "mailto:admin@example.com"}
        )
        if success:
            print(f"PUSH: Sent notification to '{requested_by}' for '{title}'", flush=True)
        else:
            # Subscription invalid/expired - clean it up
            print(f"PUSH: Subscription expired for '{requested_by}', removing", flush=True)
            db.delete_push_subscription(requested_by)
        return success
    except Exception as e:
        print(f"PUSH: Error sending notification to '{requested_by}': {e}", flush=True)
        return False


# --- JSON Lists for Sonarr/Radarr ---

@app.get("/list/radarr")
def list_radarr(_: bool = Depends(verify_feed_token)):
    """Radarr StevenLu Custom list format (JSON)."""
    db = get_database()
    all_requests = db.get_all_requests(media_type="movie")
    # Filter out items already added to library
    requests = [r for r in all_requests if not r.get('added_at')]

    items = []
    for req in requests:
        item = {
            "title": f"{req['title']} ({req['year']})" if req.get('year') else req['title'],
        }
        if req.get('imdb_id'):
            item["imdb_id"] = req['imdb_id']
        if req.get('poster_path'):
            item["poster_url"] = f"https://image.tmdb.org/t/p/w300{req['poster_path']}"
        items.append(item)

    return items


@app.get("/list/sonarr")
def list_sonarr(_: bool = Depends(verify_feed_token)):
    """Sonarr Custom List format (JSON)."""
    db = get_database()
    all_requests = db.get_all_requests(media_type="tv")
    # Filter out items already added to library
    requests = [r for r in all_requests if not r.get('added_at')]

    items = []
    for req in requests:
        if req.get('tvdb_id'):
            items.append({"tvdbId": str(req['tvdb_id'])})

    return items


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
                "description": "StevenLu Custom JSON format for Radarr",
                "url": f"{base_url}/list/radarr{token_param}",
                "format": "json",
                "setup": "Settings -> Import Lists -> Custom Lists -> StevenLu Custom"
            },
            "sonarr": {
                "name": "Sonarr (TV Shows)",
                "description": "Custom List JSON format with TVDB IDs for Sonarr",
                "url": f"{base_url}/list/sonarr{token_param}",
                "format": "json",
                "setup": "Settings -> Import Lists -> Add -> Custom Lists"
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
        print("WEBHOOK: Invalid JSON payload received", flush=True)
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # Extract key info for logging
    event = data.get('event', '')
    server_title = data.get('Server', {}).get('title', 'unknown')
    metadata = data.get('Metadata', {})
    media_title = metadata.get('title', metadata.get('grandparentTitle', 'unknown'))
    media_type_raw = metadata.get('type', 'unknown')

    print(f"WEBHOOK: Received event='{event}' server='{server_title}' type='{media_type_raw}' title='{media_title}'", flush=True)

    # Check event type - only process library.new
    if event != 'library.new':
        print(f"WEBHOOK: Ignored - event type '{event}' not processed", flush=True)
        return {"status": "ignored", "reason": f"Event type '{event}' not processed"}

    # Validate server name if configured
    if settings.plex_server_name:
        if server_title != settings.plex_server_name:
            print(f"WEBHOOK: Ignored - server mismatch (expected='{settings.plex_server_name}', got='{server_title}')", flush=True)
            return {"status": "ignored", "reason": "Server name mismatch"}

    # Parse the payload
    media = plex.parse_plex_payload(data)

    if not media:
        print(f"WEBHOOK: Ignored - unsupported media type '{media_type_raw}'", flush=True)
        return {"status": "ignored", "reason": "Unsupported media type"}

    print(f"WEBHOOK: Parsed media - title='{media.title}' type='{media.media_type}' plex_type='{media.plex_type}' tmdb={media.tmdb_id} tvdb={media.tvdb_id}", flush=True)

    # For episodes/seasons, the tmdb_id from the Guid array is episode/season-level, not show-level.
    # We need to resolve show-level IDs before adding to library or matching.
    show_tmdb_id = media.tmdb_id
    show_tvdb_id = media.tvdb_id
    resolved_from_cache = False

    # For episodes/seasons, check the Plex GUID cache first
    if media.plex_type in ('episode', 'season') and media.plex_guid:
        cached = db.get_plex_guid_cache(media.plex_guid)
        if cached:
            show_tmdb_id = cached.get('tmdb_id')
            show_tvdb_id = cached.get('tvdb_id')
            resolved_from_cache = True
            print(f"WEBHOOK: Cache hit for plex_guid - show tmdb={show_tmdb_id} tvdb={show_tvdb_id}", flush=True)
        else:
            # For episodes/seasons, the IDs in Guid array are NOT show-level
            # Clear them so we don't incorrectly add episode IDs to library
            show_tmdb_id = None
            show_tvdb_id = None
            print(f"WEBHOOK: Cache miss for plex_guid - need to resolve show IDs", flush=True)

    # Add to library only if we have a show-level TMDB ID (not episode-level)
    added_to_library = False
    if show_tmdb_id:
        db.sync_library(
            [{"tmdb_id": show_tmdb_id, "tvdb_id": show_tvdb_id, "title": media.title}],
            media.media_type,
            clear_first=False
        )
        added_to_library = True
        print(f"WEBHOOK: Added to library - tmdb={show_tmdb_id} type='{media.media_type}'", flush=True)

    # Try to match and update request using our matching strategy
    # matched_request now contains the full request data (for push notifications)
    matched_request = None

    # 1. Try TMDB ID (most reliable for movies and shows)
    if show_tmdb_id:
        matched_request = db.mark_as_added(show_tmdb_id, media.media_type)
        if matched_request:
            print(f"WEBHOOK: Matched request by TMDB ID {show_tmdb_id}", flush=True)
            # Cache the plex_guid for future episode webhooks
            if media.plex_guid:
                db.update_plex_guid(show_tmdb_id, media.media_type, media.plex_guid)
                db.set_plex_guid_cache(media.plex_guid, show_tmdb_id, show_tvdb_id)

    # 2. Try TVDB ID (common for TV shows)
    if not matched_request and show_tvdb_id and media.media_type == 'tv':
        found_request = db.find_by_tvdb_id(show_tvdb_id, media.media_type)
        if found_request:
            matched_request = db.mark_as_added(found_request['tmdb_id'], media.media_type)
            if matched_request:
                print(f"WEBHOOK: Matched request by TVDB ID {show_tvdb_id} -> TMDB {found_request['tmdb_id']}", flush=True)
                if media.plex_guid:
                    db.update_plex_guid(found_request['tmdb_id'], media.media_type, media.plex_guid)
                    db.set_plex_guid_cache(media.plex_guid, found_request['tmdb_id'], show_tvdb_id)

    # 3. Try Plex GUID (for episodes/seasons using cached show GUID from requests table)
    if not matched_request and media.plex_guid:
        found_request = db.find_by_plex_guid(media.plex_guid)
        if found_request:
            matched_request = db.mark_as_added(found_request['tmdb_id'], found_request['media_type'])
            if matched_request:
                print(f"WEBHOOK: Matched request by Plex GUID -> TMDB {found_request['tmdb_id']}", flush=True)
                # Also update the GUID cache if we matched from the request table
                if not resolved_from_cache:
                    db.set_plex_guid_cache(media.plex_guid, found_request['tmdb_id'], found_request.get('tvdb_id'))

    # 4. Try TVDB reverse lookup (episode TVDB ID → show TVDB ID)
    # Only do this if we have an episode TVDB ID and haven't matched yet
    if not matched_request and media.episode_tvdb_id:
        import asyncio
        tvdb = get_tvdb_module()
        print(f"WEBHOOK: Attempting TVDB reverse lookup for episode {media.episode_tvdb_id}", flush=True)
        show_tvdb_id_resolved = asyncio.get_event_loop().run_until_complete(
            tvdb.get_series_id_from_episode(media.episode_tvdb_id)
        )
        if show_tvdb_id_resolved:
            print(f"WEBHOOK: TVDB reverse lookup found show tvdb={show_tvdb_id_resolved}", flush=True)
            found_request = db.find_by_tvdb_id(show_tvdb_id_resolved, 'tv')
            if found_request:
                matched_request = db.mark_as_added(found_request['tmdb_id'], 'tv')
                if matched_request:
                    print(f"WEBHOOK: Matched request by TVDB reverse lookup - episode {media.episode_tvdb_id} -> show {show_tvdb_id_resolved} -> TMDB {found_request['tmdb_id']}", flush=True)
                    if media.plex_guid:
                        db.update_plex_guid(found_request['tmdb_id'], 'tv', media.plex_guid)
                        # Cache for future episode webhooks of this show
                        db.set_plex_guid_cache(media.plex_guid, found_request['tmdb_id'], show_tvdb_id_resolved)

            # Even if we didn't match a request, cache the resolved show IDs for future episodes
            # This way next episode won't need TVDB lookup
            if media.plex_guid and not resolved_from_cache:
                # We have the show's TVDB ID but may not have TMDB ID
                # Still worth caching to avoid repeated TVDB lookups
                if found_request:
                    db.set_plex_guid_cache(media.plex_guid, found_request['tmdb_id'], show_tvdb_id_resolved)
                else:
                    # Cache just the TVDB ID - future lookups can use this
                    db.set_plex_guid_cache(media.plex_guid, None, show_tvdb_id_resolved)
                    print(f"WEBHOOK: Cached plex_guid -> tvdb={show_tvdb_id_resolved} (no TMDB match)", flush=True)

    # 5. Try title-based matching as fallback (for unmatched Plex imports)
    # Only attempt if we still haven't matched and have no TMDB/TVDB IDs
    if not matched_request and not show_tmdb_id and not show_tvdb_id:
        print(f"WEBHOOK: No IDs available, attempting title match for '{media.title}'", flush=True)
        found_request = db.find_by_title(media.title, media.media_type, media.year)
        if found_request:
            matched_request = db.mark_as_added(found_request['tmdb_id'], media.media_type)
            if matched_request:
                print(f"WEBHOOK: Matched request by title '{media.title}' -> TMDB {found_request['tmdb_id']}", flush=True)
                # Add to library using the request's TMDB ID
                db.sync_library(
                    [{"tmdb_id": found_request['tmdb_id'], "tvdb_id": found_request.get('tvdb_id'), "title": media.title}],
                    media.media_type,
                    clear_first=False
                )
                added_to_library = True
                # Cache plex_guid for future lookups
                if media.plex_guid:
                    db.update_plex_guid(found_request['tmdb_id'], media.media_type, media.plex_guid)
                    db.set_plex_guid_cache(media.plex_guid, found_request['tmdb_id'], found_request.get('tvdb_id'))
        else:
            print(f"WEBHOOK: Title match failed - no unique match found", flush=True)

    # Send push notification if we matched a request
    notification_sent = False
    if matched_request:
        notification_sent = send_fulfillment_notification(matched_request)

    # Use resolved show-level TMDB ID in result (or original if show/movie)
    result_tmdb_id = show_tmdb_id if show_tmdb_id else media.tmdb_id
    result = {
        "status": "success",
        "title": media.title,
        "media_type": media.media_type,
        "plex_type": media.plex_type,
        "tmdb_id": result_tmdb_id,
        "added_to_library": added_to_library,
        "matched_request": matched_request is not None,
        "notification_sent": notification_sent
    }
    print(f"WEBHOOK: Complete - {result}", flush=True)

    return result


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
    import json

    db = get_database()

    if media_type not in ('movie', 'tv'):
        raise HTTPException(status_code=400, detail="media_type must be 'movie' or 'tv'")

    try:
        data = await request.json()
    except json.JSONDecodeError:
        print(f"SYNC: Invalid JSON body for media_type='{media_type}'", flush=True)
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    if not isinstance(data, list):
        print(f"SYNC: Body is not a list for media_type='{media_type}'", flush=True)
        raise HTTPException(status_code=400, detail="Body must be a JSON array")

    print(f"SYNC: Starting sync for media_type='{media_type}' count={len(data)} clear={clear}", flush=True)

    # Sync the library
    count = db.sync_library(data, media_type, clear_first=clear)

    # Mark any matching requests as added
    marked = 0
    for item in data:
        tmdb_id = item.get('tmdb_id')
        if tmdb_id:
            if db.mark_as_added(tmdb_id, media_type):
                marked += 1

    result = {
        "status": "success",
        "synced": count,
        "marked_as_added": marked,
        "media_type": media_type
    }
    print(f"SYNC: Complete - {result}", flush=True)

    return result


print("DEBUG: Module load complete, handler ready", flush=True)

# Lambda handler - lifespan="off" since we handle init lazily
handler = Mangum(app, lifespan="off")
