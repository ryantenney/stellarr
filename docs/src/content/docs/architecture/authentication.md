---
title: Authentication
description: PBKDF2 challenge-response authentication, HMAC session tokens, rate limiting, and endpoint protection.
---

Stellarr uses a challenge-response authentication flow based on PBKDF2 key derivation and HMAC-SHA256 signed session tokens. This design avoids sending passwords over the network while keeping the implementation simple.

## Authentication Flow

```
┌─────────┐                              ┌─────────┐
│ Browser │                              │ Server  │
└────┬────┘                              └────┬────┘
     │                                        │
     │  1. GET /api/auth/params               │
     │───────────────────────────────────────▶│
     │  { iterations: 100000 }                │
     │◀───────────────────────────────────────│
     │                                        │
     │  2. Derive key (client-side)           │
     │  key = PBKDF2(password, origin, 100K)  │
     │                                        │
     │  3. Compute hash                       │
     │  hash = SHA256(key + ":" + timestamp)  │
     │                                        │
     │  4. POST /api/auth/verify              │
     │  { origin, timestamp, hash, name }     │
     │───────────────────────────────────────▶│
     │                                        │  5. Verify hash
     │                                        │  6. Check rate limit
     │                                        │  7. Generate token
     │  { valid: true, token: "..." }         │
     │◀───────────────────────────────────────│
     │                                        │
     │  8. Subsequent requests                │
     │  Authorization: Bearer <token>         │
     │───────────────────────────────────────▶│
     │                                        │  9. Verify token signature
```

### Step by Step

1. **Fetch params** — Browser requests PBKDF2 iteration count from the server
2. **Key derivation** — Browser computes `PBKDF2(password, origin, 100,000 iterations)` using the page's origin as the salt
3. **Challenge hash** — Browser computes `SHA256(derived_key + ":" + current_timestamp)`
4. **Send verification** — Browser sends the hash, timestamp, origin, and display name
5. **Server verification** — Server derives the same key using its stored password and verifies the hash
6. **Rate limit check** — Server checks if the IP has exceeded failed attempt limits
7. **Token generation** — Server creates `HMAC-SHA256(APP_SECRET_KEY, timestamp.base64(name))` and returns it
8. **Token usage** — Browser stores the token in `localStorage` and sends it with every request
9. **Token validation** — Server verifies the HMAC signature and checks the timestamp is within 30 days

## Session Token Format

```
{timestamp}.{base64_name}.{hmac_signature}
```

| Field | Description |
|-------|-------------|
| `timestamp` | Unix timestamp when the token was issued |
| `base64_name` | Base64-encoded display name |
| `hmac_signature` | HMAC-SHA256 of `timestamp.base64_name` using `APP_SECRET_KEY` |

Tokens expire after **30 days** from the `timestamp` value.

### Legacy Format

An older token format is also supported for backwards compatibility:

```
{timestamp}.{hmac_signature}
```

This format lacks the display name and uses `HMAC-SHA256(APP_SECRET_KEY, timestamp)`.

## Security Properties

| Property | Mechanism |
|----------|-----------|
| Password never transmitted | PBKDF2 derivation happens client-side |
| Brute-force resistance | 100,000 PBKDF2 iterations per attempt |
| Replay protection | Timestamp must be within 5 minutes of server time |
| Token forgery prevention | HMAC-SHA256 requires knowledge of `APP_SECRET_KEY` |
| Session expiry | 30-day TTL built into token timestamp |
| Origin binding | PBKDF2 salt includes page origin |

## Rate Limiting

### Lambda-Level Rate Limiting (Default)

Failed authentication attempts are tracked in DynamoDB:

| Setting | Default |
|---------|---------|
| Max attempts | 5 per window |
| Window | 15 minutes |
| Storage | DynamoDB with TTL |
| Scope | Per source IP |

Rate limit entries use the partition key pattern `RATELIMIT#<ip>` with a TTL attribute, so DynamoDB automatically cleans them up after the window expires.

### WAF Rate Limiting (Optional)

AWS WAF can be enabled for additional protection:

| Rule | Limit | Scope |
|------|-------|-------|
| Auth endpoint | 100 requests / 5 min | `/api/auth/*` per IP |
| Overall | 100 requests / 5 min | All paths per IP |
| AWS Managed Rules | N/A | Common exploits, bad inputs, IP reputation |

WAF adds ~$8/month but provides defense-in-depth with managed rule sets.

## Feed and Webhook Protection

Endpoints outside the `/api/` path use token-based query parameter authentication:

### Feed Token (`FEED_TOKEN`)

Protects import list endpoints:

```
/list/radarr?token=YOUR_FEED_TOKEN
/list/sonarr?token=YOUR_FEED_TOKEN
```

If `FEED_TOKEN` is not set, these endpoints are publicly accessible.

### Plex Webhook Token (`PLEX_WEBHOOK_TOKEN`)

Protects webhook and library sync endpoints:

```
/webhook/plex?token=YOUR_PLEX_WEBHOOK_TOKEN
/sync/library?media_type=movie&token=YOUR_PLEX_WEBHOOK_TOKEN
```

If `PLEX_WEBHOOK_TOKEN` is not set, these endpoints are disabled (return 403).

## Public Endpoints

These endpoints require no authentication:

| Endpoint | Purpose |
|----------|---------|
| `/api/auth/params` | PBKDF2 iteration count |
| `/api/auth/verify` | Password verification |
| `/api/health` | Health check |
| `/trending-*.json` | Trending data (served from S3) |
