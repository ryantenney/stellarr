"""
Base configuration model for Overseer Lite.
Provider-specific config loading is handled by each provider.
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App settings
    app_secret_key: str = ""
    preshared_password: str = ""
    tmdb_api_key: str = ""
    feed_token: str = ""
    plex_webhook_token: str = ""
    plex_server_name: str = ""
    tvdb_api_key: str = ""
    vapid_private_key: str = ""  # For web push notifications

    # TMDB
    tmdb_base_url: str = "https://api.themoviedb.org/3"

    class Config:
        env_file = ".env"
