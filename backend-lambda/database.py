import boto3
import os
from datetime import datetime
from decimal import Decimal

print("DEBUG: database.py loading...", flush=True)

# Get table name from environment
TABLE_NAME = os.environ.get('DYNAMODB_TABLE', 'overseer-lite-requests')
AWS_REGION = os.environ.get('AWS_REGION_NAME', 'us-east-1')

# Create DynamoDB resource
dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
table = dynamodb.Table(TABLE_NAME)

print(f"DEBUG: DynamoDB table configured: {TABLE_NAME}", flush=True)


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
            'created_at': datetime.utcnow().isoformat(),
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
        table.put_item(
            Item=item,
            ConditionExpression='attribute_not_exists(media_type) AND attribute_not_exists(tmdb_id)'
        )
        return True
    except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
        # Item already exists
        return False
    except Exception as e:
        print(f"Error adding request: {e}", flush=True)
        return False


def remove_request(tmdb_id: int, media_type: str) -> bool:
    """Remove a media request from DynamoDB."""
    try:
        table.delete_item(
            Key={
                'media_type': media_type,
                'tmdb_id': tmdb_id
            }
        )
        return True
    except Exception as e:
        print(f"Error removing request: {e}", flush=True)
        return False


def get_all_requests(media_type: str | None = None) -> list[dict]:
    """Get all media requests, optionally filtered by type."""
    try:
        if media_type:
            # Query by partition key
            response = table.query(
                KeyConditionExpression='media_type = :mt',
                ExpressionAttributeValues={':mt': media_type}
            )
        else:
            # Scan entire table
            response = table.scan()

        items = response.get('Items', [])

        # Convert Decimal to int for JSON serialization
        for item in items:
            if 'tmdb_id' in item:
                item['tmdb_id'] = int(item['tmdb_id'])
            if 'year' in item and item['year'] is not None:
                item['year'] = int(item['year'])
            if 'tvdb_id' in item and item['tvdb_id'] is not None:
                item['tvdb_id'] = int(item['tvdb_id'])

        # Sort by created_at descending
        items.sort(key=lambda x: x.get('created_at', ''), reverse=True)

        return items
    except Exception as e:
        print(f"Error getting requests: {e}", flush=True)
        return []


def is_requested(tmdb_id: int, media_type: str) -> bool:
    """Check if a media item has already been requested."""
    try:
        response = table.get_item(
            Key={
                'media_type': media_type,
                'tmdb_id': tmdb_id
            }
        )
        return 'Item' in response
    except Exception as e:
        print(f"Error checking request: {e}", flush=True)
        return False
