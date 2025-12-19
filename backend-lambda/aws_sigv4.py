"""
AWS Signature Version 4 signing implementation.
Replaces boto3/botocore for lightweight Lambda deployments.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from urllib.parse import quote

import httpx


def _sign(key: bytes, msg: str) -> bytes:
    """HMAC-SHA256 sign a message."""
    return hmac.new(key, msg.encode('utf-8'), hashlib.sha256).digest()


def _get_signature_key(secret_key: str, date_stamp: str, region: str, service: str) -> bytes:
    """Derive the signing key for AWS SigV4."""
    k_date = _sign(f"AWS4{secret_key}".encode('utf-8'), date_stamp)
    k_region = _sign(k_date, region)
    k_service = _sign(k_region, service)
    k_signing = _sign(k_service, "aws4_request")
    return k_signing


def _sha256_hash(payload: str) -> str:
    """SHA256 hash of payload."""
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def sign_request(
    method: str,
    url: str,
    headers: dict,
    payload: str,
    service: str,
    region: str,
    access_key: str | None = None,
    secret_key: str | None = None,
    session_token: str | None = None,
) -> dict:
    """
    Sign an AWS API request using SigV4.

    Returns headers with Authorization and other required headers added.
    Credentials default to environment variables if not provided.
    """
    # Get credentials from environment if not provided
    access_key = access_key or os.environ.get('AWS_ACCESS_KEY_ID')
    secret_key = secret_key or os.environ.get('AWS_SECRET_ACCESS_KEY')
    session_token = session_token or os.environ.get('AWS_SESSION_TOKEN')

    if not access_key or not secret_key:
        raise ValueError("AWS credentials not found")

    # Parse URL to get host and path
    # URL format: https://dynamodb.us-east-1.amazonaws.com/
    url_parts = url.replace('https://', '').replace('http://', '').split('/', 1)
    host = url_parts[0]
    canonical_uri = '/' + (url_parts[1] if len(url_parts) > 1 else '')

    # Create timestamps
    t = datetime.now(timezone.utc)
    amz_date = t.strftime('%Y%m%dT%H%M%SZ')
    date_stamp = t.strftime('%Y%m%d')

    # Create canonical headers
    headers = dict(headers)  # Copy to avoid mutation
    headers['host'] = host
    headers['x-amz-date'] = amz_date

    if session_token:
        headers['x-amz-security-token'] = session_token

    # Sort headers for canonical request
    signed_headers_list = sorted(headers.keys())
    signed_headers = ';'.join(signed_headers_list)

    canonical_headers = ''
    for key in signed_headers_list:
        canonical_headers += f"{key}:{headers[key]}\n"

    # Hash the payload
    payload_hash = _sha256_hash(payload)

    # Create canonical request
    canonical_request = '\n'.join([
        method,
        canonical_uri,
        '',  # No query string for DynamoDB
        canonical_headers,
        signed_headers,
        payload_hash
    ])

    # Create string to sign
    algorithm = 'AWS4-HMAC-SHA256'
    credential_scope = f"{date_stamp}/{region}/{service}/aws4_request"
    string_to_sign = '\n'.join([
        algorithm,
        amz_date,
        credential_scope,
        _sha256_hash(canonical_request)
    ])

    # Calculate signature
    signing_key = _get_signature_key(secret_key, date_stamp, region, service)
    signature = hmac.new(signing_key, string_to_sign.encode('utf-8'), hashlib.sha256).hexdigest()

    # Create authorization header
    authorization = (
        f"{algorithm} "
        f"Credential={access_key}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, "
        f"Signature={signature}"
    )

    # Return complete headers
    result = dict(headers)
    result['Authorization'] = authorization
    result['x-amz-content-sha256'] = payload_hash

    return result


def get_secret(secret_arn: str, region: str = None) -> dict:
    """
    Retrieve a secret from AWS Secrets Manager.
    Returns the parsed JSON secret value.
    """
    region = region or os.environ.get('AWS_REGION_NAME', 'us-east-1')
    endpoint = f"https://secretsmanager.{region}.amazonaws.com"

    payload = json.dumps({'SecretId': secret_arn})

    headers = {
        'Content-Type': 'application/x-amz-json-1.1',
        'X-Amz-Target': 'secretsmanager.GetSecretValue',
    }

    signed_headers = sign_request(
        method='POST',
        url=endpoint,
        headers=headers,
        payload=payload,
        service='secretsmanager',
        region=region,
    )

    with httpx.Client(timeout=30.0) as client:
        response = client.post(
            endpoint,
            headers=signed_headers,
            content=payload,
        )

    if response.status_code != 200:
        error = response.json()
        error_type = error.get('__type', 'Unknown').split('#')[-1]
        message = error.get('message', error.get('Message', 'Unknown error'))
        raise ValueError(f"Secrets Manager error: {error_type}: {message}")

    result = response.json()
    secret_string = result.get('SecretString')

    if secret_string:
        return json.loads(secret_string)
    else:
        raise ValueError("Secret does not contain a string value")
