"""
Cache warmer Lambda - hits the trending endpoint via CloudFront to keep cache warm.

Triggered by EventBridge on a 24-hour schedule.
"""
import os
import json
import urllib.request
import urllib.error

# Import database to get the trending key
import database


def handler(event, context):
    """
    Warm the CloudFront cache by fetching trending data.

    Makes requests to the CloudFront distribution (not Lambda directly)
    to ensure the cached response is populated.
    """
    base_url = os.environ.get('BASE_URL', '').rstrip('/')

    if not base_url:
        print("ERROR: BASE_URL not configured")
        return {"statusCode": 500, "body": "BASE_URL not configured"}

    # Get the trending key from DynamoDB
    trending_key = database.get_or_create_trending_key()

    results = {}
    media_types = ['all', 'movie', 'tv']

    for media_type in media_types:
        url = f"{base_url}/api/trending?media_type={media_type}&key={trending_key}"
        print(f"CACHE_WARMER: Fetching {media_type} from {base_url}/api/trending")

        try:
            req = urllib.request.Request(
                url,
                headers={
                    'User-Agent': 'OverseerLite-CacheWarmer/1.0',
                    'Accept': 'application/json'
                }
            )

            with urllib.request.urlopen(req, timeout=30) as response:
                status = response.status
                body = response.read().decode('utf-8')
                data = json.loads(body)
                item_count = len(data.get('results', []))
                results[media_type] = {
                    'status': status,
                    'items': item_count
                }
                print(f"CACHE_WARMER: {media_type} - {status} - {item_count} items")

        except urllib.error.HTTPError as e:
            print(f"CACHE_WARMER: {media_type} - HTTP {e.code}: {e.reason}")
            results[media_type] = {
                'status': e.code,
                'error': e.reason
            }
        except urllib.error.URLError as e:
            print(f"CACHE_WARMER: {media_type} - URL Error: {e.reason}")
            results[media_type] = {
                'status': 0,
                'error': str(e.reason)
            }
        except Exception as e:
            print(f"CACHE_WARMER: {media_type} - Error: {e}")
            results[media_type] = {
                'status': 0,
                'error': str(e)
            }

    # Check if all succeeded
    all_success = all(
        r.get('status') == 200
        for r in results.values()
    )

    summary = {
        'success': all_success,
        'results': results
    }

    print(f"CACHE_WARMER: Complete - {'SUCCESS' if all_success else 'PARTIAL FAILURE'}")

    return {
        'statusCode': 200 if all_success else 500,
        'body': json.dumps(summary)
    }
