"""
Multi-tenant database operations for SQLite backend.
Handles tenants (Plex server owners) and guests.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

import aiosqlite

from config import get_settings
from crypto import encrypt, decrypt, hash_code, verify_code, generate_token, generate_slug

settings = get_settings()


async def init_tenant_tables():
    """Create tenant-related tables if they don't exist."""
    async with aiosqlite.connect(settings.database_path) as db:
        # Tenants table - Plex server owners
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tenants (
                id TEXT PRIMARY KEY,
                plex_user_id TEXT UNIQUE NOT NULL,
                plex_username TEXT NOT NULL,
                plex_email TEXT,
                plex_thumb TEXT,
                plex_token_encrypted TEXT NOT NULL,

                -- Plex server info
                plex_server_id TEXT,
                plex_server_name TEXT,
                plex_server_url TEXT,

                -- Tenant configuration
                slug TEXT UNIQUE NOT NULL,
                display_name TEXT,
                guest_access_code_hash TEXT,
                guest_access_code_salt TEXT,
                webhook_token TEXT NOT NULL,

                -- Custom domain (Cloudflare SSL for SaaS)
                custom_domain TEXT UNIQUE,
                custom_domain_status TEXT,
                custom_domain_cf_id TEXT,

                -- Settings
                settings_json TEXT DEFAULT '{}',

                -- Timestamps
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_library_sync TIMESTAMP,
                last_login TIMESTAMP
            )
        """)

        # Guests table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS guests (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                display_name TEXT,
                session_token_hash TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active TIMESTAMP,
                FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
            )
        """)

        # Create indexes
        await db.execute("CREATE INDEX IF NOT EXISTS idx_tenants_slug ON tenants(slug)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_tenants_custom_domain ON tenants(custom_domain)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_tenants_plex_user_id ON tenants(plex_user_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_guests_tenant_id ON guests(tenant_id)")

        await db.commit()


async def migrate_existing_tables():
    """Add tenant_id column to existing tables for multi-tenancy."""
    async with aiosqlite.connect(settings.database_path) as db:
        # Check and migrate requests table
        cursor = await db.execute("PRAGMA table_info(requests)")
        columns = [row[1] for row in await cursor.fetchall()]

        if 'tenant_id' not in columns:
            await db.execute("ALTER TABLE requests ADD COLUMN tenant_id TEXT")
            await db.execute("ALTER TABLE requests ADD COLUMN requested_by_guest_id TEXT")
            await db.execute("ALTER TABLE requests ADD COLUMN requested_by_name TEXT")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_requests_tenant_id ON requests(tenant_id)")

        # Check and migrate library table
        cursor = await db.execute("PRAGMA table_info(library)")
        columns = [row[1] for row in await cursor.fetchall()]

        if 'tenant_id' not in columns:
            await db.execute("ALTER TABLE library ADD COLUMN tenant_id TEXT")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_library_tenant_id ON library(tenant_id)")

        # Check and migrate plex_guid_cache table
        cursor = await db.execute("PRAGMA table_info(plex_guid_cache)")
        columns = [row[1] for row in await cursor.fetchall()]

        if 'tenant_id' not in columns:
            await db.execute("ALTER TABLE plex_guid_cache ADD COLUMN tenant_id TEXT")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_plex_guid_cache_tenant_id ON plex_guid_cache(tenant_id)")

        await db.commit()


# --- Tenant Operations ---

async def create_tenant(
    plex_user_id: str,
    plex_username: str,
    plex_token: str,
    plex_email: Optional[str] = None,
    plex_thumb: Optional[str] = None,
) -> dict:
    """
    Create a new tenant from Plex OAuth.

    Args:
        plex_user_id: Plex account ID
        plex_username: Plex display name
        plex_token: Plex auth token (will be encrypted)
        plex_email: Plex email (optional)
        plex_thumb: Plex avatar URL (optional)

    Returns:
        Created tenant dict
    """
    tenant_id = str(uuid.uuid4())
    slug = generate_slug(plex_username)
    webhook_token = generate_token(24)

    # Encrypt the Plex token
    if not settings.encryption_key:
        raise ValueError("ENCRYPTION_KEY must be set for multi-tenant mode")

    encrypted_token = encrypt(plex_token, settings.encryption_key)

    async with aiosqlite.connect(settings.database_path) as db:
        await db.execute(
            """
            INSERT INTO tenants (
                id, plex_user_id, plex_username, plex_email, plex_thumb,
                plex_token_encrypted, slug, webhook_token, created_at, last_login
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (tenant_id, plex_user_id, plex_username, plex_email, plex_thumb,
             encrypted_token, slug, webhook_token)
        )
        await db.commit()

    return {
        'id': tenant_id,
        'plex_user_id': plex_user_id,
        'plex_username': plex_username,
        'plex_email': plex_email,
        'plex_thumb': plex_thumb,
        'slug': slug,
        'webhook_token': webhook_token,
    }


async def get_tenant_by_plex_id(plex_user_id: str) -> Optional[dict]:
    """Get a tenant by their Plex user ID."""
    async with aiosqlite.connect(settings.database_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM tenants WHERE plex_user_id = ?",
            (plex_user_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_tenant_by_id(tenant_id: str) -> Optional[dict]:
    """Get a tenant by their ID."""
    async with aiosqlite.connect(settings.database_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM tenants WHERE id = ?",
            (tenant_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_tenant_by_slug(slug: str) -> Optional[dict]:
    """Get a tenant by their URL slug."""
    async with aiosqlite.connect(settings.database_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM tenants WHERE slug = ?",
            (slug,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_tenant_by_custom_domain(domain: str) -> Optional[dict]:
    """Get a tenant by their custom domain."""
    async with aiosqlite.connect(settings.database_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM tenants WHERE custom_domain = ? AND custom_domain_status = 'active'",
            (domain.lower(),)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_tenant_by_webhook_token(token: str) -> Optional[dict]:
    """Get a tenant by their webhook token."""
    async with aiosqlite.connect(settings.database_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM tenants WHERE webhook_token = ?",
            (token,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def update_tenant(tenant_id: str, **updates) -> bool:
    """Update tenant fields."""
    if not updates:
        return False

    # Build SET clause dynamically
    set_parts = []
    values = []
    for key, value in updates.items():
        set_parts.append(f"{key} = ?")
        values.append(value)

    # Always update updated_at
    set_parts.append("updated_at = CURRENT_TIMESTAMP")
    values.append(tenant_id)

    async with aiosqlite.connect(settings.database_path) as db:
        try:
            await db.execute(
                f"UPDATE tenants SET {', '.join(set_parts)} WHERE id = ?",
                values
            )
            await db.commit()
            return True
        except Exception as e:
            print(f"Error updating tenant: {e}")
            return False


async def update_tenant_plex_token(tenant_id: str, plex_token: str) -> bool:
    """Update a tenant's encrypted Plex token."""
    if not settings.encryption_key:
        raise ValueError("ENCRYPTION_KEY must be set")

    encrypted_token = encrypt(plex_token, settings.encryption_key)
    return await update_tenant(tenant_id, plex_token_encrypted=encrypted_token)


async def get_tenant_plex_token(tenant_id: str) -> Optional[str]:
    """Get decrypted Plex token for a tenant."""
    tenant = await get_tenant_by_id(tenant_id)
    if not tenant or not tenant.get('plex_token_encrypted'):
        return None

    if not settings.encryption_key:
        raise ValueError("ENCRYPTION_KEY must be set")

    try:
        return decrypt(tenant['plex_token_encrypted'], settings.encryption_key)
    except Exception as e:
        print(f"Error decrypting Plex token: {e}")
        return None


async def set_guest_access_code(tenant_id: str, access_code: str) -> bool:
    """Set or update the guest access code for a tenant."""
    hash_value, salt = hash_code(access_code)
    return await update_tenant(
        tenant_id,
        guest_access_code_hash=hash_value,
        guest_access_code_salt=salt
    )


async def verify_guest_access_code(tenant_id: str, access_code: str) -> bool:
    """Verify a guest access code for a tenant."""
    tenant = await get_tenant_by_id(tenant_id)
    if not tenant:
        return False

    stored_hash = tenant.get('guest_access_code_hash')
    stored_salt = tenant.get('guest_access_code_salt')

    if not stored_hash or not stored_salt:
        return False

    return verify_code(access_code, stored_hash, stored_salt)


async def regenerate_webhook_token(tenant_id: str) -> Optional[str]:
    """Regenerate the webhook token for a tenant."""
    new_token = generate_token(24)
    success = await update_tenant(tenant_id, webhook_token=new_token)
    return new_token if success else None


async def update_tenant_login(tenant_id: str) -> bool:
    """Update the last login timestamp."""
    async with aiosqlite.connect(settings.database_path) as db:
        try:
            await db.execute(
                "UPDATE tenants SET last_login = CURRENT_TIMESTAMP WHERE id = ?",
                (tenant_id,)
            )
            await db.commit()
            return True
        except Exception:
            return False


async def update_plex_server_info(
    tenant_id: str,
    server_id: str,
    server_name: str,
    server_url: str
) -> bool:
    """Update Plex server information for a tenant."""
    return await update_tenant(
        tenant_id,
        plex_server_id=server_id,
        plex_server_name=server_name,
        plex_server_url=server_url
    )


# --- Guest Operations ---

async def create_guest(
    tenant_id: str,
    display_name: Optional[str] = None
) -> dict:
    """Create a new guest for a tenant."""
    guest_id = str(uuid.uuid4())

    async with aiosqlite.connect(settings.database_path) as db:
        await db.execute(
            """
            INSERT INTO guests (id, tenant_id, display_name, created_at, last_active)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (guest_id, tenant_id, display_name)
        )
        await db.commit()

    return {
        'id': guest_id,
        'tenant_id': tenant_id,
        'display_name': display_name,
    }


async def get_guest_by_id(guest_id: str) -> Optional[dict]:
    """Get a guest by ID."""
    async with aiosqlite.connect(settings.database_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM guests WHERE id = ?",
            (guest_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def update_guest_activity(guest_id: str) -> bool:
    """Update the last active timestamp for a guest."""
    async with aiosqlite.connect(settings.database_path) as db:
        try:
            await db.execute(
                "UPDATE guests SET last_active = CURRENT_TIMESTAMP WHERE id = ?",
                (guest_id,)
            )
            await db.commit()
            return True
        except Exception:
            return False


async def get_tenant_guests(tenant_id: str) -> list[dict]:
    """Get all guests for a tenant."""
    async with aiosqlite.connect(settings.database_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM guests WHERE tenant_id = ? ORDER BY last_active DESC",
            (tenant_id,)
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


# --- Custom Domain Operations ---

async def set_custom_domain(
    tenant_id: str,
    domain: str,
    cf_id: str,
    status: str = 'pending_validation'
) -> bool:
    """Set or update custom domain for a tenant."""
    return await update_tenant(
        tenant_id,
        custom_domain=domain.lower(),
        custom_domain_cf_id=cf_id,
        custom_domain_status=status
    )


async def update_custom_domain_status(tenant_id: str, status: str) -> bool:
    """Update the status of a tenant's custom domain."""
    return await update_tenant(tenant_id, custom_domain_status=status)


async def remove_custom_domain(tenant_id: str) -> bool:
    """Remove custom domain from a tenant."""
    return await update_tenant(
        tenant_id,
        custom_domain=None,
        custom_domain_cf_id=None,
        custom_domain_status=None
    )
