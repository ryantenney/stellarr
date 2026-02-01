"""
Authentication API routes for multi-tenant Overseer Lite.
"""
from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, HTTPException, Request, Response, Query, Depends
from pydantic import BaseModel

from config import get_settings
from auth import (
    create_session_token,
    create_legacy_token,
    get_session_user,
    get_session_user_compat,
    SessionUser,
)
import plex_auth
from tenants import (
    create_tenant,
    get_tenant_by_plex_id,
    get_tenant_by_id,
    get_tenant_by_slug,
    verify_guest_access_code,
    create_guest,
    update_tenant_login,
    update_guest_activity,
)

settings = get_settings()
router = APIRouter(prefix="/auth", tags=["auth"])

# In-memory store for pending Plex PINs
# In production, consider using Redis or database
_pending_pins: dict[int, plex_auth.PlexPin] = {}


# --- Plex OAuth Routes ---

class PlexLoginResponse(BaseModel):
    auth_url: str
    pin_id: int


@router.get("/plex/login")
async def plex_login(request: Request) -> PlexLoginResponse:
    """
    Initiate Plex OAuth login.

    Returns a URL to redirect the user to for Plex authentication.
    """
    if not settings.is_multi_tenant:
        raise HTTPException(
            status_code=400,
            detail="Plex login is only available in multi-tenant mode"
        )

    # Create a new PIN
    pin = await plex_auth.create_pin()

    # Store PIN for later verification
    _pending_pins[pin.id] = pin

    # Build callback URL
    base_url = settings.base_url or str(request.base_url).rstrip("/")
    callback_url = f"{base_url}/auth/plex/callback?pin_id={pin.id}"

    # Get Plex auth URL
    auth_url = plex_auth.get_auth_url(pin, callback_url)

    return PlexLoginResponse(auth_url=auth_url, pin_id=pin.id)


class PlexCallbackResponse(BaseModel):
    success: bool
    token: Optional[str] = None
    user: Optional[dict] = None
    is_new_user: bool = False
    needs_setup: bool = False


@router.get("/plex/callback")
async def plex_callback(
    pin_id: int = Query(...),
    request: Request = None
) -> PlexCallbackResponse:
    """
    Handle Plex OAuth callback.

    Exchanges the PIN for an auth token and creates/updates the tenant.
    """
    if not settings.is_multi_tenant:
        raise HTTPException(
            status_code=400,
            detail="Plex login is only available in multi-tenant mode"
        )

    # Check the PIN status
    try:
        pin = await plex_auth.check_pin(pin_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to check PIN: {e}")

    if not pin.auth_token:
        raise HTTPException(
            status_code=400,
            detail="Authorization not completed. Please complete the Plex login."
        )

    # Get user info from Plex
    try:
        plex_user = await plex_auth.get_user(pin.auth_token)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to get user info: {e}")

    # Clean up pending PIN
    _pending_pins.pop(pin_id, None)

    # Check if tenant already exists
    existing_tenant = await get_tenant_by_plex_id(plex_user.id)

    if existing_tenant:
        # Update login timestamp
        await update_tenant_login(existing_tenant["id"])

        # Create session token
        token = create_session_token(
            user_type="owner",
            tenant_id=existing_tenant["id"],
            user_id=plex_user.id,
            name=plex_user.username,
            plex_thumb=plex_user.thumb
        )

        return PlexCallbackResponse(
            success=True,
            token=token,
            user={
                "id": plex_user.id,
                "username": plex_user.username,
                "email": plex_user.email,
                "thumb": plex_user.thumb,
                "tenant_id": existing_tenant["id"],
                "slug": existing_tenant["slug"],
            },
            is_new_user=False,
            needs_setup=not existing_tenant.get("plex_server_id")
        )
    else:
        # Create new tenant
        tenant = await create_tenant(
            plex_user_id=plex_user.id,
            plex_username=plex_user.username,
            plex_token=pin.auth_token,
            plex_email=plex_user.email,
            plex_thumb=plex_user.thumb
        )

        # Create session token
        token = create_session_token(
            user_type="owner",
            tenant_id=tenant["id"],
            user_id=plex_user.id,
            name=plex_user.username,
            plex_thumb=plex_user.thumb
        )

        return PlexCallbackResponse(
            success=True,
            token=token,
            user={
                "id": plex_user.id,
                "username": plex_user.username,
                "email": plex_user.email,
                "thumb": plex_user.thumb,
                "tenant_id": tenant["id"],
                "slug": tenant["slug"],
            },
            is_new_user=True,
            needs_setup=True
        )


@router.get("/plex/poll/{pin_id}")
async def plex_poll(pin_id: int) -> PlexCallbackResponse:
    """
    Poll for Plex PIN authorization status.

    Alternative to callback - client polls this until auth completes.
    """
    if not settings.is_multi_tenant:
        raise HTTPException(
            status_code=400,
            detail="Plex login is only available in multi-tenant mode"
        )

    try:
        pin = await plex_auth.check_pin(pin_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to check PIN: {e}")

    if not pin.auth_token:
        return PlexCallbackResponse(success=False)

    # Auth completed - same logic as callback
    return await plex_callback(pin_id)


# --- Guest Authentication ---

class GuestLoginRequest(BaseModel):
    tenant_slug: str
    access_code: str
    display_name: Optional[str] = None


class GuestLoginResponse(BaseModel):
    success: bool
    token: Optional[str] = None
    tenant: Optional[dict] = None
    guest_id: Optional[str] = None


@router.post("/guest")
async def guest_login(data: GuestLoginRequest) -> GuestLoginResponse:
    """
    Authenticate as a guest using an access code.
    """
    # Get tenant by slug
    tenant = await get_tenant_by_slug(data.tenant_slug)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # Verify access code
    if not await verify_guest_access_code(tenant["id"], data.access_code):
        raise HTTPException(status_code=401, detail="Invalid access code")

    # Create guest record
    guest = await create_guest(
        tenant_id=tenant["id"],
        display_name=data.display_name
    )

    # Create session token
    token = create_session_token(
        user_type="guest",
        tenant_id=tenant["id"],
        user_id=guest["id"],
        name=data.display_name
    )

    return GuestLoginResponse(
        success=True,
        token=token,
        tenant={
            "id": tenant["id"],
            "slug": tenant["slug"],
            "display_name": tenant.get("display_name") or tenant.get("plex_server_name"),
        },
        guest_id=guest["id"]
    )


# --- Legacy Password Authentication (backward compatibility) ---

class LegacyPasswordCheck(BaseModel):
    password: str


class LegacyAuthResponse(BaseModel):
    valid: bool
    token: Optional[str] = None


@router.post("/verify")
async def verify_legacy_password(data: LegacyPasswordCheck) -> LegacyAuthResponse:
    """
    Legacy password verification for single-tenant mode.
    """
    import secrets as sec

    if settings.is_multi_tenant:
        raise HTTPException(
            status_code=400,
            detail="Legacy password auth is disabled in multi-tenant mode. Use /auth/plex/login or /auth/guest"
        )

    if sec.compare_digest(data.password, settings.preshared_password):
        token = create_legacy_token()
        return LegacyAuthResponse(valid=True, token=token)

    raise HTTPException(status_code=401, detail="Invalid password")


# --- Session Info ---

class UserInfoResponse(BaseModel):
    authenticated: bool
    type: Optional[str] = None
    tenant_id: Optional[str] = None
    user_id: Optional[str] = None
    name: Optional[str] = None
    plex_thumb: Optional[str] = None
    tenant: Optional[dict] = None


@router.get("/me")
async def get_current_user(
    user: SessionUser = Depends(get_session_user_compat)
) -> UserInfoResponse:
    """
    Get information about the current authenticated user.
    """
    response = UserInfoResponse(
        authenticated=True,
        type=user.type,
        tenant_id=user.tenant_id,
        user_id=user.user_id,
        name=user.name,
        plex_thumb=user.plex_thumb
    )

    # Include tenant info if available
    if user.tenant_id:
        tenant = await get_tenant_by_id(user.tenant_id)
        if tenant:
            response.tenant = {
                "id": tenant["id"],
                "slug": tenant["slug"],
                "display_name": tenant.get("display_name") or tenant.get("plex_server_name"),
                "plex_server_name": tenant.get("plex_server_name"),
            }

            # Update activity
            if user.type == "guest" and user.user_id:
                await update_guest_activity(user.user_id)

    return response


@router.post("/logout")
async def logout():
    """
    Logout endpoint.

    Tokens are stateless, so this just returns success.
    Client should clear the stored token.
    """
    return {"success": True}


# --- Auth Params (for PBKDF2 iterations - legacy compatibility) ---

@router.get("/params")
async def get_auth_params():
    """
    Get authentication parameters (for legacy PBKDF2 client).
    """
    return {
        "iterations": 100000,
        "multi_tenant": settings.is_multi_tenant
    }
