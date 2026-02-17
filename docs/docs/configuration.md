---
sidebar_position: 3
title: Configuration
---

# Configuration

Stellarr is configured via environment variables. For Docker deployments, set these in your `.env` file. For AWS, they're stored in Secrets Manager and set via Terraform.

## Required Variables

| Variable | Description |
|----------|-------------|
| `APP_SECRET_KEY` | Secret key for signing session tokens. Generate with `openssl rand -hex 32` |
| `PRESHARED_PASSWORD` | Password users enter to access the application |
| `TMDB_API_KEY` | API key from [The Movie Database](https://www.themoviedb.org/settings/api) |

## Optional Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `FEED_TOKEN` | Token required to access RSS/list endpoints. If set, append `?token=XXX` to feed URLs | None (public) |
| `PLEX_WEBHOOK_TOKEN` | Token required for Plex webhook and library sync endpoints | None (disabled) |
| `PLEX_SERVER_NAME` | Only process webhooks from this Plex server name | None (all servers) |
| `TVDB_API_KEY` | TVDB API key for episode-to-show resolution | None |
| `DATABASE_PATH` | Path to SQLite database (Docker only) | `./data/stellarr.db` |

## Authentication

### Session Tokens

Stellarr uses HMAC-SHA256 signed session tokens with a 30-day expiry. The authentication flow:

1. User enters password in the browser
2. Browser derives a key using PBKDF2 (100,000 iterations)
3. Browser sends a challenge-response hash to the server
4. Server verifies and returns a signed session token
5. Token is stored in localStorage and sent with each request

This design ensures:
- Passwords are never sent in plaintext
- Brute-force attacks are computationally expensive
- Tokens can't be forged without the `APP_SECRET_KEY`

### Rate Limiting (AWS Only)

Failed authentication attempts are rate-limited:
- 5 attempts per 15 minutes per IP
- Stored in DynamoDB with TTL

## Feed Protection

If `FEED_TOKEN` is set, all RSS and list endpoints require authentication:

```
# Without token (public)
https://stellarr.example.com/list/radarr

# With token (protected)
https://stellarr.example.com/list/radarr?token=your-feed-token
```

This prevents unauthorized access to your request lists while still allowing Sonarr/Radarr to import them.

## Plex Integration

### Webhook Token

Set `PLEX_WEBHOOK_TOKEN` to enable the Plex webhook endpoint:

```
https://stellarr.example.com/webhook/plex?token=your-webhook-token
```

The same token is used for the library sync endpoint.

### Server Filtering

If you have multiple Plex servers, set `PLEX_SERVER_NAME` to only process webhooks from a specific server:

```bash
PLEX_SERVER_NAME="My Plex Server"
```

The server name must match exactly as shown in Plex.

## TVDB Integration

Set `TVDB_API_KEY` to enable episode-to-show resolution. This is useful when Plex sends webhooks for individual episodes - Stellarr can look up which show the episode belongs to and mark the correct request as added.

Get an API key at [thetvdb.com](https://thetvdb.com/api-information).

## AWS-Specific Configuration

For AWS deployments, additional configuration is set in `terraform.tfvars`:

```hcl
# Lambda configuration
lambda_memory_size = 256    # MB
lambda_timeout     = 30     # seconds

# Rate limiting
rate_limit_enabled       = true
rate_limit_max_attempts  = 5
rate_limit_window        = 900  # seconds

# WAF (optional, adds ~$8/month)
enable_waf = false
```

## Security Best Practices

1. **Use strong secrets** - Generate `APP_SECRET_KEY` with `openssl rand -hex 32`
2. **Protect your feeds** - Set `FEED_TOKEN` if your instance is publicly accessible
3. **Use HTTPS** - Always deploy with TLS (automatic with Caddy or CloudFront)
4. **Limit Plex servers** - Set `PLEX_SERVER_NAME` if you have multiple servers
5. **Rotate secrets periodically** - Update tokens if compromised

## Environment File Example

```bash
# .env file for Docker deployment

# Required
APP_SECRET_KEY=a1b2c3d4e5f6...  # 64 hex chars
PRESHARED_PASSWORD=mypassword
TMDB_API_KEY=abc123...

# Optional - Feed protection
FEED_TOKEN=feed-secret-token

# Optional - Plex integration
PLEX_WEBHOOK_TOKEN=plex-webhook-token
PLEX_SERVER_NAME=My Plex Server

# Optional - TVDB for episode resolution
TVDB_API_KEY=tvdb-api-key

# Production only
DOMAIN=stellarr.example.com
```
