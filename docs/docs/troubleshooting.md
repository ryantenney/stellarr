---
sidebar_position: 7
title: Troubleshooting
---

# Troubleshooting

Common issues and solutions for Overseer Lite.

## Authentication Issues

### "Invalid credentials" on login

1. **Check password** - Ensure you're entering the correct `PRESHARED_PASSWORD`
2. **Check clock sync** - The authentication uses timestamps. Ensure your device's clock is accurate
3. **Clear browser cache** - Try clearing localStorage: `localStorage.clear()` in browser console
4. **Check rate limiting** - After 5 failed attempts, you're blocked for 15 minutes

### Session expires too quickly

Sessions last 30 days. If you're being logged out sooner:

1. Check that `APP_SECRET_KEY` hasn't changed (invalidates all sessions)
2. Verify your browser isn't clearing localStorage

### Rate limited (429 error)

Wait 15 minutes, or if you have server access:

```bash
# Docker - check database
sqlite3 data/overseer.db "DELETE FROM rate_limits;"

# AWS - items auto-expire via DynamoDB TTL
```

## Search Issues

### No results found

1. **Check TMDB API key** - Verify `TMDB_API_KEY` is valid
2. **Try different search terms** - TMDB search can be picky about exact titles
3. **Check network** - Ensure the server can reach api.themoviedb.org

### Missing posters

TMDB may not have posters for all content. The UI shows a placeholder for missing images.

### Slow search/trending

For AWS deployments:
- First request after idle period is slow (Lambda cold start)
- Subsequent requests should be fast
- Trending is cached for 1 hour via CloudFront

## Request Issues

### "Missing IMDB ID" or "Missing TVDB ID" warning

Some TMDB entries don't have external IDs. These items:
- Won't appear in Sonarr/Radarr feeds
- Show a warning in the UI

This is a TMDB data issue - nothing Overseer can fix.

### Request not appearing in Sonarr/Radarr

1. **Check external IDs** - Request must have IMDB (movies) or TVDB (TV) ID
2. **Force sync** - Go to System → Tasks → Import List Sync in your *arr app
3. **Check feed URL** - Test the feed URL directly in browser
4. **Verify token** - Ensure feed token matches

### Duplicate requests after item downloads

The Plex webhook should mark requests as "Added". If not:

1. Verify webhook is configured in Plex
2. Check `PLEX_WEBHOOK_TOKEN` matches
3. Check webhook logs for errors
4. Run library sync to catch up

## Plex Integration Issues

### Webhook not firing

1. **Check Plex settings** - Verify webhook URL in Settings → Webhooks
2. **Check network** - Plex must be able to reach your Overseer instance
3. **Check logs** - Look for `WEBHOOK:` entries in CloudWatch or Docker logs

### "Server name mismatch"

If you set `PLEX_SERVER_NAME`, it must match exactly. Check your server name in Plex → Settings → General.

### Request not marked as Added

Check webhook logs for matching attempts:

```
WEBHOOK: Received event='library.new' ...
WEBHOOK: Parsed media - title='...' tmdb=123 tvdb=456
WEBHOOK: Matched request by TMDB ID 123
```

If no match, possible issues:
- TMDB ID in Plex doesn't match request
- Media type mismatch (movie vs TV)
- Request was made with different ID

### Episode webhooks not matching

For individual episodes, you need `TVDB_API_KEY` to resolve episode IDs to show IDs.

## Feed Issues

### Empty feed

1. Check you have pending requests
2. Verify requests have required external IDs
3. Check feed token if protected

### "401 Unauthorized" on feed

Add the token parameter: `?token=YOUR_FEED_TOKEN`

### Feed returns old data

Feeds are not cached - they always return current data. If stale:
1. Check database has latest requests
2. Verify you're hitting the right server

## AWS-Specific Issues

### Lambda timeout

If requests timeout (30s default):
1. Check CloudWatch logs for errors
2. Increase `lambda_timeout` in Terraform
3. Check for network issues (Lambda → TMDB/TVDB APIs)

### Cold start latency

First request after idle is slow (2-5 seconds). Mitigations:
- Frontend preloads auth params to warm Lambda
- Provisioned concurrency (adds cost)

### DynamoDB errors

1. Check table exists and has correct schema
2. Verify Lambda has IAM permissions
3. Check CloudWatch for throttling (unlikely with on-demand)

### CloudFront caching issues

After deploying frontend changes:

```bash
aws cloudfront create-invalidation \
  --distribution-id YOUR_DIST_ID \
  --paths "/*"
```

## Docker-Specific Issues

### Port already in use

```bash
sudo lsof -i :80
sudo lsof -i :443
```

Stop conflicting services or change ports in docker-compose.yml.

### Permission denied on data directory

```bash
sudo chown -R 1000:1000 ./data
```

### Container won't start

Check logs:

```bash
docker compose logs backend
docker compose logs caddy
```

### HTTPS not working (production)

1. Verify `DOMAIN` is set correctly
2. Check DNS points to your server
3. Ensure ports 80 and 443 are open
4. Check Caddy logs for certificate errors

## Database Issues

### SQLite locked (Docker)

Only one process can write at a time. This shouldn't happen in normal operation. Restart the container:

```bash
docker compose restart backend
```

### DynamoDB provisioned capacity exceeded

Switch to on-demand billing or increase provisioned capacity.

## Getting Help

If you're still stuck:

1. **Check logs** - Most issues are visible in logs
2. **Search issues** - Check GitHub issues for similar problems
3. **Open an issue** - Include logs, configuration (redact secrets), and steps to reproduce

### Useful Log Commands

**Docker:**
```bash
docker compose logs -f backend
docker compose logs -f --tail=100 backend
```

**AWS CloudWatch:**
```
fields @timestamp, @message
| filter @message like /ERROR/
| sort @timestamp desc
| limit 100
```

**Webhook-specific:**
```
fields @timestamp, @message
| filter @message like /WEBHOOK:/
| sort @timestamp desc
```
