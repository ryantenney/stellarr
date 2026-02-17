"""
Database interface (Protocol) for Overseer Lite.

All cloud providers must implement a database module with these functions.
Functions are synchronous - async adapters can be added at the handler level.
"""
from __future__ import annotations

from typing import Protocol


class DatabaseProvider(Protocol):
    """Protocol defining the database interface for all providers."""

    def init_db(self) -> None:
        """Initialize the database (create tables, etc.)."""
        ...

    def add_request(
        self,
        tmdb_id: int,
        media_type: str,
        title: str,
        year: int | None,
        overview: str | None,
        poster_path: str | None,
        imdb_id: str | None = None,
        tvdb_id: int | None = None,
        requested_by: str | None = None,
    ) -> bool:
        """Add a media request. Returns True if added, False if already exists."""
        ...

    def remove_request(self, tmdb_id: int, media_type: str) -> bool:
        """Remove a media request. Returns True if removed."""
        ...

    def get_all_requests(self, media_type: str | None = None) -> list[dict]:
        """Get all media requests, optionally filtered by type."""
        ...

    def is_requested(self, tmdb_id: int, media_type: str) -> bool:
        """Check if a media item has been requested."""
        ...

    def mark_as_added(self, tmdb_id: int, media_type: str) -> dict | None:
        """Mark a request as added to library. Returns the updated request or None."""
        ...

    def find_by_tvdb_id(self, tvdb_id: int, media_type: str) -> dict | None:
        """Find a request by TVDB ID."""
        ...

    def find_by_plex_guid(self, plex_guid: str) -> dict | None:
        """Find a request by Plex GUID."""
        ...

    def update_plex_guid(self, tmdb_id: int, media_type: str, plex_guid: str) -> bool:
        """Cache a Plex GUID on a request."""
        ...

    def check_rate_limit(self, ip: str, max_attempts: int, window_seconds: int) -> tuple[bool, int]:
        """Check if an IP is rate limited. Returns (allowed, attempts_remaining)."""
        ...

    def record_failed_attempt(self, ip: str, window_seconds: int) -> int:
        """Record a failed auth attempt. Returns new failure count."""
        ...

    def clear_rate_limit(self, ip: str) -> bool:
        """Clear rate limit on successful auth."""
        ...

    def sync_library(self, items: list[dict], media_type: str, clear_first: bool = False) -> int:
        """Sync library items. Returns count of items synced."""
        ...

    def is_in_library(self, tmdb_id: int, media_type: str) -> bool:
        """Check if an item exists in the library."""
        ...

    def get_library_ids(self, media_type: str | None = None) -> set[tuple[int, str]]:
        """Get all (tmdb_id, media_type) pairs in library."""
        ...

    def get_plex_guid_cache(self, plex_guid: str) -> dict | None:
        """Look up cached show-level IDs for a Plex GUID."""
        ...

    def set_plex_guid_cache(self, plex_guid: str, tmdb_id: int | None, tvdb_id: int | None) -> bool:
        """Cache show-level IDs for a Plex GUID."""
        ...

    def get_trending_key(self) -> str | None:
        """Get the trending API key from config."""
        ...

    def set_trending_key(self, key: str) -> bool:
        """Set or update the trending API key."""
        ...

    def get_or_create_trending_key(self) -> str:
        """Get existing trending key or create a new one."""
        ...

    def find_by_title(self, title: str, media_type: str, year: int | None = None) -> dict | None:
        """Find a pending request by title (normalized match)."""
        ...

    def get_all_library_tmdb_ids(self) -> dict[str, list[int]]:
        """Get all TMDB IDs in library, grouped by media type."""
        ...

    def save_push_subscription(self, user_name: str, subscription: dict) -> bool:
        """Save or update a push subscription for a user."""
        ...

    def get_push_subscription(self, user_name: str) -> dict | None:
        """Get push subscription for a user."""
        ...

    def delete_push_subscription(self, user_name: str) -> bool:
        """Delete push subscription for a user."""
        ...
