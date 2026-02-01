"""
Authentication module for multi-tenant Overseer Lite.

Supports:
- Plex OAuth for server owners
- Access code authentication for guests
- Legacy preshared password (backward compatibility)
"""
from __future__ import annotations

import json
import time
import hmac
import hashlib
import base64
import secrets
from typing import Optional, Literal
from dataclasses import dataclass

from fastapi import HTTPException, Header, Request, Query
from pydantic import BaseModel

from config import get_settings

settings = get_settings()

# Session duration: 30 days in seconds
SESSION_DURATION_SECONDS = 30 * 24 * 60 * 60


@dataclass
class SessionUser:
    """Represents an authenticated user (owner or guest)."""
    type: Literal["owner", "guest", "legacy"]
    tenant_id: Optional[str] = None
    user_id: Optional[str] = None  # plex_user_id for owners, guest_id for guests
    name: Optional[str] = None
    plex_thumb: Optional[str] = None


class SessionToken(BaseModel):
    """JWT-like session token payload."""
    type: str  # "owner", "guest", or "legacy"
    tenant_id: Optional[str] = None
    user_id: Optional[str] = None
    name: Optional[str] = None
    plex_thumb: Optional[str] = None
    exp: int  # Expiration timestamp


def create_session_token(
    user_type: str,
    tenant_id: Optional[str] = None,
    user_id: Optional[str] = None,
    name: Optional[str] = None,
    plex_thumb: Optional[str] = None,
) -> str:
    """
    Create a signed session token.

    Token format: base64(payload).signature
    """
    payload = SessionToken(
        type=user_type,
        tenant_id=tenant_id,
        user_id=user_id,
        name=name,
        plex_thumb=plex_thumb,
        exp=int(time.time()) + SESSION_DURATION_SECONDS
    )

    # Encode payload
    payload_json = payload.model_dump_json()
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode()).decode().rstrip("=")

    # Sign
    signature = hmac.new(
        settings.app_secret_key.encode(),
        payload_b64.encode(),
        hashlib.sha256
    ).digest()
    sig_b64 = base64.urlsafe_b64encode(signature).decode().rstrip("=")

    return f"{payload_b64}.{sig_b64}"


def verify_session_token(token: str) -> SessionToken:
    """
    Verify and decode a session token.

    Raises:
        HTTPException: If token is invalid or expired
    """
    try:
        parts = token.split(".", 1)
        if len(parts) != 2:
            raise ValueError("Invalid token format")

        payload_b64, sig_b64 = parts

        # Verify signature
        expected_sig = hmac.new(
            settings.app_secret_key.encode(),
            payload_b64.encode(),
            hashlib.sha256
        ).digest()
        expected_b64 = base64.urlsafe_b64encode(expected_sig).decode().rstrip("=")

        if not secrets.compare_digest(sig_b64, expected_b64):
            raise ValueError("Invalid signature")

        # Decode payload (add padding back)
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding

        payload_json = base64.urlsafe_b64decode(payload_b64).decode()
        payload = SessionToken.model_validate_json(payload_json)

        # Check expiration
        if time.time() > payload.exp:
            raise ValueError("Token expired")

        return payload

    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")


def get_session_user(
    authorization: Optional[str] = Header(None, alias="Authorization")
) -> SessionUser:
    """
    FastAPI dependency to get the current authenticated user.

    Returns SessionUser or raises HTTPException if not authenticated.
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")

    # Expect "Bearer <token>"
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid authorization format")

    token = verify_session_token(parts[1])

    return SessionUser(
        type=token.type,
        tenant_id=token.tenant_id,
        user_id=token.user_id,
        name=token.name,
        plex_thumb=token.plex_thumb
    )


def get_optional_session_user(
    authorization: Optional[str] = Header(None, alias="Authorization")
) -> Optional[SessionUser]:
    """
    FastAPI dependency to optionally get the current user.

    Returns SessionUser if authenticated, None otherwise.
    """
    if not authorization:
        return None

    try:
        return get_session_user(authorization)
    except HTTPException:
        return None


def require_owner(user: SessionUser = None) -> SessionUser:
    """
    FastAPI dependency that requires an owner session.

    Use as: user: SessionUser = Depends(require_owner)
    """
    if user is None:
        raise HTTPException(status_code=401, detail="Authorization required")

    if user.type != "owner":
        raise HTTPException(status_code=403, detail="Owner access required")

    return user


def require_tenant_access(user: SessionUser = None) -> SessionUser:
    """
    FastAPI dependency that requires owner or guest access to a tenant.

    Use as: user: SessionUser = Depends(require_tenant_access)
    """
    if user is None:
        raise HTTPException(status_code=401, detail="Authorization required")

    if user.type not in ("owner", "guest"):
        raise HTTPException(status_code=403, detail="Tenant access required")

    if not user.tenant_id:
        raise HTTPException(status_code=403, detail="No tenant context")

    return user


# --- Legacy Token Support (backward compatibility) ---

def create_legacy_token() -> str:
    """Create a legacy session token (for single-tenant mode)."""
    timestamp = str(int(time.time()))
    signature = hmac.new(
        settings.app_secret_key.encode(),
        timestamp.encode(),
        hashlib.sha256
    ).digest()
    sig_b64 = base64.urlsafe_b64encode(signature).decode().rstrip("=")
    return f"{timestamp}.{sig_b64}"


def verify_legacy_token(token: str) -> bool:
    """Verify a legacy session token."""
    try:
        timestamp_str, sig_b64 = token.split(".", 1)
        timestamp = int(timestamp_str)
    except (ValueError, AttributeError):
        return False

    # Check if expired
    if time.time() - timestamp > SESSION_DURATION_SECONDS:
        return False

    # Verify signature
    expected_sig = hmac.new(
        settings.app_secret_key.encode(),
        timestamp_str.encode(),
        hashlib.sha256
    ).digest()
    expected_b64 = base64.urlsafe_b64encode(expected_sig).decode().rstrip("=")

    return secrets.compare_digest(sig_b64, expected_b64)


def get_session_user_compat(
    authorization: Optional[str] = Header(None, alias="Authorization")
) -> SessionUser:
    """
    Compatible session dependency that handles both new and legacy tokens.

    In multi-tenant mode: Uses new JWT-like tokens
    In single-tenant mode: Accepts legacy tokens
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")

    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid authorization format")

    token = parts[1]

    # Try new token format first
    if "." in token:
        try:
            # Check if it's a legacy token (timestamp.signature)
            timestamp_str = token.split(".")[0]
            if timestamp_str.isdigit():
                # Legacy token format
                if verify_legacy_token(token):
                    return SessionUser(type="legacy")
                raise HTTPException(status_code=401, detail="Invalid or expired token")
        except Exception:
            pass

        # Try new JWT-like format
        try:
            session = verify_session_token(token)
            return SessionUser(
                type=session.type,
                tenant_id=session.tenant_id,
                user_id=session.user_id,
                name=session.name,
                plex_thumb=session.plex_thumb
            )
        except HTTPException:
            raise

    raise HTTPException(status_code=401, detail="Invalid token format")


# --- Tenant Context from Request ---

@dataclass
class TenantContext:
    """Resolved tenant context from request."""
    tenant_id: str
    slug: str
    display_name: Optional[str] = None


async def get_tenant_from_request(request: Request) -> Optional[TenantContext]:
    """
    Resolve tenant context from the request.

    Checks in order:
    1. Custom domain header (from reverse proxy)
    2. Host header for custom domain
    3. Subdomain (slug.base_domain)
    4. Path prefix (/t/{slug}/)

    Returns None if no tenant context found.
    """
    from tenants import get_tenant_by_custom_domain, get_tenant_by_slug

    host = request.headers.get("host", "").lower().split(":")[0]

    # Check custom domain header (set by reverse proxy)
    custom_domain_header = request.headers.get("x-custom-domain")
    if custom_domain_header:
        tenant = await get_tenant_by_custom_domain(custom_domain_header)
        if tenant:
            return TenantContext(
                tenant_id=tenant["id"],
                slug=tenant["slug"],
                display_name=tenant.get("display_name")
            )

    # Check if host is a custom domain
    if settings.base_domain and not host.endswith(settings.base_domain):
        tenant = await get_tenant_by_custom_domain(host)
        if tenant:
            return TenantContext(
                tenant_id=tenant["id"],
                slug=tenant["slug"],
                display_name=tenant.get("display_name")
            )

    # Check subdomain
    if settings.base_domain and host.endswith(settings.base_domain):
        subdomain = host.replace(f".{settings.base_domain}", "")
        if subdomain and subdomain != host:
            tenant = await get_tenant_by_slug(subdomain)
            if tenant:
                return TenantContext(
                    tenant_id=tenant["id"],
                    slug=tenant["slug"],
                    display_name=tenant.get("display_name")
                )

    # Check path prefix /t/{slug}/
    path = request.url.path
    if path.startswith("/t/"):
        parts = path.split("/")
        if len(parts) >= 3:
            slug = parts[2]
            tenant = await get_tenant_by_slug(slug)
            if tenant:
                return TenantContext(
                    tenant_id=tenant["id"],
                    slug=tenant["slug"],
                    display_name=tenant.get("display_name")
                )

    return None


def verify_webhook_token(
    token: Optional[str] = Query(None, alias="token"),
    tenant_id: Optional[str] = None
):
    """
    Verify webhook token for a tenant or legacy mode.

    In multi-tenant mode: Token is per-tenant
    In single-tenant mode: Uses PLEX_WEBHOOK_TOKEN env var
    """
    if settings.is_multi_tenant:
        if not tenant_id:
            raise HTTPException(status_code=400, detail="Tenant ID required for webhook")

        from tenants import get_tenant_by_webhook_token
        import asyncio

        # Run async lookup
        loop = asyncio.new_event_loop()
        try:
            tenant = loop.run_until_complete(get_tenant_by_webhook_token(token or ""))
        finally:
            loop.close()

        if not tenant or tenant["id"] != tenant_id:
            raise HTTPException(status_code=401, detail="Invalid webhook token")

        return True
    else:
        # Legacy single-tenant mode
        if not settings.plex_webhook_token:
            raise HTTPException(status_code=401, detail="Plex webhook not configured")

        if not token:
            raise HTTPException(status_code=401, detail="Webhook token required")

        if not secrets.compare_digest(token, settings.plex_webhook_token):
            raise HTTPException(status_code=401, detail="Invalid webhook token")

        return True
