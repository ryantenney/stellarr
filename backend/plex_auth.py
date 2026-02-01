"""
Plex OAuth authentication flow.

Flow:
1. Request a PIN from Plex API
2. Redirect user to Plex login page with the PIN code
3. Poll for PIN status or use callback
4. Exchange completed PIN for auth token
5. Fetch user info using the token
"""
from __future__ import annotations

import httpx
from typing import Optional
from dataclasses import dataclass

from config import get_settings

settings = get_settings()

PLEX_API_BASE = "https://plex.tv/api/v2"
PLEX_AUTH_URL = "https://app.plex.tv/auth"


def _get_plex_headers(token: Optional[str] = None) -> dict:
    """Get common Plex API headers."""
    headers = {
        "Accept": "application/json",
        "X-Plex-Client-Identifier": settings.plex_client_identifier,
        "X-Plex-Product": settings.plex_product_name,
        "X-Plex-Version": "1.0.0",
        "X-Plex-Platform": "Web",
        "X-Plex-Device": "Browser",
    }
    if token:
        headers["X-Plex-Token"] = token
    return headers


@dataclass
class PlexPin:
    """Represents a Plex authentication PIN."""
    id: int
    code: str
    auth_token: Optional[str] = None
    expires_at: Optional[str] = None


@dataclass
class PlexUser:
    """Represents a Plex user."""
    id: str
    username: str
    email: Optional[str] = None
    thumb: Optional[str] = None
    auth_token: str = ""


async def create_pin() -> PlexPin:
    """
    Create a new PIN for Plex OAuth.

    Returns:
        PlexPin with id and code for authorization
    """
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{PLEX_API_BASE}/pins",
            headers=_get_plex_headers(),
            data={"strong": "true"}
        )
        response.raise_for_status()
        data = response.json()

        return PlexPin(
            id=data["id"],
            code=data["code"],
            expires_at=data.get("expiresAt")
        )


def get_auth_url(pin: PlexPin, callback_url: Optional[str] = None) -> str:
    """
    Get the Plex authorization URL for user login.

    Args:
        pin: The PIN from create_pin()
        callback_url: Optional URL to redirect after authorization

    Returns:
        URL to redirect the user to for Plex login
    """
    params = [
        f"clientID={settings.plex_client_identifier}",
        f"code={pin.code}",
        f"context[device][product]={settings.plex_product_name}",
    ]

    if callback_url:
        # Plex will redirect back to this URL after auth
        params.append(f"forwardUrl={callback_url}")

    return f"{PLEX_AUTH_URL}#!?{'&'.join(params)}"


async def check_pin(pin_id: int) -> PlexPin:
    """
    Check the status of a PIN.

    Args:
        pin_id: The PIN ID from create_pin()

    Returns:
        PlexPin with auth_token if authorization completed
    """
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{PLEX_API_BASE}/pins/{pin_id}",
            headers=_get_plex_headers()
        )
        response.raise_for_status()
        data = response.json()

        return PlexPin(
            id=data["id"],
            code=data["code"],
            auth_token=data.get("authToken"),
            expires_at=data.get("expiresAt")
        )


async def get_user(token: str) -> PlexUser:
    """
    Get user information using a Plex auth token.

    Args:
        token: Plex auth token

    Returns:
        PlexUser with user information
    """
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{PLEX_API_BASE}/user",
            headers=_get_plex_headers(token)
        )
        response.raise_for_status()
        data = response.json()

        return PlexUser(
            id=str(data["id"]),
            username=data.get("username", data.get("title", "Unknown")),
            email=data.get("email"),
            thumb=data.get("thumb"),
            auth_token=token
        )


async def get_servers(token: str) -> list[dict]:
    """
    Get list of Plex servers accessible to the user.

    Args:
        token: Plex auth token

    Returns:
        List of server dictionaries with connection info
    """
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{PLEX_API_BASE}/resources",
            headers=_get_plex_headers(token),
            params={"includeHttps": 1, "includeRelay": 1}
        )
        response.raise_for_status()
        data = response.json()

        servers = []
        for resource in data:
            if resource.get("provides") == "server":
                # Find the best connection URL
                connections = resource.get("connections", [])
                # Prefer local, then relay, then remote
                connection_url = None
                for conn in connections:
                    if conn.get("local"):
                        connection_url = conn.get("uri")
                        break
                if not connection_url:
                    for conn in connections:
                        if conn.get("relay"):
                            connection_url = conn.get("uri")
                            break
                if not connection_url and connections:
                    connection_url = connections[0].get("uri")

                servers.append({
                    "id": resource.get("clientIdentifier"),
                    "name": resource.get("name"),
                    "url": connection_url,
                    "owned": resource.get("owned", False),
                    "home": resource.get("home", False),
                    "access_token": resource.get("accessToken"),
                })

        return servers


async def get_libraries(server_url: str, token: str) -> list[dict]:
    """
    Get list of libraries from a Plex server.

    Args:
        server_url: Plex server URL
        token: Plex auth token (server-specific or user token)

    Returns:
        List of library dictionaries
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{server_url}/library/sections",
            headers=_get_plex_headers(token)
        )
        response.raise_for_status()
        data = response.json()

        libraries = []
        for container in data.get("MediaContainer", {}).get("Directory", []):
            lib_type = container.get("type")
            if lib_type in ("movie", "show"):
                libraries.append({
                    "key": container.get("key"),
                    "title": container.get("title"),
                    "type": "movie" if lib_type == "movie" else "tv",
                    "uuid": container.get("uuid"),
                })

        return libraries


async def get_library_items(
    server_url: str,
    token: str,
    library_key: str,
    start: int = 0,
    size: int = 100
) -> tuple[list[dict], int]:
    """
    Get items from a Plex library with pagination.

    Args:
        server_url: Plex server URL
        token: Plex auth token
        library_key: Library key from get_libraries()
        start: Starting offset
        size: Number of items to fetch

    Returns:
        Tuple of (items list, total count)
    """
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.get(
            f"{server_url}/library/sections/{library_key}/all",
            headers=_get_plex_headers(token),
            params={
                "X-Plex-Container-Start": start,
                "X-Plex-Container-Size": size,
            }
        )
        response.raise_for_status()
        data = response.json()

        container = data.get("MediaContainer", {})
        total = container.get("totalSize", 0)

        items = []
        for metadata in container.get("Metadata", []):
            item = {
                "title": metadata.get("title"),
                "year": metadata.get("year"),
                "plex_key": metadata.get("key"),
                "plex_rating_key": metadata.get("ratingKey"),
            }

            # Extract external IDs from Guid array
            guids = metadata.get("Guid", [])
            for guid in guids:
                guid_id = guid.get("id", "")
                if guid_id.startswith("tmdb://"):
                    item["tmdb_id"] = int(guid_id.replace("tmdb://", ""))
                elif guid_id.startswith("tvdb://"):
                    item["tvdb_id"] = int(guid_id.replace("tvdb://", ""))
                elif guid_id.startswith("imdb://"):
                    item["imdb_id"] = guid_id.replace("imdb://", "")

            # Only include if we have at least TMDB or TVDB ID
            if item.get("tmdb_id") or item.get("tvdb_id"):
                items.append(item)

        return items, total


async def validate_token(token: str) -> bool:
    """
    Validate a Plex auth token.

    Args:
        token: Plex auth token to validate

    Returns:
        True if token is valid, False otherwise
    """
    try:
        await get_user(token)
        return True
    except Exception:
        return False
