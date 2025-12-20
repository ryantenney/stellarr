"""
Database operations using lightweight DynamoDB client (no boto3).
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from dynamodb_lite import DynamoDBClient, ConditionalCheckFailedException

print("DEBUG: database.py loading (boto3-free)...", flush=True)

# Get table name from environment
TABLE_NAME = os.environ.get('DYNAMODB_TABLE', 'overseer-lite-requests')
AWS_REGION = os.environ.get('AWS_REGION_NAME', 'us-east-1')

# Create lightweight DynamoDB client
_client = None


def _get_client() -> DynamoDBClient:
    """Lazy-init the DynamoDB client."""
    global _client
    if _client is None:
        _client = DynamoDBClient(TABLE_NAME, AWS_REGION)
        print(f"DEBUG: DynamoDB client initialized for {TABLE_NAME}", flush=True)
    return _client


def init_db():
    """Initialize database - no-op for DynamoDB (table created by Terraform)."""
    print(f"DEBUG: DynamoDB init - table {TABLE_NAME} ready", flush=True)


def add_request(
    tmdb_id: int,
    media_type: str,
    title: str,
    year: int | None,
    overview: str | None,
    poster_path: str | None,
    imdb_id: str | None = None,
    tvdb_id: int | None = None,
    requested_by: str | None = None
) -> bool:
    """Add a media request to DynamoDB."""
    try:
        item = {
            'media_type': media_type,
            'tmdb_id': tmdb_id,
            'title': title,
            'created_at': datetime.now(timezone.utc).isoformat(),
        }

        # Add optional fields if present
        if year is not None:
            item['year'] = year
        if overview:
            item['overview'] = overview
        if poster_path:
            item['poster_path'] = poster_path
        if imdb_id:
            item['imdb_id'] = imdb_id
        if tvdb_id is not None:
            item['tvdb_id'] = tvdb_id
        if requested_by:
            item['requested_by'] = requested_by

        # Use condition to prevent overwriting existing items
        _get_client().put_item(
            item,
            condition_expression='attribute_not_exists(media_type) AND attribute_not_exists(tmdb_id)'
        )
        return True
    except ConditionalCheckFailedException:
        # Item already exists
        return False
    except Exception as e:
        print(f"Error adding request: {e}", flush=True)
        return False


def remove_request(tmdb_id: int, media_type: str) -> bool:
    """Remove a media request from DynamoDB."""
    try:
        _get_client().delete_item({
            'media_type': media_type,
            'tmdb_id': tmdb_id
        })
        return True
    except Exception as e:
        print(f"Error removing request: {e}", flush=True)
        return False


def get_all_requests(media_type: str | None = None) -> list[dict]:
    """Get all media requests, optionally filtered by type."""
    try:
        client = _get_client()

        if media_type:
            # Query by partition key
            items = client.query(
                key_condition_expression='media_type = :mt',
                expression_attribute_values={':mt': media_type}
            )
        else:
            # Scan entire table (filter out rate limit entries)
            all_items = client.scan()
            # Filter out rate limit entries
            items = [item for item in all_items if not item.get('media_type', '').startswith('RATELIMIT#')]

        # Sort by created_at descending
        items.sort(key=lambda x: x.get('created_at', ''), reverse=True)

        return items
    except Exception as e:
        print(f"Error getting requests: {e}", flush=True)
        return []


def is_requested(tmdb_id: int, media_type: str) -> bool:
    """Check if a media item has already been requested."""
    try:
        item = _get_client().get_item({
            'media_type': media_type,
            'tmdb_id': tmdb_id
        })
        return item is not None
    except Exception as e:
        print(f"Error checking request: {e}", flush=True)
        return False


def mark_as_added(tmdb_id: int, media_type: str) -> bool:
    """Mark a request as added to Plex library."""
    try:
        result = _get_client().update_item(
            key={
                'media_type': media_type,
                'tmdb_id': tmdb_id
            },
            update_expression='SET added_at = :now',
            condition_expression='attribute_exists(media_type) AND attribute_not_exists(added_at)',
            expression_attribute_values={
                ':now': datetime.now(timezone.utc).isoformat()
            },
            return_values='UPDATED_NEW'
        )
        return result is not None
    except ConditionalCheckFailedException:
        # Either item doesn't exist or already marked as added
        return False
    except Exception as e:
        print(f"Error marking request as added: {e}", flush=True)
        return False


def find_by_tvdb_id(tvdb_id: int, media_type: str) -> dict | None:
    """Find a request by TVDB ID."""
    try:
        # Query by media_type and filter by tvdb_id
        items = _get_client().query(
            key_condition_expression='media_type = :mt',
            filter_expression='tvdb_id = :tvdb',
            expression_attribute_values={
                ':mt': media_type,
                ':tvdb': tvdb_id
            }
        )
        return items[0] if items else None
    except Exception as e:
        print(f"Error finding by tvdb_id: {e}", flush=True)
        return None


def find_by_plex_guid(plex_guid: str) -> dict | None:
    """Find a request by Plex GUID."""
    try:
        # Scan with filter (plex_guid is not a key)
        all_items = _get_client().scan(
            filter_expression='plex_guid = :pg',
            expression_attribute_values={':pg': plex_guid}
        )
        return all_items[0] if all_items else None
    except Exception as e:
        print(f"Error finding by plex_guid: {e}", flush=True)
        return None


def update_plex_guid(tmdb_id: int, media_type: str, plex_guid: str) -> bool:
    """Cache a Plex GUID on a request for future matching."""
    try:
        _get_client().update_item(
            key={
                'media_type': media_type,
                'tmdb_id': tmdb_id
            },
            update_expression='SET plex_guid = :pg',
            expression_attribute_values={
                ':pg': plex_guid
            }
        )
        return True
    except Exception as e:
        print(f"Error updating plex_guid: {e}", flush=True)
        return False


# --- Rate Limiting ---

def check_rate_limit(ip: str, max_attempts: int, window_seconds: int) -> tuple[bool, int]:
    """
    Check if an IP is rate limited.
    Returns (allowed, attempts_remaining).
    """
    try:
        item = _get_client().get_item({
            'media_type': f'RATELIMIT#{ip}',
            'tmdb_id': 0  # Dummy sort key
        })

        if not item:
            return True, max_attempts

        failed_attempts = int(item.get('failed_attempts', 0))
        first_attempt = int(item.get('first_attempt', 0))
        current_time = int(datetime.now(timezone.utc).timestamp())

        # Check if window has expired
        if current_time - first_attempt > window_seconds:
            # Window expired, allow and reset will happen on next failure
            return True, max_attempts

        # Check if over limit
        if failed_attempts >= max_attempts:
            return False, 0

        return True, max_attempts - failed_attempts

    except Exception as e:
        print(f"Error checking rate limit: {e}", flush=True)
        # Fail open - allow request if we can't check
        return True, max_attempts


def record_failed_attempt(ip: str, window_seconds: int) -> int:
    """
    Record a failed auth attempt. Returns new failure count.
    Uses atomic increment to handle concurrent requests.
    """
    try:
        current_time = int(datetime.now(timezone.utc).timestamp())
        ttl = current_time + window_seconds + 60  # Extra minute buffer

        # Try to increment existing counter
        result = _get_client().update_item(
            key={
                'media_type': f'RATELIMIT#{ip}',
                'tmdb_id': 0
            },
            update_expression='SET failed_attempts = if_not_exists(failed_attempts, :zero) + :inc, '
                            'first_attempt = if_not_exists(first_attempt, :now), '
                            'last_attempt = :now, '
                            'ttl = :ttl',
            expression_attribute_values={
                ':zero': 0,
                ':inc': 1,
                ':now': current_time,
                ':ttl': ttl
            },
            return_values='ALL_NEW'
        )

        if not result:
            return 0

        new_count = int(result.get('failed_attempts', 0))
        first_attempt = int(result.get('first_attempt', 0))

        # If the window has passed, reset the counter
        if current_time - first_attempt > window_seconds:
            _get_client().put_item({
                'media_type': f'RATELIMIT#{ip}',
                'tmdb_id': 0,
                'failed_attempts': 1,
                'first_attempt': current_time,
                'last_attempt': current_time,
                'ttl': ttl
            })
            return 1

        return new_count

    except Exception as e:
        print(f"Error recording failed attempt: {e}", flush=True)
        return 0


def clear_rate_limit(ip: str) -> bool:
    """Clear rate limit on successful auth."""
    try:
        _get_client().delete_item({
            'media_type': f'RATELIMIT#{ip}',
            'tmdb_id': 0
        })
        return True
    except Exception as e:
        print(f"Error clearing rate limit: {e}", flush=True)
        return False
