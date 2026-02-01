"""
Tenant management API routes.
"""
from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Request, BackgroundTasks
from pydantic import BaseModel

from config import get_settings
from auth import get_session_user, require_owner, SessionUser
from tenants import (
    get_tenant_by_id,
    get_tenant_plex_token,
    update_tenant,
    update_plex_server_info,
    set_guest_access_code,
    regenerate_webhook_token,
    set_custom_domain,
    update_custom_domain_status,
    remove_custom_domain,
)
import plex_auth
from database import sync_library

settings = get_settings()
router = APIRouter(prefix="/api/tenant", tags=["tenant"])


# --- Setup & Server Selection ---

class ServerInfo(BaseModel):
    id: str
    name: str
    url: Optional[str] = None
    owned: bool = False


class ServersResponse(BaseModel):
    servers: list[ServerInfo]


@router.get("/servers")
async def get_plex_servers(
    user: SessionUser = Depends(get_session_user)
) -> ServersResponse:
    """
    Get list of Plex servers accessible to the owner.
    """
    if user.type != "owner":
        raise HTTPException(status_code=403, detail="Owner access required")

    if not user.tenant_id:
        raise HTTPException(status_code=400, detail="No tenant context")

    # Get decrypted Plex token
    plex_token = await get_tenant_plex_token(user.tenant_id)
    if not plex_token:
        raise HTTPException(status_code=400, detail="Plex token not found")

    # Get servers from Plex
    try:
        servers = await plex_auth.get_servers(plex_token)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch servers: {e}")

    return ServersResponse(
        servers=[
            ServerInfo(
                id=s["id"],
                name=s["name"],
                url=s["url"],
                owned=s["owned"]
            )
            for s in servers
            if s["owned"]  # Only show owned servers
        ]
    )


class SelectServerRequest(BaseModel):
    server_id: str


class SetupStatus(BaseModel):
    has_server: bool
    server_name: Optional[str] = None
    has_access_code: bool
    webhook_url: str
    library_synced: bool
    last_sync: Optional[str] = None
    custom_domain: Optional[str] = None
    custom_domain_status: Optional[str] = None


@router.post("/select-server")
async def select_plex_server(
    data: SelectServerRequest,
    background_tasks: BackgroundTasks,
    user: SessionUser = Depends(get_session_user)
) -> SetupStatus:
    """
    Select a Plex server and trigger initial library scan.
    """
    if user.type != "owner":
        raise HTTPException(status_code=403, detail="Owner access required")

    if not user.tenant_id:
        raise HTTPException(status_code=400, detail="No tenant context")

    tenant = await get_tenant_by_id(user.tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # Get Plex token
    plex_token = await get_tenant_plex_token(user.tenant_id)
    if not plex_token:
        raise HTTPException(status_code=400, detail="Plex token not found")

    # Get servers and find the selected one
    servers = await plex_auth.get_servers(plex_token)
    selected_server = next((s for s in servers if s["id"] == data.server_id), None)

    if not selected_server:
        raise HTTPException(status_code=404, detail="Server not found")

    if not selected_server["owned"]:
        raise HTTPException(status_code=403, detail="You can only select servers you own")

    # Update tenant with server info
    await update_plex_server_info(
        tenant_id=user.tenant_id,
        server_id=selected_server["id"],
        server_name=selected_server["name"],
        server_url=selected_server["url"]
    )

    # Queue background library scan
    background_tasks.add_task(
        scan_library_task,
        tenant_id=user.tenant_id,
        server_url=selected_server["url"],
        plex_token=plex_token
    )

    # Build webhook URL
    base_url = settings.base_url or ""
    webhook_url = f"{base_url}/webhook/plex/{user.tenant_id}?token={tenant['webhook_token']}"

    return SetupStatus(
        has_server=True,
        server_name=selected_server["name"],
        has_access_code=bool(tenant.get("guest_access_code_hash")),
        webhook_url=webhook_url,
        library_synced=False,  # Scan is in progress
        last_sync=tenant.get("last_library_sync"),
        custom_domain=tenant.get("custom_domain"),
        custom_domain_status=tenant.get("custom_domain_status"),
    )


async def scan_library_task(tenant_id: str, server_url: str, plex_token: str):
    """
    Background task to scan Plex library and sync to database.
    """
    try:
        # Get libraries
        libraries = await plex_auth.get_libraries(server_url, plex_token)

        for library in libraries:
            media_type = library["type"]
            library_key = library["key"]

            # Fetch all items with pagination
            all_items = []
            start = 0
            size = 100

            while True:
                items, total = await plex_auth.get_library_items(
                    server_url, plex_token, library_key, start, size
                )
                all_items.extend(items)
                start += size
                if start >= total:
                    break

            # Sync to database (clear first for full sync)
            if all_items:
                await sync_library_with_tenant(
                    tenant_id=tenant_id,
                    items=all_items,
                    media_type=media_type,
                    clear_first=True
                )

        # Update last sync timestamp
        await update_tenant(tenant_id, last_library_sync="CURRENT_TIMESTAMP")

        print(f"Library scan complete for tenant {tenant_id}")

    except Exception as e:
        print(f"Library scan failed for tenant {tenant_id}: {e}")


async def sync_library_with_tenant(
    tenant_id: str,
    items: list[dict],
    media_type: str,
    clear_first: bool = False
):
    """
    Sync library items with tenant_id.
    """
    import aiosqlite
    from config import get_settings
    settings = get_settings()

    async with aiosqlite.connect(settings.database_path) as db:
        if clear_first:
            await db.execute(
                "DELETE FROM library WHERE media_type = ? AND tenant_id = ?",
                (media_type, tenant_id)
            )

        for item in items:
            await db.execute(
                """
                INSERT OR REPLACE INTO library
                (tmdb_id, media_type, tvdb_id, title, tenant_id, synced_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (
                    item.get("tmdb_id"),
                    media_type,
                    item.get("tvdb_id"),
                    item.get("title"),
                    tenant_id
                )
            )

        await db.commit()


# --- Setup Status ---

@router.get("/setup")
async def get_setup_status(
    request: Request,
    user: SessionUser = Depends(get_session_user)
) -> SetupStatus:
    """
    Get current setup status for the owner.
    """
    if user.type != "owner":
        raise HTTPException(status_code=403, detail="Owner access required")

    if not user.tenant_id:
        raise HTTPException(status_code=400, detail="No tenant context")

    tenant = await get_tenant_by_id(user.tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # Build webhook URL
    base_url = settings.base_url or str(request.base_url).rstrip("/")
    webhook_url = f"{base_url}/webhook/plex/{user.tenant_id}?token={tenant['webhook_token']}"

    return SetupStatus(
        has_server=bool(tenant.get("plex_server_id")),
        server_name=tenant.get("plex_server_name"),
        has_access_code=bool(tenant.get("guest_access_code_hash")),
        webhook_url=webhook_url,
        library_synced=bool(tenant.get("last_library_sync")),
        last_sync=tenant.get("last_library_sync"),
        custom_domain=tenant.get("custom_domain"),
        custom_domain_status=tenant.get("custom_domain_status"),
    )


# --- Access Code Management ---

class SetAccessCodeRequest(BaseModel):
    access_code: str


class AccessCodeResponse(BaseModel):
    success: bool
    message: str


@router.post("/access-code")
async def set_access_code_endpoint(
    data: SetAccessCodeRequest,
    user: SessionUser = Depends(get_session_user)
) -> AccessCodeResponse:
    """
    Set or update the guest access code.
    """
    if user.type != "owner":
        raise HTTPException(status_code=403, detail="Owner access required")

    if not user.tenant_id:
        raise HTTPException(status_code=400, detail="No tenant context")

    if len(data.access_code) < 4:
        raise HTTPException(status_code=400, detail="Access code must be at least 4 characters")

    success = await set_guest_access_code(user.tenant_id, data.access_code)

    if success:
        return AccessCodeResponse(success=True, message="Access code updated")
    else:
        raise HTTPException(status_code=500, detail="Failed to update access code")


# --- Webhook Token Management ---

class RegenerateTokenResponse(BaseModel):
    webhook_token: str
    webhook_url: str


@router.post("/regenerate-webhook-token")
async def regenerate_webhook_token_endpoint(
    request: Request,
    user: SessionUser = Depends(get_session_user)
) -> RegenerateTokenResponse:
    """
    Regenerate the webhook token.
    """
    if user.type != "owner":
        raise HTTPException(status_code=403, detail="Owner access required")

    if not user.tenant_id:
        raise HTTPException(status_code=400, detail="No tenant context")

    new_token = await regenerate_webhook_token(user.tenant_id)
    if not new_token:
        raise HTTPException(status_code=500, detail="Failed to regenerate token")

    base_url = settings.base_url or str(request.base_url).rstrip("/")
    webhook_url = f"{base_url}/webhook/plex/{user.tenant_id}?token={new_token}"

    return RegenerateTokenResponse(
        webhook_token=new_token,
        webhook_url=webhook_url
    )


# --- Library Rescan ---

class RescanResponse(BaseModel):
    success: bool
    message: str


@router.post("/rescan-library")
async def rescan_library(
    background_tasks: BackgroundTasks,
    user: SessionUser = Depends(get_session_user)
) -> RescanResponse:
    """
    Trigger a full library rescan.
    """
    if user.type != "owner":
        raise HTTPException(status_code=403, detail="Owner access required")

    if not user.tenant_id:
        raise HTTPException(status_code=400, detail="No tenant context")

    tenant = await get_tenant_by_id(user.tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    if not tenant.get("plex_server_url"):
        raise HTTPException(status_code=400, detail="No Plex server configured")

    plex_token = await get_tenant_plex_token(user.tenant_id)
    if not plex_token:
        raise HTTPException(status_code=400, detail="Plex token not found")

    # Queue background scan
    background_tasks.add_task(
        scan_library_task,
        tenant_id=user.tenant_id,
        server_url=tenant["plex_server_url"],
        plex_token=plex_token
    )

    return RescanResponse(success=True, message="Library rescan started")


# --- Tenant Info ---

class TenantInfoResponse(BaseModel):
    id: str
    slug: str
    display_name: Optional[str] = None
    plex_username: str
    plex_server_name: Optional[str] = None
    created_at: str
    custom_domain: Optional[str] = None
    custom_domain_status: Optional[str] = None


@router.get("")
async def get_tenant_info(
    user: SessionUser = Depends(get_session_user)
) -> TenantInfoResponse:
    """
    Get tenant information.
    """
    if user.type != "owner":
        raise HTTPException(status_code=403, detail="Owner access required")

    if not user.tenant_id:
        raise HTTPException(status_code=400, detail="No tenant context")

    tenant = await get_tenant_by_id(user.tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    return TenantInfoResponse(
        id=tenant["id"],
        slug=tenant["slug"],
        display_name=tenant.get("display_name"),
        plex_username=tenant["plex_username"],
        plex_server_name=tenant.get("plex_server_name"),
        created_at=tenant["created_at"],
        custom_domain=tenant.get("custom_domain"),
        custom_domain_status=tenant.get("custom_domain_status"),
    )


class UpdateTenantRequest(BaseModel):
    display_name: Optional[str] = None


@router.patch("")
async def update_tenant_info(
    data: UpdateTenantRequest,
    user: SessionUser = Depends(get_session_user)
) -> TenantInfoResponse:
    """
    Update tenant information.
    """
    if user.type != "owner":
        raise HTTPException(status_code=403, detail="Owner access required")

    if not user.tenant_id:
        raise HTTPException(status_code=400, detail="No tenant context")

    updates = {}
    if data.display_name is not None:
        updates["display_name"] = data.display_name

    if updates:
        await update_tenant(user.tenant_id, **updates)

    return await get_tenant_info(user)


# --- Custom Domain (Cloudflare SSL for SaaS) ---

class CustomDomainRequest(BaseModel):
    domain: str


class CustomDomainResponse(BaseModel):
    domain: str
    status: str
    validation_txt: Optional[str] = None
    cname_target: Optional[str] = None
    message: str


@router.post("/domain")
async def add_custom_domain(
    data: CustomDomainRequest,
    user: SessionUser = Depends(get_session_user)
) -> CustomDomainResponse:
    """
    Add a custom domain for the tenant.

    Requires Cloudflare SSL for SaaS to be configured.
    """
    if user.type != "owner":
        raise HTTPException(status_code=403, detail="Owner access required")

    if not user.tenant_id:
        raise HTTPException(status_code=400, detail="No tenant context")

    if not settings.cf_api_token or not settings.cf_zone_id:
        raise HTTPException(
            status_code=400,
            detail="Custom domains are not configured on this server"
        )

    # Validate domain format
    domain = data.domain.lower().strip()
    if not domain or "." not in domain:
        raise HTTPException(status_code=400, detail="Invalid domain format")

    # Create custom hostname in Cloudflare
    try:
        import httpx

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"https://api.cloudflare.com/client/v4/zones/{settings.cf_zone_id}/custom_hostnames",
                headers={
                    "Authorization": f"Bearer {settings.cf_api_token}",
                    "Content-Type": "application/json",
                },
                json={
                    "hostname": domain,
                    "ssl": {
                        "method": "http",
                        "type": "dv",
                        "settings": {
                            "min_tls_version": "1.2"
                        }
                    }
                }
            )

            result = response.json()

            if not result.get("success"):
                errors = result.get("errors", [])
                error_msg = errors[0].get("message") if errors else "Unknown error"
                raise HTTPException(status_code=400, detail=f"Cloudflare error: {error_msg}")

            cf_data = result["result"]

            # Save to database
            await set_custom_domain(
                tenant_id=user.tenant_id,
                domain=domain,
                cf_id=cf_data["id"],
                status="pending_validation"
            )

            return CustomDomainResponse(
                domain=domain,
                status="pending_validation",
                cname_target=settings.cf_cname_target,
                message=f"Add a CNAME record pointing {domain} to {settings.cf_cname_target}"
            )

    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail=f"Failed to contact Cloudflare: {e}")


@router.get("/domain")
async def get_custom_domain_status(
    user: SessionUser = Depends(get_session_user)
) -> Optional[CustomDomainResponse]:
    """
    Get the current custom domain status.
    """
    if user.type != "owner":
        raise HTTPException(status_code=403, detail="Owner access required")

    if not user.tenant_id:
        raise HTTPException(status_code=400, detail="No tenant context")

    tenant = await get_tenant_by_id(user.tenant_id)
    if not tenant or not tenant.get("custom_domain"):
        return None

    # Check status with Cloudflare if pending
    if tenant.get("custom_domain_status") == "pending_validation" and tenant.get("custom_domain_cf_id"):
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"https://api.cloudflare.com/client/v4/zones/{settings.cf_zone_id}/custom_hostnames/{tenant['custom_domain_cf_id']}",
                    headers={
                        "Authorization": f"Bearer {settings.cf_api_token}",
                    }
                )

                result = response.json()
                if result.get("success"):
                    cf_data = result["result"]
                    ssl_status = cf_data.get("ssl", {}).get("status")

                    if ssl_status == "active":
                        await update_custom_domain_status(user.tenant_id, "active")
                        return CustomDomainResponse(
                            domain=tenant["custom_domain"],
                            status="active",
                            cname_target=settings.cf_cname_target,
                            message="Custom domain is active!"
                        )

        except Exception as e:
            print(f"Error checking domain status: {e}")

    return CustomDomainResponse(
        domain=tenant["custom_domain"],
        status=tenant.get("custom_domain_status", "unknown"),
        cname_target=settings.cf_cname_target,
        message=f"Add a CNAME record pointing {tenant['custom_domain']} to {settings.cf_cname_target}"
    )


@router.delete("/domain")
async def delete_custom_domain(
    user: SessionUser = Depends(get_session_user)
):
    """
    Remove the custom domain.
    """
    if user.type != "owner":
        raise HTTPException(status_code=403, detail="Owner access required")

    if not user.tenant_id:
        raise HTTPException(status_code=400, detail="No tenant context")

    tenant = await get_tenant_by_id(user.tenant_id)
    if not tenant or not tenant.get("custom_domain_cf_id"):
        raise HTTPException(status_code=404, detail="No custom domain configured")

    # Delete from Cloudflare
    try:
        import httpx

        async with httpx.AsyncClient() as client:
            await client.delete(
                f"https://api.cloudflare.com/client/v4/zones/{settings.cf_zone_id}/custom_hostnames/{tenant['custom_domain_cf_id']}",
                headers={
                    "Authorization": f"Bearer {settings.cf_api_token}",
                }
            )
    except Exception as e:
        print(f"Error deleting from Cloudflare: {e}")

    await remove_custom_domain(user.tenant_id)

    return {"success": True, "message": "Custom domain removed"}
