"""
GCP-specific configuration loading (Secret Manager).

TODO: Implement GCP Secret Manager integration.

GCP Secret Manager uses:
- google-cloud-secret-manager client library
- Service account credentials (automatic in Cloud Functions)
- Secret names like: projects/{project}/secrets/{name}/versions/latest

Example implementation:
    from google.cloud import secretmanager

    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
    response = client.access_secret_version(request={"name": name})
    secret_value = response.payload.data.decode("UTF-8")
"""
import os
from functools import lru_cache

from shared.config import Settings


@lru_cache()
def get_settings() -> Settings:
    """Load settings from environment variables or GCP Secret Manager.

    When running in Cloud Functions, secrets can be mounted as environment
    variables directly via the GCP console or gcloud CLI:
        gcloud functions deploy overseer-lite \\
            --set-secrets 'APP_SECRET_KEY=app-secret-key:latest'

    Alternatively, implement Secret Manager API calls here.
    """
    settings = Settings()

    # GCP Cloud Functions can mount secrets as env vars directly.
    # If using Secret Manager API, load secrets here:
    #
    # if os.environ.get('GCP_PROJECT_ID'):
    #     from google.cloud import secretmanager
    #     client = secretmanager.SecretManagerServiceClient()
    #     project_id = os.environ['GCP_PROJECT_ID']
    #     secret_name = os.environ.get('APP_SECRET_NAME', 'overseer-lite-config')
    #     name = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
    #     response = client.access_secret_version(request={"name": name})
    #     import json
    #     config = json.loads(response.payload.data.decode("UTF-8"))
    #     settings.app_secret_key = config.get('APP_SECRET_KEY', '')
    #     settings.preshared_password = config.get('PRESHARED_PASSWORD', '')
    #     settings.tmdb_api_key = config.get('TMDB_API_KEY', '')
    #     settings.feed_token = config.get('FEED_TOKEN', '')
    #     settings.plex_webhook_token = config.get('PLEX_WEBHOOK_TOKEN', '')
    #     settings.plex_server_name = config.get('PLEX_SERVER_NAME', '')
    #     settings.tvdb_api_key = config.get('TVDB_API_KEY', '')
    #     settings.vapid_private_key = config.get('VAPID_PRIVATE_KEY', '')

    return settings
