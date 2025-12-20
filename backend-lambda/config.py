import os
import time
from functools import lru_cache
from pydantic_settings import BaseSettings

from aws_sigv4 import get_secret

print("DEBUG: config.py loading (boto3-free)...", flush=True)


class Settings(BaseSettings):
    # App settings (loaded from Secrets Manager)
    app_secret_key: str = ""
    preshared_password: str = ""
    tmdb_api_key: str = ""
    feed_token: str = ""
    plex_webhook_token: str = ""
    plex_server_name: str = ""
    tvdb_api_key: str = ""

    # TMDB
    tmdb_base_url: str = "https://api.themoviedb.org/3"

    class Config:
        env_file = ".env"

    def load_from_secrets_manager(self):
        """Load configuration from AWS Secrets Manager."""
        app_secret_arn = os.environ.get('APP_SECRET_ARN')
        if app_secret_arn:
            print(f"DEBUG: Loading app config from Secrets Manager: {app_secret_arn[:50]}...", flush=True)
            start = time.time()
            app_config = get_secret(app_secret_arn)
            print(f"DEBUG: App config loaded in {time.time() - start:.2f}s", flush=True)
            self.app_secret_key = app_config.get('APP_SECRET_KEY', '')
            self.preshared_password = app_config.get('PRESHARED_PASSWORD', '')
            self.tmdb_api_key = app_config.get('TMDB_API_KEY', '')
            self.feed_token = app_config.get('FEED_TOKEN', '')
            self.plex_webhook_token = app_config.get('PLEX_WEBHOOK_TOKEN', '')
            self.plex_server_name = app_config.get('PLEX_SERVER_NAME', '')
            self.tvdb_api_key = app_config.get('TVDB_API_KEY', '')
        else:
            print("DEBUG: WARNING - APP_SECRET_ARN not set", flush=True)


@lru_cache()
def get_settings() -> Settings:
    settings = Settings()
    # Load from Secrets Manager if running in Lambda
    if os.environ.get('AWS_LAMBDA_FUNCTION_NAME'):
        settings.load_from_secrets_manager()
    return settings
