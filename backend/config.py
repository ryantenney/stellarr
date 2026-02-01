from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    # Core settings
    app_secret_key: str = "change-me-in-production"
    tmdb_api_key: str = ""
    tmdb_base_url: str = "https://api.themoviedb.org/3"
    database_path: str = "/app/data/overseer.db"

    # Legacy single-tenant mode settings
    # When multi_tenant_mode is False, these are used for backward compatibility
    multi_tenant_mode: bool = False
    preshared_password: str = "changeme"
    feed_token: str = ""  # Optional token for RSS/list endpoint protection
    plex_webhook_token: str = ""  # Token for Plex webhook authentication
    plex_server_name: str = ""  # Optional Plex server name for validation

    # Multi-tenant mode settings
    encryption_key: str = ""  # Required for multi-tenant: 32-byte key, base64 encoded
    base_url: str = ""  # Public base URL (e.g., https://overseer.example.com)
    base_domain: str = ""  # Base domain for subdomains (e.g., overseer.io)

    # Plex OAuth settings
    plex_client_identifier: str = "overseer-lite"
    plex_product_name: str = "Overseer Lite"

    # Cloudflare SSL for SaaS settings (optional, for custom domains)
    cf_api_token: str = ""
    cf_zone_id: str = ""
    cf_fallback_origin: str = ""  # e.g., app.overseer.io
    cf_cname_target: str = ""  # e.g., custom.overseer.io

    # TVDB for episode lookups
    tvdb_api_key: str = ""  # TVDB API key for episode-to-show lookups

    class Config:
        env_file = ".env"

    @property
    def is_multi_tenant(self) -> bool:
        """Check if running in multi-tenant mode."""
        return self.multi_tenant_mode and bool(self.encryption_key)


@lru_cache()
def get_settings() -> Settings:
    return Settings()
