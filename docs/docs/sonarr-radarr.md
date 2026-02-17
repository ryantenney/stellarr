---
sidebar_position: 5
title: Sonarr & Radarr
---

# Sonarr & Radarr Setup

Stellarr exposes your requests as import lists compatible with Sonarr and Radarr. When a user requests media, it automatically appears in your \*arr application.

## Available Endpoints

### Radarr (Movies)

| Endpoint | Format | Description |
|----------|--------|-------------|
| `/list/radarr` | JSON | **Recommended** - StevenLu Custom format |
| `/rss/movies` | RSS | Alternative RSS format |

### Sonarr (TV Shows)

| Endpoint | Format | Description |
|----------|--------|-------------|
| `/list/sonarr` | JSON | **Recommended** - Custom List format |
| `/rss/tv` | RSS | Alternative RSS format |

### Combined

| Endpoint | Format | Description |
|----------|--------|-------------|
| `/rss/all` | RSS | All requests (movies + TV) |

## Feed Token

If `FEED_TOKEN` is configured, append it to your URLs:

```
https://stellarr.example.com/list/radarr?token=YOUR_FEED_TOKEN
```

## Radarr Setup

### Using StevenLu Custom (Recommended)

1. Go to **Settings** → **Import Lists**
2. Click **+** to add a new list
3. Select **Custom Lists** → **StevenLu Custom**
4. Configure:
   - **Name**: Stellarr
   - **URL**: `https://stellarr.example.com/list/radarr?token=YOUR_TOKEN`
   - **Import Automatically**: Yes
   - **Quality Profile**: Your preferred profile
   - **Root Folder**: Your movies folder
   - **Monitor**: Movie Only (or your preference)
   - **Search on Add**: Yes (recommended)
5. Click **Test** then **Save**

### List Format

The `/list/radarr` endpoint returns:

```json
[
  {"title": "Inception (2010)", "imdb_id": "tt1375666"},
  {"title": "The Dark Knight (2008)", "imdb_id": "tt0468569"}
]
```

Radarr uses the IMDB ID to identify movies.

## Sonarr Setup

### Using Custom Lists (Recommended)

1. Go to **Settings** → **Import Lists**
2. Click **+** to add a new list
3. Select **Custom Lists**
4. Configure:
   - **Name**: Stellarr
   - **URL**: `https://stellarr.example.com/list/sonarr?token=YOUR_TOKEN`
   - **Import Automatically**: Yes
   - **Quality Profile**: Your preferred profile
   - **Root Folder**: Your TV folder
   - **Monitor**: All Episodes (or your preference)
   - **Series Type**: Standard
   - **Search on Add**: Yes (recommended)
5. Click **Test** then **Save**

### List Format

The `/list/sonarr` endpoint returns:

```json
[
  {"tvdbId": "81189"},
  {"tvdbId": "153021"}
]
```

Sonarr uses the TVDB ID to identify shows.

## RSS Feeds (Alternative)

If you prefer RSS feeds or need compatibility with other tools:

### Radarr RSS

1. Settings → Import Lists → **+** → RSS List
2. URL: `https://stellarr.example.com/rss/movies?token=YOUR_TOKEN`

### Sonarr RSS

RSS support in Sonarr is limited. Use the JSON Custom Lists endpoint instead.

## Sync Interval

By default, Sonarr and Radarr sync import lists every 6 hours. To sync immediately:

1. Go to **System** → **Tasks**
2. Click the refresh icon next to "Import List Sync"

Or trigger via API:

```bash
# Radarr
curl -X POST "http://localhost:7878/api/v3/command" \
  -H "X-Api-Key: YOUR_RADARR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name": "ImportListSync"}'

# Sonarr
curl -X POST "http://localhost:8989/api/v3/command" \
  -H "X-Api-Key: YOUR_SONARR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name": "ImportListSync"}'
```

## Missing ID Warnings

Some TMDB entries don't have corresponding IMDB or TVDB IDs. These items:

- Show a **warning icon** in Stellarr's UI
- **Won't appear** in the respective feed

The UI shows which IDs are missing so users know their request may not be imported automatically.

## Troubleshooting

### "Test Failed" in Sonarr/Radarr

1. Check the URL is accessible from your \*arr instance
2. Verify the feed token is correct
3. Ensure HTTPS certificate is valid (or use HTTP for local testing)

### Items Not Importing

1. Check the request has the required external ID (IMDB for movies, TVDB for TV)
2. Verify the item isn't already in your library
3. Check Sonarr/Radarr logs for import errors

### Duplicate Imports

If items keep being re-added:
- Ensure "Search on Add" is enabled to immediately download
- Check that Plex webhooks are working to mark items as added
- Run a library sync to update Stellarr's library cache

### Feed Returns Empty

1. Check you have pending requests in Stellarr
2. Verify requests have valid external IDs
3. Try accessing the feed URL directly in a browser

## Example Workflow

1. User searches for "Breaking Bad" in Stellarr
2. User clicks "Request"
3. Request is saved with TVDB ID 81189
4. Sonarr syncs import lists (every 6 hours or manually)
5. Sonarr sees new entry, adds show, starts searching
6. Sonarr downloads episodes
7. Plex scans library, sends webhook
8. Stellarr marks request as "Added"
9. User sees green "Added" badge in Stellarr
