"""
Encryption utilities for secure token storage.
Uses AES-256-GCM for authenticated encryption.
"""
from __future__ import annotations

import base64
import os
import secrets
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


# Nonce size for AES-GCM (96 bits recommended by NIST)
NONCE_SIZE = 12


def generate_encryption_key() -> str:
    """Generate a new 256-bit encryption key, base64 encoded."""
    key = secrets.token_bytes(32)
    return base64.urlsafe_b64encode(key).decode()


def _get_key_bytes(key: str) -> bytes:
    """Convert base64-encoded key string to bytes."""
    # Handle both url-safe and standard base64
    try:
        return base64.urlsafe_b64decode(key)
    except Exception:
        return base64.b64decode(key)


def encrypt(plaintext: str, key: str) -> str:
    """
    Encrypt a string using AES-256-GCM.

    Args:
        plaintext: The string to encrypt
        key: Base64-encoded 256-bit key

    Returns:
        Base64-encoded ciphertext (nonce || ciphertext || tag)
    """
    key_bytes = _get_key_bytes(key)
    if len(key_bytes) != 32:
        raise ValueError("Encryption key must be 32 bytes (256 bits)")

    aesgcm = AESGCM(key_bytes)
    nonce = os.urandom(NONCE_SIZE)

    # Encrypt and get ciphertext with auth tag appended
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode('utf-8'), None)

    # Combine nonce + ciphertext for storage
    combined = nonce + ciphertext
    return base64.urlsafe_b64encode(combined).decode()


def decrypt(encrypted: str, key: str) -> str:
    """
    Decrypt a string encrypted with AES-256-GCM.

    Args:
        encrypted: Base64-encoded ciphertext from encrypt()
        key: Base64-encoded 256-bit key (same key used for encryption)

    Returns:
        Decrypted plaintext string

    Raises:
        ValueError: If decryption fails (wrong key or tampered data)
    """
    key_bytes = _get_key_bytes(key)
    if len(key_bytes) != 32:
        raise ValueError("Encryption key must be 32 bytes (256 bits)")

    try:
        combined = base64.urlsafe_b64decode(encrypted)
    except Exception:
        # Try standard base64 as fallback
        combined = base64.b64decode(encrypted)

    if len(combined) < NONCE_SIZE + 16:  # At least nonce + auth tag
        raise ValueError("Invalid encrypted data")

    nonce = combined[:NONCE_SIZE]
    ciphertext = combined[NONCE_SIZE:]

    aesgcm = AESGCM(key_bytes)

    try:
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext.decode('utf-8')
    except Exception as e:
        raise ValueError(f"Decryption failed: {e}")


def hash_code(code: str, salt: Optional[bytes] = None) -> tuple[str, str]:
    """
    Hash an access code using PBKDF2-SHA256.

    Args:
        code: The access code to hash
        salt: Optional salt bytes. If None, generates a new random salt.

    Returns:
        Tuple of (hash, salt) both base64-encoded
    """
    if salt is None:
        salt = os.urandom(16)

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100_000,
    )

    hash_bytes = kdf.derive(code.encode('utf-8'))

    return (
        base64.urlsafe_b64encode(hash_bytes).decode(),
        base64.urlsafe_b64encode(salt).decode()
    )


def verify_code(code: str, stored_hash: str, stored_salt: str) -> bool:
    """
    Verify an access code against a stored hash.

    Args:
        code: The access code to verify
        stored_hash: Base64-encoded hash from hash_code()
        stored_salt: Base64-encoded salt from hash_code()

    Returns:
        True if the code matches, False otherwise
    """
    salt = base64.urlsafe_b64decode(stored_salt)

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100_000,
    )

    try:
        expected_hash = base64.urlsafe_b64decode(stored_hash)
        kdf.verify(code.encode('utf-8'), expected_hash)
        return True
    except Exception:
        return False


def generate_token(length: int = 32) -> str:
    """Generate a URL-safe random token."""
    return secrets.token_urlsafe(length)


def generate_slug(base: str) -> str:
    """
    Generate a URL-safe slug from a base string.

    Args:
        base: The base string (e.g., username or server name)

    Returns:
        URL-safe slug with random suffix for uniqueness
    """
    import re

    # Lowercase and replace spaces/special chars with hyphens
    slug = base.lower().strip()
    slug = re.sub(r'[^a-z0-9]+', '-', slug)
    slug = slug.strip('-')

    # Truncate if too long
    if len(slug) > 20:
        slug = slug[:20].rstrip('-')

    # Add random suffix for uniqueness
    suffix = secrets.token_hex(3)

    return f"{slug}-{suffix}" if slug else suffix
