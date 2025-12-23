"""
Lightweight Web Push implementation for Lambda.
No external dependencies - uses only Python stdlib + cryptography (already in Lambda).

Usage:
    from webpush import send_push, generate_vapid_keys

    # Generate VAPID keys (do once, store in env vars)
    private_key, public_key = generate_vapid_keys()

    # Send a push notification
    send_push(
        subscription={
            'endpoint': 'https://fcm.googleapis.com/fcm/send/...',
            'keys': {
                'p256dh': 'base64-encoded-key',
                'auth': 'base64-encoded-auth'
            }
        },
        data={'title': 'Hello', 'body': 'World'},
        vapid_private_key=private_key,
        vapid_claims={'sub': 'mailto:admin@example.com'}
    )
"""
import base64
import json
import os
import time
import urllib.request
import urllib.error
from typing import Any
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.backends import default_backend


def _b64encode(data: bytes) -> str:
    """URL-safe base64 encode without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')


def _b64decode(data: str) -> bytes:
    """Base64 decode with padding restoration. Handles both URL-safe and standard base64."""
    # Convert standard base64 to URL-safe if needed
    data = data.replace('+', '-').replace('/', '_')
    # Restore padding
    padding = 4 - (len(data) % 4)
    if padding != 4:
        data += '=' * padding
    return base64.urlsafe_b64decode(data)


def generate_vapid_keys() -> tuple[str, str]:
    """
    Generate a new VAPID key pair.
    Returns (private_key_base64, public_key_base64).

    Store the private key securely (env var).
    The public key goes in your frontend for subscription.
    """
    private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())

    # Export private key as raw bytes (32 bytes for P-256)
    private_bytes = private_key.private_numbers().private_value.to_bytes(32, 'big')

    # Export public key as uncompressed point (65 bytes: 0x04 + x + y)
    public_key = private_key.public_key()
    public_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint
    )

    return _b64encode(private_bytes), _b64encode(public_bytes)


def _create_vapid_jwt(endpoint: str, vapid_private_key: str, vapid_claims: dict) -> tuple[str, str]:
    """
    Create VAPID JWT token and public key for Authorization header.
    Returns (jwt_token, public_key_base64).
    """
    from urllib.parse import urlparse

    # Extract audience from endpoint
    parsed = urlparse(endpoint)
    audience = f"{parsed.scheme}://{parsed.netloc}"

    # Build JWT header and payload
    header = {'typ': 'JWT', 'alg': 'ES256'}
    payload = {
        'aud': audience,
        'exp': int(time.time()) + 12 * 3600,  # 12 hour expiry
        **vapid_claims
    }

    # Encode header and payload
    header_b64 = _b64encode(json.dumps(header, separators=(',', ':')).encode())
    payload_b64 = _b64encode(json.dumps(payload, separators=(',', ':')).encode())
    signing_input = f"{header_b64}.{payload_b64}".encode()

    # Load private key
    private_bytes = _b64decode(vapid_private_key)
    private_key = ec.derive_private_key(
        int.from_bytes(private_bytes, 'big'),
        ec.SECP256R1(),
        default_backend()
    )

    # Sign with ECDSA
    signature = private_key.sign(signing_input, ec.ECDSA(hashes.SHA256()))

    # Convert DER signature to raw r||s format (64 bytes)
    # DER format: 0x30 len 0x02 r_len r 0x02 s_len s
    from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
    r, s = decode_dss_signature(signature)
    sig_bytes = r.to_bytes(32, 'big') + s.to_bytes(32, 'big')

    jwt_token = f"{header_b64}.{payload_b64}.{_b64encode(sig_bytes)}"

    # Get public key
    public_key = private_key.public_key()
    public_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint
    )

    return jwt_token, _b64encode(public_bytes)


def _encrypt_payload(
    data: bytes,
    subscription_public_key: str,
    subscription_auth: str
) -> tuple[bytes, bytes, bytes]:
    """
    Encrypt payload using Web Push encryption (aes128gcm).
    Returns (encrypted_payload, salt, server_public_key).
    """
    # Decode subscription keys
    user_public_bytes = _b64decode(subscription_public_key)
    auth_secret = _b64decode(subscription_auth)

    # Generate ephemeral server key pair
    server_private = ec.generate_private_key(ec.SECP256R1(), default_backend())
    server_public = server_private.public_key()
    server_public_bytes = server_public.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint
    )

    # Load user's public key
    user_public = ec.EllipticCurvePublicKey.from_encoded_point(
        ec.SECP256R1(), user_public_bytes
    )

    # ECDH shared secret
    shared_secret = server_private.exchange(ec.ECDH(), user_public)

    # Generate salt
    salt = os.urandom(16)

    # Derive IKM using HKDF with auth_secret
    # info = "WebPush: info\0" + user_public + server_public
    info_prefix = b"WebPush: info\x00"
    ikm_info = info_prefix + user_public_bytes + server_public_bytes

    ikm = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=auth_secret,
        info=ikm_info,
        backend=default_backend()
    ).derive(shared_secret)

    # Derive content encryption key and nonce
    cek_info = b"Content-Encoding: aes128gcm\x00"
    cek = HKDF(
        algorithm=hashes.SHA256(),
        length=16,
        salt=salt,
        info=cek_info,
        backend=default_backend()
    ).derive(ikm)

    nonce_info = b"Content-Encoding: nonce\x00"
    nonce = HKDF(
        algorithm=hashes.SHA256(),
        length=12,
        salt=salt,
        info=nonce_info,
        backend=default_backend()
    ).derive(ikm)

    # Pad the plaintext (add 0x02 delimiter + optional padding)
    # Minimum padding: just the delimiter
    padded_data = data + b'\x02'

    # Encrypt with AES-GCM
    aesgcm = AESGCM(cek)
    ciphertext = aesgcm.encrypt(nonce, padded_data, None)

    # Build aes128gcm payload:
    # salt (16) + rs (4, big-endian record size) + idlen (1) + keyid (server_public) + ciphertext
    rs = (4096).to_bytes(4, 'big')  # Record size
    idlen = len(server_public_bytes).to_bytes(1, 'big')

    encrypted_payload = salt + rs + idlen + server_public_bytes + ciphertext

    return encrypted_payload, salt, server_public_bytes


def send_push(
    subscription: dict,
    data: dict | str,
    vapid_private_key: str,
    vapid_claims: dict,
    ttl: int = 86400
) -> bool:
    """
    Send a Web Push notification.

    Args:
        subscription: Push subscription object with 'endpoint' and 'keys' (p256dh, auth)
        data: Notification payload (dict will be JSON-encoded)
        vapid_private_key: Base64-encoded VAPID private key
        vapid_claims: VAPID claims dict (must include 'sub' with mailto: or https: URL)
        ttl: Time-to-live in seconds (default 24 hours)

    Returns:
        True if successful, False if subscription is invalid/expired.

    Raises:
        Exception for other errors.
    """
    endpoint = subscription['endpoint']
    keys = subscription.get('keys', {})

    # Encode payload as JSON if dict
    if isinstance(data, dict):
        payload_bytes = json.dumps(data).encode('utf-8')
    else:
        payload_bytes = data.encode('utf-8')

    # Encrypt payload
    encrypted_payload, _, _ = _encrypt_payload(
        payload_bytes,
        keys['p256dh'],
        keys['auth']
    )

    # Create VAPID authorization
    jwt_token, vapid_public = _create_vapid_jwt(endpoint, vapid_private_key, vapid_claims)

    # Build request
    headers = {
        'Authorization': f'vapid t={jwt_token}, k={vapid_public}',
        'Content-Type': 'application/octet-stream',
        'Content-Encoding': 'aes128gcm',
        'TTL': str(ttl),
    }

    request = urllib.request.Request(
        endpoint,
        data=encrypted_payload,
        headers=headers,
        method='POST'
    )

    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return True
    except urllib.error.HTTPError as e:
        if e.code in (404, 410):
            # Subscription no longer valid
            return False
        raise Exception(f"Push failed: {e.code} {e.reason}")
    except urllib.error.URLError as e:
        raise Exception(f"Push failed: {e.reason}")


def get_vapid_public_key(vapid_private_key: str) -> str:
    """
    Derive the public key from a VAPID private key.
    Use this to get the applicationServerKey for frontend subscription.
    """
    private_bytes = _b64decode(vapid_private_key)
    private_key = ec.derive_private_key(
        int.from_bytes(private_bytes, 'big'),
        ec.SECP256R1(),
        default_backend()
    )
    public_key = private_key.public_key()
    public_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint
    )
    return _b64encode(public_bytes)
