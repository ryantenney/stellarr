---
sidebar_position: 4
title: Plex Integration
---

# Plex Integration

Stellarr integrates with Plex in two ways:

1. **Webhooks** - Automatically mark requests as "Added" when Plex downloads new media
2. **Library Sync** - Bulk import your existing library to show "In Library" badges

## Webhooks

### Setup

1. Open Plex Web → Settings → Webhooks
2. Click **Add Webhook**
3. Enter your webhook URL:
   ```
   https://stellarr.example.com/webhook/plex?token=YOUR_PLEX_WEBHOOK_TOKEN
   ```
4. Click **Save Changes**

### How It Works

When Plex adds new media to your library, it sends a `library.new` webhook. Stellarr:

1. Parses the webhook payload to extract TMDB/TVDB IDs
2. Adds the item to the library table (enables "In Library" badges)
3. Finds and marks any matching requests as "Added"

### Supported Events

| Event | Action |
|-------|--------|
| `library.new` | Marks requests as added, updates library |
| All others | Ignored |

### ID Resolution

Stellarr uses multiple strategies to match webhook events to requests:

1. **TMDB ID** - Direct match (most reliable)
2. **TVDB ID** - For TV shows
3. **Plex GUID** - Cached from previous matches
4. **Episode TVDB ID** - Resolved to show via TVDB API (requires `TVDB_API_KEY`)

### Server Filtering

If you have multiple Plex servers, set `PLEX_SERVER_NAME` to only process webhooks from a specific server:

```bash
PLEX_SERVER_NAME="My Plex Server"
```

### Monitoring Webhooks

Webhooks are logged with the `WEBHOOK:` prefix. In AWS CloudWatch:

```
fields @timestamp, @message
| filter @message like /WEBHOOK:/
| sort @timestamp desc
| limit 100
```

Example log output:

```
WEBHOOK: Received event='library.new' server='MyPlex' type='movie' title='Inception'
WEBHOOK: Parsed media - title='Inception' type='movie' tmdb=27205 tvdb=None
WEBHOOK: Added to library - tmdb=27205 type='movie'
WEBHOOK: Matched request by TMDB ID 27205
WEBHOOK: Complete - {'status': 'success', 'title': 'Inception', ...}
```

## Library Sync

For items added before the webhook was configured, use the library sync script.

### Prerequisites

```bash
cd scripts
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Running the Sync

```bash
python plex-sync.py \
  --plex-url http://localhost:32400 \
  --plex-token YOUR_PLEX_TOKEN \
  --stellarr-url https://stellarr.example.com \
  --sync-token YOUR_PLEX_WEBHOOK_TOKEN
```

Or use environment variables:

```bash
export PLEX_URL=http://localhost:32400
export PLEX_TOKEN=your-plex-token
export STELLARR_URL=https://stellarr.example.com
export STELLARR_SYNC_TOKEN=your-sync-token

python plex-sync.py
```

### What Gets Synced

The script:

1. Connects to your Plex server
2. Scans all movie and TV show libraries
3. Extracts TMDB and TVDB IDs from each item
4. Sends them to Stellarr's sync endpoint
5. Marks any matching requests as "Added"

### Getting Your Plex Token

1. Open Plex Web and sign in
2. Open any media item
3. Click the "..." menu → "Get Info"
4. Click "View XML"
5. Find `X-Plex-Token=` in the URL

Or use the [Plex Token Guide](https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/).

### Automating Sync

Run the sync periodically with cron:

```bash
# Sync every night at 3am
0 3 * * * /path/to/scripts/venv/bin/python /path/to/scripts/plex-sync.py
```

## "In Library" Badge

Once library sync is complete, search results and trending items show an "In Library" badge for media already in Plex:

- **Green badge** on poster - "In Library"
- **Grey button** - "In Library" (can't request again)

This prevents duplicate requests and helps users see what's already available.

## Testing

### Test Webhook (curl)

```bash
# Movie
curl -X POST "https://stellarr.example.com/webhook/plex?token=YOUR_TOKEN" \
  -F 'payload={
    "event": "library.new",
    "Server": {"title": "My Plex Server"},
    "Metadata": {
      "type": "movie",
      "title": "Inception",
      "year": 2010,
      "Guid": [
        {"id": "tmdb://27205"},
        {"id": "imdb://tt1375666"}
      ]
    }
  }'

# TV Show
curl -X POST "https://stellarr.example.com/webhook/plex?token=YOUR_TOKEN" \
  -F 'payload={
    "event": "library.new",
    "Server": {"title": "My Plex Server"},
    "Metadata": {
      "type": "show",
      "title": "Breaking Bad",
      "year": 2008,
      "Guid": [
        {"id": "tmdb://1396"},
        {"id": "tvdb://81189"}
      ]
    }
  }'
```

### Expected Response

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

## Troubleshooting

### Webhook Not Firing

1. Verify the webhook URL in Plex settings
2. Check that the token matches `PLEX_WEBHOOK_TOKEN`
3. Ensure Plex can reach your Stellarr instance

### "Server name mismatch"

Set `PLEX_SERVER_NAME` to match your server exactly, or remove it to accept all servers.

### Request Not Marked as Added

Check the logs for matching attempts. Common issues:

- TMDB ID not in Plex metadata (older scanner)
- Item requested before it was in library (sync needed)
- Media type mismatch (movie vs. TV show)

### Episode Webhooks Not Working

For episode-level webhooks, you need `TVDB_API_KEY` to resolve episode IDs to show IDs.
