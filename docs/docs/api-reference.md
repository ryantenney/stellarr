---
sidebar_position: 6
title: API Reference
---

# API Reference

All API endpoints are prefixed with `/api` unless otherwise noted.

## Authentication

### Get Auth Parameters

```http
GET /api/auth/params
```

Returns PBKDF2 parameters for client-side password hashing.

**Response:**

```json
{
  "iterations": 100000
}
```

### Verify Password

```http
POST /api/auth/verify
Content-Type: application/json

{
  "origin": "https://stellarr.example.com",
  "timestamp": 1703001234,
  "hash": "sha256-hash-here",
  "name": "John"
}
```

**Response:**

```json
{
  "valid": true,
  "token": "1703001234.abc123...",
  "name": "John"
}
```

The token should be included in subsequent requests as:

```http
Authorization: Bearer 1703001234.abc123...
```

## Search

### Search TMDB

```http
POST /api/search
Authorization: Bearer <token>
Content-Type: application/json

{
  "query": "breaking bad",
  "media_type": "tv",  // optional: "movie", "tv", or null for all
  "page": 1
}
```

**Response:**

```json
{
  "results": [
    {
      "id": 1396,
      "title": "Breaking Bad",
      "year": 2008,
      "overview": "A high school chemistry teacher...",
      "poster_path": "/ggFHVNu6YYI5L9pCfOacjizRGt.jpg",
      "media_type": "tv",
      "vote_average": 8.9,
      "requested": false,
      "in_library": true,
      "number_of_seasons": 5
    }
  ],
  "page": 1,
  "total_pages": 1,
  "total_results": 1
}
```

### Get Trending

```http
GET /trending-{type}-{locale}.json
```

Trending data is served as static JSON files from S3 via CloudFront. No authentication required.

**URL Parameters:**

| Parameter | Values | Example |
|-----------|--------|---------|
| `type` | `all`, `movie`, `tv` | `all` |
| `locale` | `en`, `es`, `fr`, `de` | `en` |

**Example:** `/trending-all-en.json`, `/trending-movie-fr.json`

**Response:** Same format as search results.

:::note
Files are cached for 1 hour and refreshed daily by the cache warmer Lambda. The frontend hydrates results with current request status client-side.
:::

## Requests

### Add Request

```http
POST /api/request
Authorization: Bearer <token>
Content-Type: application/json

{
  "tmdb_id": 1396,
  "media_type": "tv",
  "requested_by": "John"  // optional
}
```

**Response:**

```json
{
  "success": true,
  "message": "Added Breaking Bad to requests"
}
```

### List Requests

```http
GET /api/requests?media_type=tv
Authorization: Bearer <token>
```

**Query Parameters:**

| Parameter | Values | Default |
|-----------|--------|---------|
| `media_type` | `movie`, `tv`, or omit for all | all |

**Response:**

```json
{
  "requests": [
    {
      "tmdb_id": 1396,
      "media_type": "tv",
      "title": "Breaking Bad",
      "year": 2008,
      "overview": "...",
      "poster_path": "/ggFHVNu6YYI5L9pCfOacjizRGt.jpg",
      "imdb_id": "tt0903747",
      "tvdb_id": 81189,
      "status": "pending",
      "requested_at": "2024-01-15T10:30:00Z",
      "requested_by": "John"
    }
  ]
}
```

### Remove Request

```http
DELETE /api/request/{media_type}/{tmdb_id}
Authorization: Bearer <token>
```

**Response:**

```json
{
  "success": true,
  "message": "Request removed"
}
```

## Feeds

### Get Feed Info

```http
GET /api/feeds
Authorization: Bearer <token>
```

Returns URLs and setup instructions for all available feeds.

**Response:**

```json
{
  "token_required": true,
  "feeds": {
    "radarr": {
      "name": "Radarr (Movies)",
      "description": "StevenLu Custom JSON format",
      "url": "https://stellarr.example.com/list/radarr?token=...",
      "format": "json",
      "setup": "Settings -> Import Lists -> Custom Lists -> StevenLu Custom"
    },
    "sonarr": {
      "name": "Sonarr (TV Shows)",
      "description": "Custom List JSON format with TVDB IDs",
      "url": "https://stellarr.example.com/list/sonarr?token=...",
      "format": "json",
      "setup": "Settings -> Import Lists -> Add -> Custom Lists"
    }
    // ... more feeds
  }
}
```

## Import Lists

These endpoints don't require Bearer auth, but may require a feed token query parameter.

### Radarr JSON

```http
GET /list/radarr?token=<feed_token>
```

**Response:**

```json
[
  {"title": "Inception (2010)", "imdb_id": "tt1375666"},
  {"title": "The Dark Knight (2008)", "imdb_id": "tt0468569"}
]
```

### Sonarr JSON

```http
GET /list/sonarr?token=<feed_token>
```

**Response:**

```json
[
  {"tvdbId": "81189"},
  {"tvdbId": "153021"}
]
```

### RSS Feeds

```http
GET /rss/movies?token=<feed_token>
GET /rss/tv?token=<feed_token>
GET /rss/all?token=<feed_token>
```

Returns XML RSS feeds.

## Webhooks

### Plex Webhook

```http
POST /webhook/plex?token=<plex_webhook_token>
Content-Type: multipart/form-data

payload=<JSON string>
```

Plex sends this automatically when configured. The payload contains event type and metadata.

**Response:**

```json
{
  "status": "success",
  "title": "Inception",
  "media_type": "movie",
  "tmdb_id": 27205,
  "added_to_library": true,
  "matched_request": true
}
```

## Library Sync

### Bulk Sync

```http
POST /sync/library?media_type=movie&token=<plex_webhook_token>&clear=false
Content-Type: application/json

[
  {"tmdb_id": 27205, "tvdb_id": null, "title": "Inception"},
  {"tmdb_id": 155, "tvdb_id": null, "title": "The Dark Knight"}
]
```

**Query Parameters:**

| Parameter | Description |
|-----------|-------------|
| `media_type` | Required: `movie` or `tv` |
| `token` | Required: Plex webhook token |
| `clear` | Optional: Set `true` to clear existing items first |

**Response:**

```json
{
  "status": "success",
  "synced": 150,
  "marked_as_added": 3,
  "media_type": "movie"
}
```

## Health Check

```http
GET /api/health
```

**Response:**

```json
{
  "status": "healthy",
  "service": "stellarr"
}
```

No authentication required. Use for load balancer health checks.

## Error Responses

All errors follow this format:

```json
{
  "detail": "Error message here"
}
```

### Common Status Codes

| Code | Description |
|------|-------------|
| 400 | Bad request (invalid input) |
| 401 | Unauthorized (missing/invalid token) |
| 404 | Not found |
| 429 | Rate limited (too many failed auth attempts) |
| 500 | Internal server error |
