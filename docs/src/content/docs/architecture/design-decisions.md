---
title: Design Decisions
description: Key architectural choices and their rationale, including the custom DynamoDB client, feed-based integration, and dual backend strategy.
---

This page documents the key architectural decisions behind Stellarr and the reasoning for each.

## Custom DynamoDB Client (No boto3)

**Decision:** Replace boto3 with a custom DynamoDB client built on httpx and AWS SigV4 signing.

**Why:** boto3 adds ~70 MB to the Lambda deployment package, dramatically increasing cold start times. The custom client (`dynamodb_lite.py` + `aws_sigv4.py`) provides:

- ~70 MB smaller Lambda package
- Faster cold starts (less code to load)
- Only the DynamoDB operations we actually use (GetItem, PutItem, DeleteItem, Query, Scan, Update, BatchWrite)
- Direct HTTP calls with proper error handling

**Trade-off:** We maintain our own DynamoDB client code instead of using the well-tested boto3 library. This is acceptable because DynamoDB's HTTP API is simple and well-documented, and our usage is limited to basic CRUD operations.

## Feed-Based Integration (No Open Ports)

**Decision:** Expose requests as import list endpoints (JSON) that Sonarr/Radarr poll, rather than pushing directly to their APIs.

**Why:**

- **No inbound connections needed** — Stellarr doesn't need to know where Sonarr/Radarr are running
- **No API keys stored** — Stellarr never stores Sonarr/Radarr credentials
- **Works across networks** — Sonarr/Radarr can pull from a public URL; no VPN or tunneling needed
- **Simple failure model** — If Stellarr is down, Sonarr/Radarr just retry on next sync cycle
- **Multiple consumers** — The same feed can serve multiple Sonarr/Radarr instances

**Trade-off:** There's a polling delay (default 6 hours in \*arr apps) between request creation and download start. Users can manually trigger a sync for immediate action.

## Lazy Imports for Cold Start Optimization

**Decision:** Heavy modules (TMDB client, Plex parser, TVDB client) are imported lazily — only when the specific endpoint that needs them is called.

**Why:** Lambda cold starts load all imported modules. Most requests only need a subset of functionality:

- Search only needs the TMDB client
- Webhooks only need the Plex parser
- Episode matching only needs the TVDB client

By deferring imports until they're needed, the initial cold start is faster for all endpoints, and rarely-used code paths (like TVDB lookups) don't penalize common operations.

## Lambda Layers for Heavy Dependencies

**Decision:** Package `cryptography` (used for Web Push VAPID signing) in a separate Lambda Layer.

**Why:** The `cryptography` library includes compiled C extensions that are large (~30 MB). By isolating it in a layer:

- The main Lambda package stays small and deploys faster
- The layer is only updated when `cryptography` version changes (rare)
- The `cryptography` module is only loaded when push notifications are sent (webhook handler)

## Static SPA (No Server-Side Rendering)

**Decision:** Build the frontend as a fully static SPA using SvelteKit's static adapter.

**Why:**

- **No Node.js server needed** — Deploy as plain HTML/JS/CSS to S3
- **CDN-friendly** — Every page is a static file that CloudFront can cache
- **Simple deployment** — Just `aws s3 sync`
- **Low cost** — S3 + CloudFront is essentially free for this traffic level
- **Client-side hydration** — Trending data is public, user-specific status is merged client-side

**Trade-off:** No server-side rendering means slower initial page load and no SEO benefits. This is acceptable for an authenticated application.

## Dual Backend Strategy

**Decision:** Maintain two separate backend implementations — one for Docker (SQLite) and one for Lambda (DynamoDB).

**Why:**

- **Docker** is simpler for self-hosting: single container, SQLite file, no cloud dependencies
- **Lambda** offers near-zero operational overhead and sub-dollar monthly costs
- The FastAPI endpoint logic is identical; only the database layer differs
- Shared modules (`tmdb.py`, `plex.py`, `tvdb.py`) are duplicated but kept in sync

**Trade-off:** Code duplication between backends means API changes must be applied twice. The shared modules mitigate this by containing most of the business logic.

## Single DynamoDB Table Design

**Decision:** Store all data (requests, library items, rate limit entries, push subscriptions) in a single DynamoDB table.

**Schema:**

| Partition Key (`media_type`) | Sort Key (`tmdb_id`) | Purpose |
|-----|------|---------|
| `movie` | TMDB ID | Movie requests and library items |
| `tv` | TMDB ID | TV show requests and library items |
| `RATELIMIT#<ip>` | `0` | Auth rate limit entries (TTL auto-cleanup) |
| `PUSH#<endpoint>` | `0` | Push notification subscriptions |
| `PLEX_GUID#<guid>` | `0` | Plex GUID → TMDB ID cache |

**Why:**

- Simpler infrastructure (one table to manage)
- Cheaper (single on-demand table)
- All access patterns are partition-key lookups or scans within a partition
- Rate limit entries use DynamoDB TTL for automatic cleanup

## Challenge-Response Authentication

**Decision:** Use PBKDF2 key derivation on the client with HMAC-SHA256 signed session tokens, rather than sending passwords directly.

**Flow:**

1. Client derives key: `PBKDF2(password, origin, 100,000 iterations)`
2. Client computes hash: `SHA256(key + ":" + timestamp)`
3. Server verifies hash against its own derivation
4. Server returns: `HMAC-SHA256(APP_SECRET_KEY, timestamp + "." + name)`

**Why:**

- **Password never sent** — Only a derived hash crosses the network
- **Replay protection** — Timestamp must be within 5 minutes
- **Brute-force resistant** — PBKDF2 with 100K iterations is computationally expensive
- **Simple token format** — No JWT library dependency; just `timestamp.name.signature`
- **30-day sessions** — Long-lived tokens reduce re-authentication friction

## Trending Cache Architecture

**Decision:** Serve trending data as static JSON files from S3, refreshed daily by a separate Lambda, rather than proxying TMDB trending requests through the API Lambda.

**Why:**

- **Fast** — Pure CDN serving, no Lambda invocation for trending
- **Cheap** — S3 GET requests are essentially free
- **Private** — Trending data is public; user-specific status (requested, in library) is merged client-side after authentication
- **Reliable** — If TMDB is slow or down, cached trending still works
- **Separate concerns** — Cache warmer Lambda is small (128 MB) and runs independently

See [Trending Cache](/docs/architecture/trending-cache/) for detailed architecture.

## ARM64 (Graviton2) Lambda

**Decision:** Run Lambda functions on ARM64 architecture.

**Why:**

- **20% cheaper** than x86 per millisecond of compute
- **Better performance** for most workloads
- **Same code** — Python runs identically on ARM64
- Requires ARM64-compatible compiled dependencies (handled by Docker build in `deploy.sh`)
