#!/usr/bin/env python3
"""
Quick test script for lightweight AWS clients.
Run with AWS credentials configured (env vars or ~/.aws/credentials).

Usage:
    python test_aws_clients.py <table-name> [secret-arn]

Examples:
    python test_aws_clients.py stellarr-requests
    python test_aws_clients.py stellarr-requests arn:aws:secretsmanager:us-east-1:123:secret:my-secret
"""
import sys
import os

# Ensure we're using the local modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_dynamodb(table_name: str):
    """Test DynamoDB operations."""
    print("\n=== Testing DynamoDB ===")

    from dynamodb_lite import DynamoDBClient, ConditionalCheckFailedException

    client = DynamoDBClient(table_name)
    print(f"✓ Client created for table: {table_name}")

    # Test scan
    print("\nTesting scan...")
    items = client.scan()
    print(f"✓ Scan returned {len(items)} items")
    if items:
        print(f"  Sample item keys: {list(items[0].keys())}")

    # Test put_item with a test record
    test_key = {'media_type': 'TEST', 'tmdb_id': 99999999}
    test_item = {
        **test_key,
        'title': 'Test Item - Delete Me',
        'created_at': '2024-01-01T00:00:00Z',
    }

    print("\nTesting put_item...")
    try:
        client.put_item(test_item)
        print(f"✓ Put item succeeded")
    except Exception as e:
        print(f"✗ Put item failed: {e}")
        return False

    # Test get_item
    print("\nTesting get_item...")
    retrieved = client.get_item(test_key)
    if retrieved and retrieved.get('title') == test_item['title']:
        print(f"✓ Get item succeeded: {retrieved.get('title')}")
    else:
        print(f"✗ Get item failed or returned wrong data: {retrieved}")
        return False

    # Test query
    print("\nTesting query...")
    query_results = client.query(
        key_condition_expression='media_type = :mt',
        expression_attribute_values={':mt': 'TEST'}
    )
    if any(item.get('tmdb_id') == 99999999 for item in query_results):
        print(f"✓ Query succeeded, found test item in {len(query_results)} results")
    else:
        print(f"✗ Query didn't find test item")
        return False

    # Test update_item
    print("\nTesting update_item...")
    updated = client.update_item(
        key=test_key,
        update_expression='SET title = :t',
        expression_attribute_values={':t': 'Updated Test Item'},
        return_values='ALL_NEW'
    )
    if updated and updated.get('title') == 'Updated Test Item':
        print(f"✓ Update item succeeded: {updated.get('title')}")
    else:
        print(f"✗ Update item failed: {updated}")
        return False

    # Test delete_item
    print("\nTesting delete_item...")
    client.delete_item(test_key)

    # Verify deletion
    deleted_check = client.get_item(test_key)
    if deleted_check is None:
        print(f"✓ Delete item succeeded (item gone)")
    else:
        print(f"✗ Delete item failed (item still exists)")
        return False

    # Test conditional put (should fail on second attempt)
    print("\nTesting conditional put_item...")
    client.put_item(test_item)
    try:
        client.put_item(test_item, condition_expression='attribute_not_exists(media_type)')
        print(f"✗ Conditional put should have failed")
        client.delete_item(test_key)  # Cleanup
        return False
    except ConditionalCheckFailedException:
        print(f"✓ Conditional put correctly raised ConditionalCheckFailedException")
        client.delete_item(test_key)  # Cleanup

    print("\n✓ All DynamoDB tests passed!")
    return True


def test_secrets_manager(secret_arn: str):
    """Test Secrets Manager."""
    print("\n=== Testing Secrets Manager ===")

    from aws_sigv4 import get_secret

    print(f"Fetching secret: {secret_arn[:50]}...")
    try:
        secret = get_secret(secret_arn)
        print(f"✓ Secret retrieved successfully")
        print(f"  Keys in secret: {list(secret.keys())}")
        return True
    except Exception as e:
        print(f"✗ Failed to get secret: {e}")
        return False


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    table_name = sys.argv[1]
    secret_arn = sys.argv[2] if len(sys.argv) > 2 else None

    # Check for AWS credentials
    if not os.environ.get('AWS_ACCESS_KEY_ID') and not os.path.exists(os.path.expanduser('~/.aws/credentials')):
        print("Warning: No AWS credentials found in environment or ~/.aws/credentials")
        print("Make sure you have credentials configured.\n")

    region = os.environ.get('AWS_REGION_NAME', os.environ.get('AWS_DEFAULT_REGION', 'us-east-1'))
    print(f"Using region: {region}")

    success = True

    # Test DynamoDB
    if not test_dynamodb(table_name):
        success = False

    # Test Secrets Manager if ARN provided
    if secret_arn:
        if not test_secrets_manager(secret_arn):
            success = False
    else:
        print("\n=== Skipping Secrets Manager (no ARN provided) ===")

    print("\n" + "=" * 40)
    if success:
        print("All tests passed! Ready to deploy.")
    else:
        print("Some tests failed. Check the output above.")

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
