#!/usr/bin/env python3
"""
Generate VAPID key pair for Web Push notifications.
Used by Terraform external data source.

Outputs JSON: {"private_key": "base64...", "public_key": "base64..."}
"""
import base64
import json
import sys

try:
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.backends import default_backend
except ImportError:
    print(json.dumps({"error": "cryptography library not installed"}), file=sys.stderr)
    sys.exit(1)


def b64encode(data: bytes) -> str:
    """URL-safe base64 encode without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')


def generate_vapid_keys() -> tuple[str, str]:
    """Generate a valid VAPID key pair. Returns (private_key, public_key)."""
    # Generate a proper EC P-256 private key
    private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())

    # Export private key as raw 32-byte scalar
    private_bytes = private_key.private_numbers().private_value.to_bytes(32, 'big')

    # Export public key as uncompressed point (65 bytes: 0x04 + x + y)
    public_key = private_key.public_key()
    public_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint
    )

    return b64encode(private_bytes), b64encode(public_bytes)


if __name__ == "__main__":
    # Read input from Terraform (required by external data source, but we ignore it)
    input_json = sys.stdin.read()

    private_key, public_key = generate_vapid_keys()
    print(json.dumps({"private_key": private_key, "public_key": public_key}))
