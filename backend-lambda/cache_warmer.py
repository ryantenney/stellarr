"""
Cache warmer Lambda - fetches trending data from TMDB and writes to S3.

Triggered by EventBridge daily.
CloudFront serves the S3 files directly, avoiding Lambda invocations.
"""
import json
import os

import httpx

from aws_sigv4 import get_secret, put_s3_object

# Supported locales - must match frontend/src/lib/i18n.js supportedLocales
SUPPORTED_LOCALES = ['en', 'es', 'fr', 'de']


def get_tmdb_api_key():
    """Load TMDB API key from Secrets Manager."""
    app_secret_arn = os.environ.get('APP_SECRET_ARN')
    if not app_secret_arn:
        raise ValueError("APP_SECRET_ARN not configured")

    secrets = get_secret(app_secret_arn)
    api_key = secrets.get('TMDB_API_KEY')
    if not api_key:
        raise ValueError("TMDB_API_KEY not found in secrets")
    return api_key


def fetch_trending(api_key: str, media_type: str, locale: str = 'en') -> dict:
    """Fetch trending data from TMDB API."""
    url = f"https://api.themoviedb.org/3/trending/{media_type}/week"
    params = {"api_key": api_key, "language": locale}

    with httpx.Client(timeout=30.0) as client:
        response = client.get(url, params=params)
        response.raise_for_status()
        return response.json()


def normalize_item(item: dict, default_media_type: str) -> dict:
    """
    Normalize TMDB item to frontend-expected format.
    Keeps only fields the frontend actually uses.
    """
    media_type = item.get('media_type', default_media_type)

    if media_type == 'tv':
        title = item.get('name')
        date_str = item.get('first_air_date', '')
    else:
        title = item.get('title')
        date_str = item.get('release_date', '')

    year = int(date_str[:4]) if date_str and len(date_str) >= 4 else None

    return {
        'id': item.get('id'),
        'title': title,
        'year': year,
        'overview': item.get('overview'),
        'poster_path': item.get('poster_path'),
        'media_type': media_type,
        'vote_average': item.get('vote_average'),
    }


def handler(event, context):
    """
    Fetch trending data from TMDB and write to S3.

    Creates JSON files for each media type and locale:
    - trending-all-en.json, trending-all-es.json, etc.
    - trending-movie-en.json, trending-movie-es.json, etc.
    - trending-tv-en.json, trending-tv-es.json, etc.
    """
    bucket = os.environ.get('TRENDING_S3_BUCKET')
    if not bucket:
        print("ERROR: TRENDING_S3_BUCKET not configured")
        return {"statusCode": 500, "body": "TRENDING_S3_BUCKET not configured"}

    region = os.environ.get('AWS_REGION_NAME', 'us-east-1')

    try:
        api_key = get_tmdb_api_key()
    except Exception as e:
        print(f"ERROR: Failed to get TMDB API key: {e}")
        return {"statusCode": 500, "body": str(e)}

    results = {}
    media_types = ['all', 'movie', 'tv']

    for locale in SUPPORTED_LOCALES:
        for media_type in media_types:
            result_key = f"{media_type}-{locale}"
            print(f"CACHE_WARMER: Fetching {media_type}/{locale} from TMDB...")

            try:
                data = fetch_trending(api_key, media_type, locale)

                # Normalize items to frontend format, keeping only needed fields
                default_type = 'movie' if media_type == 'movie' else 'tv' if media_type == 'tv' else None
                normalized = [normalize_item(item, default_type) for item in data.get('results', [])]

                # Write to S3
                key = f"trending-{media_type}-{locale}.json"
                json_data = json.dumps({'results': normalized}, separators=(',', ':')).encode('utf-8')

                put_s3_object(
                    bucket=bucket,
                    key=key,
                    data=json_data,
                    region=region,
                    content_type='application/json',
                    cache_control='public, max-age=3600',
                )

                results[result_key] = {
                    'status': 'success',
                    'items': len(normalized),
                    'bytes': len(json_data)
                }
                print(f"CACHE_WARMER: {media_type}/{locale} - {len(normalized)} items, {len(json_data)} bytes")

            except httpx.HTTPStatusError as e:
                print(f"CACHE_WARMER: {media_type}/{locale} - TMDB error: {e.response.status_code}")
                results[result_key] = {
                    'status': 'error',
                    'error': f"TMDB HTTP {e.response.status_code}"
                }
            except Exception as e:
                print(f"CACHE_WARMER: {media_type}/{locale} - Error: {e}")
                results[result_key] = {
                    'status': 'error',
                    'error': str(e)
                }

    # Check if all succeeded
    all_success = all(r.get('status') == 'success' for r in results.values())

    summary = {
        'success': all_success,
        'results': results
    }

    print(f"CACHE_WARMER: Complete - {'SUCCESS' if all_success else 'PARTIAL FAILURE'}")

    return {
        'statusCode': 200 if all_success else 500,
        'body': json.dumps(summary)
    }
