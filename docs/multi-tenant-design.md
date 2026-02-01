# Multi-Tenant Overseer Lite - Architecture Design

## Overview

This document outlines the architecture for transforming Overseer Lite from a single-tenant, password-based system to a multi-tenant platform where Plex server owners can sign up, import their libraries, and invite guests to request media.

## Goals

1. **Plex Server Owner Authentication**: OAuth-based sign-in via Plex
2. **Secure Token Storage**: Encrypted storage of Plex auth tokens
3. **Library Import**: Initial scan of Plex libraries on signup
4. **Guest System**: Server owners can invite guests with simple access codes
5. **Webhook Configuration**: Provide per-tenant webhook URLs for Plex configuration
6. **Custom Domains**: Cloudflare SSL for SaaS integration for vanity domains

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Multi-Tenant Flow                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────┐    OAuth    ┌──────────────┐                              │
│  │ Plex Server  │◄───────────►│   plex.tv    │                              │
│  │    Owner     │             └──────────────┘                              │
│  └──────┬───────┘                                                           │
│         │ Signs in, configures webhook                                      │
│         ▼                                                                   │
│  ┌──────────────────────────────────────────────────────────────┐          │
│  │                     Overseer Lite                             │          │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐   │          │
│  │  │   Tenants   │  │   Guests    │  │   Custom Domains    │   │          │
│  │  │  (Owners)   │  │ (Invitees)  │  │ (Cloudflare SaaS)   │   │          │
│  │  └─────────────┘  └─────────────┘  └─────────────────────┘   │          │
│  └──────────────────────────────────────────────────────────────┘          │
│         │                     │                                             │
│         │ Webhook URL         │ Access Code                                 │
│         ▼                     ▼                                             │
│  ┌──────────────┐      ┌──────────────┐                                    │
│  │ Plex Server  │      │    Guest     │                                    │
│  │  Webhooks    │      │   Browser    │                                    │
│  └──────────────┘      └──────────────┘                                    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Database Schema

### New Tables

#### `tenants` - Plex Server Owners
```sql
CREATE TABLE tenants (
    id TEXT PRIMARY KEY,                    -- UUID
    plex_user_id TEXT UNIQUE NOT NULL,      -- Plex account ID
    plex_username TEXT NOT NULL,            -- Display name from Plex
    plex_email TEXT,                        -- Email from Plex (if available)
    plex_thumb TEXT,                        -- Avatar URL
    plex_token_encrypted TEXT NOT NULL,     -- AES-256-GCM encrypted Plex token

    -- Plex server info (populated after library scan)
    plex_server_id TEXT,                    -- Machine identifier
    plex_server_name TEXT,                  -- Server name
    plex_server_url TEXT,                   -- Connection URL (local or remote)

    -- Tenant configuration
    slug TEXT UNIQUE NOT NULL,              -- URL-friendly identifier (e.g., "johns-plex")
    display_name TEXT,                      -- Custom display name
    guest_access_code TEXT,                 -- Simple code for guest access
    guest_access_code_hash TEXT,            -- PBKDF2 hash of access code

    -- Custom domain (Cloudflare SSL for SaaS)
    custom_domain TEXT UNIQUE,              -- e.g., "requests.example.com"
    custom_domain_status TEXT,              -- pending_validation, active, failed
    custom_domain_cf_id TEXT,               -- Cloudflare custom hostname ID

    -- Settings
    settings_json TEXT DEFAULT '{}',        -- JSON blob for tenant settings

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_library_sync TIMESTAMP,
    last_login TIMESTAMP
);

CREATE INDEX idx_tenants_slug ON tenants(slug);
CREATE INDEX idx_tenants_custom_domain ON tenants(custom_domain);
CREATE INDEX idx_tenants_plex_user_id ON tenants(plex_user_id);
```

#### `guests` - Invited Users
```sql
CREATE TABLE guests (
    id TEXT PRIMARY KEY,                    -- UUID
    tenant_id TEXT NOT NULL,                -- FK to tenants

    -- Guest identity (optional - can be anonymous)
    display_name TEXT,                      -- Self-provided name

    -- Session tracking
    session_token_hash TEXT,                -- Hash of current session token

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_active TIMESTAMP,

    FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
);

CREATE INDEX idx_guests_tenant_id ON guests(tenant_id);
```

### Modified Tables

#### `requests` - Add tenant_id
```sql
ALTER TABLE requests ADD COLUMN tenant_id TEXT NOT NULL;
ALTER TABLE requests ADD COLUMN requested_by_guest_id TEXT;
ALTER TABLE requests ADD COLUMN requested_by_name TEXT;

CREATE INDEX idx_requests_tenant_id ON requests(tenant_id);
```

#### `library` - Add tenant_id
```sql
ALTER TABLE library ADD COLUMN tenant_id TEXT NOT NULL;

-- Modify primary key to include tenant_id
-- (tmdb_id, media_type, tenant_id) should be unique
CREATE UNIQUE INDEX idx_library_tenant_item ON library(tenant_id, tmdb_id, media_type);
```

#### `plex_guid_cache` - Add tenant_id
```sql
ALTER TABLE plex_guid_cache ADD COLUMN tenant_id TEXT NOT NULL;

CREATE INDEX idx_plex_guid_cache_tenant ON plex_guid_cache(tenant_id);
```

---

## Authentication Flows

### 1. Plex Server Owner Sign-In (OAuth)

```
┌─────────┐     ┌──────────────┐     ┌─────────────┐     ┌──────────┐
│ Browser │     │ Overseer API │     │  plex.tv    │     │ Database │
└────┬────┘     └──────┬───────┘     └──────┬──────┘     └────┬─────┘
     │                 │                    │                 │
     │ GET /auth/plex/login                 │                 │
     │────────────────►│                    │                 │
     │                 │                    │                 │
     │                 │ POST /api/v2/pins  │                 │
     │                 │───────────────────►│                 │
     │                 │                    │                 │
     │                 │   {id, code}       │                 │
     │                 │◄───────────────────│                 │
     │                 │                    │                 │
     │ Redirect to plex.tv/link?code=XXX   │                 │
     │◄────────────────│                    │                 │
     │                 │                    │                 │
     │ User authorizes ─────────────────────►                 │
     │                 │                    │                 │
     │ Callback: /auth/plex/callback?pin=ID│                 │
     │────────────────►│                    │                 │
     │                 │                    │                 │
     │                 │ GET /api/v2/pins/{id}                │
     │                 │───────────────────►│                 │
     │                 │                    │                 │
     │                 │   {authToken}      │                 │
     │                 │◄───────────────────│                 │
     │                 │                    │                 │
     │                 │ Encrypt token, create/update tenant  │
     │                 │───────────────────────────────────────►
     │                 │                    │                 │
     │                 │ Issue session JWT  │                 │
     │◄────────────────│                    │                 │
     │                 │                    │                 │
     │ Set cookie, redirect to /setup       │                 │
     │◄────────────────│                    │                 │
```

**Plex OAuth Implementation Details:**

1. **Request PIN**: `POST https://plex.tv/api/v2/pins`
   - Headers: `X-Plex-Client-Identifier`, `X-Plex-Product`, `X-Plex-Version`
   - Response: `{id: 12345, code: "ABCD"}`

2. **Redirect User**: `https://app.plex.tv/auth#!?clientID={clientId}&code={code}&context[device][product]=Overseer`

3. **Poll for Token**: `GET https://plex.tv/api/v2/pins/{id}`
   - Poll every 1-2 seconds until `authToken` is present
   - Or use callback URL if supported

4. **Get User Info**: `GET https://plex.tv/api/v2/user`
   - Headers: `X-Plex-Token: {authToken}`
   - Response includes: `id`, `username`, `email`, `thumb`

### 2. Guest Access (Simple Code)

```
┌─────────┐     ┌──────────────┐     ┌──────────┐
│ Browser │     │ Overseer API │     │ Database │
└────┬────┘     └──────┬───────┘     └────┬─────┘
     │                 │                  │
     │ Visit tenant URL (e.g., /t/johns-plex or custom domain)
     │────────────────►│                  │
     │                 │                  │
     │ Show access code prompt            │
     │◄────────────────│                  │
     │                 │                  │
     │ POST /auth/guest                   │
     │ {tenant_slug, access_code, name?}  │
     │────────────────►│                  │
     │                 │                  │
     │                 │ Verify code hash │
     │                 │─────────────────►│
     │                 │                  │
     │                 │ Create guest     │
     │                 │ session          │
     │                 │─────────────────►│
     │                 │                  │
     │ Session token (JWT)                │
     │◄────────────────│                  │
```

**Guest Session Token Claims:**
```json
{
  "type": "guest",
  "tenant_id": "uuid",
  "guest_id": "uuid",
  "name": "John",
  "exp": 1234567890
}
```

### 3. Owner Session Token Claims
```json
{
  "type": "owner",
  "tenant_id": "uuid",
  "plex_user_id": "12345",
  "username": "plexuser",
  "exp": 1234567890
}
```

---

## Plex Integration

### Webhook URL Structure

Each tenant gets a unique webhook URL:
```
https://overseer.example.com/webhook/plex/{tenant_id}?token={webhook_secret}
```

Or with custom domain:
```
https://requests.johndoe.com/webhook/plex?token={webhook_secret}
```

**Webhook Secret Generation:**
- Generated per-tenant on signup
- Stored hashed in database
- Displayed once to owner during setup

### Initial Library Scan

On first login, we scan the owner's Plex libraries:

1. **Get Servers**: `GET https://plex.tv/api/v2/resources?includeHttps=1`
2. **Get Libraries**: `GET {server_url}/library/sections`
3. **Get Items**: `GET {server_url}/library/sections/{id}/all`
4. **Extract IDs**: Parse TMDB/TVDB/IMDB IDs from GUIDs
5. **Bulk Insert**: Add to `library` table with `tenant_id`

### Library Sync Script

The existing `plex-sync.py` script needs modification to support tenant identification:
```bash
python plex-sync.py --tenant-id UUID --token SECRET
```

Or we provide a self-contained URL for owners:
```
https://overseer.example.com/sync/library/{tenant_id}?token={sync_token}
```

---

## Token Encryption

### Plex Token Storage

Plex auth tokens are encrypted at rest using AES-256-GCM:

```python
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import os

# Master key from environment (ENCRYPTION_KEY)
# Should be 32 bytes, base64 encoded in env var

def encrypt_plex_token(token: str, master_key: bytes) -> str:
    """Encrypt Plex token for storage."""
    aesgcm = AESGCM(master_key)
    nonce = os.urandom(12)  # 96-bit nonce
    ciphertext = aesgcm.encrypt(nonce, token.encode(), None)
    # Return as base64: nonce || ciphertext
    return base64.b64encode(nonce + ciphertext).decode()

def decrypt_plex_token(encrypted: str, master_key: bytes) -> str:
    """Decrypt Plex token from storage."""
    data = base64.b64decode(encrypted)
    nonce, ciphertext = data[:12], data[12:]
    aesgcm = AESGCM(master_key)
    return aesgcm.decrypt(nonce, ciphertext, None).decode()
```

### Key Management

- `ENCRYPTION_KEY`: Master encryption key (required in production)
- Key rotation: Store key version in encrypted blob, support multiple keys

---

## Cloudflare Custom Domains

### SSL for SaaS Setup

**Prerequisites:**
1. Cloudflare zone with the base domain (e.g., `overseer.io`)
2. Fallback origin configured (e.g., `app.overseer.io`)
3. CNAME target configured (e.g., `custom.overseer.io`)

### Adding a Custom Domain

```python
async def add_custom_domain(tenant_id: str, domain: str) -> dict:
    """Add custom hostname via Cloudflare API."""
    response = await cf_client.post(
        f"/zones/{ZONE_ID}/custom_hostnames",
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
    return response.json()
```

### Domain Validation Flow

```
1. Tenant requests custom domain "requests.example.com"
2. We create custom hostname in Cloudflare
3. Cloudflare returns validation requirements:
   - TXT record: _cf-custom-hostname.requests.example.com → {validation_txt}
   - OR HTTP validation (if domain already points to us)
4. Tenant adds CNAME: requests.example.com → custom.overseer.io
5. Cloudflare validates and issues certificate
6. We update tenant.custom_domain_status = 'active'
```

### Request Routing

```python
async def get_tenant_from_request(request: Request) -> Tenant:
    """Determine tenant from request host or path."""
    host = request.headers.get("host", "")

    # Check for custom domain
    tenant = await db.get_tenant_by_custom_domain(host)
    if tenant:
        return tenant

    # Check for slug in path (/t/{slug})
    if request.url.path.startswith("/t/"):
        slug = request.url.path.split("/")[2]
        return await db.get_tenant_by_slug(slug)

    # Check for subdomain (slug.overseer.io)
    if host.endswith(".overseer.io"):
        slug = host.split(".")[0]
        return await db.get_tenant_by_slug(slug)

    raise TenantNotFoundError()
```

---

## API Endpoints

### Authentication

| Method | Path | Description |
|--------|------|-------------|
| GET | `/auth/plex/login` | Initiate Plex OAuth flow |
| GET | `/auth/plex/callback` | Handle Plex OAuth callback |
| POST | `/auth/guest` | Guest login with access code |
| POST | `/auth/logout` | Clear session |
| GET | `/auth/me` | Get current user info |

### Tenant Management (Owner only)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/tenant` | Get tenant info and settings |
| PATCH | `/api/tenant` | Update tenant settings |
| POST | `/api/tenant/regenerate-codes` | Regenerate access/webhook codes |
| GET | `/api/tenant/setup` | Get setup status and webhook URL |
| POST | `/api/tenant/scan-library` | Trigger library rescan |

### Custom Domains (Owner only)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/tenant/domain` | Get current domain config |
| POST | `/api/tenant/domain` | Add custom domain |
| DELETE | `/api/tenant/domain` | Remove custom domain |
| GET | `/api/tenant/domain/status` | Check validation status |

### Existing Endpoints (Modified for Multi-Tenancy)

All existing endpoints now require tenant context:

| Method | Path | Changes |
|--------|------|---------|
| GET | `/api/search` | No change (TMDB search) |
| POST | `/api/request` | Add `tenant_id`, `requested_by` |
| DELETE | `/api/request` | Filter by `tenant_id` |
| GET | `/api/requests` | Filter by `tenant_id` |
| GET | `/api/library-status` | Filter by `tenant_id` |
| POST | `/webhook/plex/{tenant_id}` | Route to correct tenant |
| POST | `/sync/library/{tenant_id}` | Route to correct tenant |
| GET | `/rss/{tenant_id}/*` | Per-tenant feeds |

---

## Frontend Changes

### New Routes

```
/                       # Landing page (marketing, login options)
/auth/plex             # Plex OAuth redirect
/setup                 # Owner setup wizard (after first login)
/t/{slug}              # Tenant home (guest access)
/t/{slug}/requests     # Tenant requests page
/dashboard             # Owner dashboard
/dashboard/settings    # Owner settings (domain, codes, etc.)
```

### Components

1. **Landing Page**: Marketing + "Sign in with Plex" button
2. **Setup Wizard**: Guide owner through:
   - Server selection (if multiple)
   - Initial library scan
   - Webhook URL configuration
   - Guest access code setup
   - Custom domain (optional)
3. **Guest Login Modal**: Access code input + optional name
4. **Owner Dashboard**: Library stats, recent requests, settings

### State Management

```javascript
// New stores
export const tenant = writable(null);           // Current tenant context
export const user = writable(null);             // Current user (owner or guest)
export const isOwner = derived(user, $u => $u?.type === 'owner');
export const isGuest = derived(user, $u => $u?.type === 'guest');

// Modified stores
export const libraryStatus = writable(null);    // Now tenant-scoped
export const requests = writable([]);           // Now tenant-scoped
```

---

## Implementation Phases

### Phase 1: Database & Core Multi-Tenancy
- [ ] Add new tables (tenants, guests)
- [ ] Modify existing tables (add tenant_id)
- [ ] Implement tenant context middleware
- [ ] Update all queries to filter by tenant_id

### Phase 2: Plex OAuth
- [ ] Implement Plex OAuth flow
- [ ] Token encryption/decryption
- [ ] User info retrieval
- [ ] Session JWT generation

### Phase 3: Owner Setup & Library Scan
- [ ] Server discovery endpoint
- [ ] Library scan implementation
- [ ] Setup wizard frontend
- [ ] Webhook URL generation

### Phase 4: Guest Access
- [ ] Guest authentication endpoint
- [ ] Access code generation/validation
- [ ] Guest session management
- [ ] Frontend access code flow

### Phase 5: Tenant Routing
- [ ] Slug-based routing (/t/{slug})
- [ ] Subdomain routing ({slug}.overseer.io)
- [ ] Request/response tenant context

### Phase 6: Custom Domains
- [ ] Cloudflare API integration
- [ ] Domain validation flow
- [ ] Custom domain routing
- [ ] SSL certificate monitoring

### Phase 7: Migration & Polish
- [ ] Migration script for existing data
- [ ] Owner dashboard
- [ ] Settings management
- [ ] Documentation

---

## Environment Variables

### New Variables

```bash
# Encryption
ENCRYPTION_KEY=           # 32-byte key, base64 encoded

# Plex OAuth
PLEX_CLIENT_IDENTIFIER=   # Unique app identifier
PLEX_PRODUCT_NAME=        # "Overseer Lite"

# Cloudflare (optional, for custom domains)
CF_API_TOKEN=             # Cloudflare API token
CF_ZONE_ID=               # Zone ID for custom hostnames
CF_FALLBACK_ORIGIN=       # Fallback origin hostname
CF_CNAME_TARGET=          # CNAME target for customers

# Base URL
BASE_URL=                 # https://overseer.example.com
```

---

## Security Considerations

1. **Token Encryption**: Plex tokens encrypted at rest with AES-256-GCM
2. **Access Code Hashing**: Guest codes hashed with PBKDF2
3. **Tenant Isolation**: All queries filtered by tenant_id
4. **Rate Limiting**: Per-tenant and per-IP rate limits
5. **Webhook Secrets**: Per-tenant secrets for webhook authentication
6. **CORS**: Strict origin checking for custom domains
7. **Session Security**: Short-lived JWTs, secure cookie flags

---

## Open Questions

1. **Existing Authentication**: Keep the simple password auth for backward compatibility?
   - Recommendation: Support both modes - legacy single-tenant and new multi-tenant

2. **Free Tier Limits**: Should we limit the number of guests or requests per tenant?
   - Recommendation: Start unlimited, add limits if needed

3. **Plex Server Selection**: What if owner has multiple Plex servers?
   - Recommendation: Let them choose during setup, allow changing later

4. **Guest Identity**: Should guests be able to create accounts vs anonymous?
   - Recommendation: Optional name during access, no persistent accounts

5. **Data Portability**: Allow owners to export/delete their data?
   - Recommendation: Yes, implement GDPR-compliant data export/deletion
