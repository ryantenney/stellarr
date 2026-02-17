"""
AWS-specific configuration loading (Secrets Manager).
"""
import os
import time
from functools import lru_cache

from shared.config import Settings
from providers.aws.aws_sigv4 import get_secret

print("DEBUG: providers.aws.config loading (boto3-free)...", flush=True)


@lru_cache()
def get_settings() -> Settings:
    """Load settings, optionally from AWS Secrets Manager."""
    settings = Settings()
    # Load from Secrets Manager if running in Lambda
    if os.environ.get('AWS_LAMBDA_FUNCTION_NAME'):
        app_secret_arn = os.environ.get('APP_SECRET_ARN')
        if app_secret_arn:
            print(f"DEBUG: Loading app config from Secrets Manager: {app_secret_arn[:50]}...", flush=True)
            start = time.time()
            app_config = get_secret(app_secret_arn)
            print(f"DEBUG: App config loaded in {time.time() - start:.2f}s", flush=True)
            settings.app_secret_key = app_config.get('APP_SECRET_KEY', '')
            settings.preshared_password = app_config.get('PRESHARED_PASSWORD', '')
            settings.tmdb_api_key = app_config.get('TMDB_API_KEY', '')
            settings.feed_token = app_config.get('FEED_TOKEN', '')
            settings.plex_webhook_token = app_config.get('PLEX_WEBHOOK_TOKEN', '')
            settings.plex_server_name = app_config.get('PLEX_SERVER_NAME', '')
            settings.tvdb_api_key = app_config.get('TVDB_API_KEY', '')
            settings.vapid_private_key = app_config.get('VAPID_PRIVATE_KEY', '')
        else:
            print("DEBUG: WARNING - APP_SECRET_ARN not set", flush=True)
    return settings
