"""
TVDB API v4 client for episode-to-show lookups. Cloud-agnostic.

The TVDB API uses a login flow:
1. POST /login with API key -> receive bearer token (valid 1 month)
2. Use bearer token for subsequent requests

We cache the token and refresh when expired.
"""
import httpx
import time

# Token cache
_token: str | None = None
_token_expires: float = 0

# API key - set by provider via configure()
_api_key: str | None = None

TVDB_BASE_URL = "https://api4.thetvdb.com/v4"
# Token valid for 1 month, but refresh after 29 days to be safe
TOKEN_LIFETIME_SECONDS = 29 * 24 * 60 * 60


def configure(api_key: str):
    """Configure the TVDB client with an API key."""
    global _api_key
    _api_key = api_key


async def _login() -> str | None:
    """Login to TVDB API and get bearer token."""
    global _token, _token_expires

    if not _api_key:
        return None

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{TVDB_BASE_URL}/login",
                json={"apikey": _api_key},
                timeout=10.0
            )
            response.raise_for_status()
            data = response.json()
            _token = data.get("data", {}).get("token")
            _token_expires = time.time() + TOKEN_LIFETIME_SECONDS
            return _token
    except Exception as e:
        print(f"TVDB login failed: {e}")
        return None


async def _get_token() -> str | None:
    """Get a valid bearer token, refreshing if needed."""
    global _token, _token_expires

    if _token and time.time() < _token_expires:
        return _token

    return await _login()


async def get_series_id_from_episode(episode_tvdb_id: int) -> int | None:
    """
    Look up the series TVDB ID from an episode TVDB ID.

    Returns the series ID or None if not found.
    """
    token = await _get_token()
    if not token:
        return None

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{TVDB_BASE_URL}/episodes/{episode_tvdb_id}",
                headers={"Authorization": f"Bearer {token}"},
                timeout=10.0
            )
            response.raise_for_status()
            data = response.json()
            return data.get("data", {}).get("seriesId")
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            # Episode not found
            return None
        print(f"TVDB episode lookup failed: {e}")
        return None
    except Exception as e:
        print(f"TVDB episode lookup failed: {e}")
        return None
