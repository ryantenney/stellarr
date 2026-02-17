"""
GCP Cloud Functions handler for Overseer Lite.

TODO: Implement Cloud Functions entry point.

Cloud Functions supports HTTP-triggered functions. The FastAPI app
can be served using a functions-framework wrapper or by using
Cloud Run (which supports containers directly).

Option 1: Cloud Functions (HTTP trigger)
    The functions-framework can serve FastAPI/ASGI apps:

    import functions_framework
    from shared.app import app, registry
    from providers.gcp.config import get_settings
    from providers.gcp import database as gcp_database
    from shared.tmdb import TMDBClient
    import shared.plex as plex_module
    import shared.tvdb as tvdb_module
    import shared.webpush as webpush_module

    def _init():
        settings = get_settings()
        tvdb_module.configure(settings.tvdb_api_key)
        tmdb_client = TMDBClient(api_key=settings.tmdb_api_key, base_url=settings.tmdb_base_url)
        registry.configure(
            settings_fn=get_settings,
            database=gcp_database,
            tmdb_client=tmdb_client,
            plex_module=plex_module,
            tvdb_module=tvdb_module,
            webpush_module=webpush_module,
        )

    _init()

    @functions_framework.http
    def handler(request):
        # Use an ASGI-to-WSGI adapter or Cloud Run instead
        pass

Option 2: Cloud Run (recommended for FastAPI)
    Cloud Run runs containers, so you can use uvicorn directly:

    # Dockerfile
    FROM python:3.12-slim
    COPY shared/ /app/shared/
    COPY providers/ /app/providers/
    COPY requirements.txt /app/
    RUN pip install -r /app/requirements.txt
    CMD ["uvicorn", "providers.gcp.handler:app", "--host", "0.0.0.0", "--port", "8080"]

    This is the recommended approach for GCP since Cloud Run:
    - Supports ASGI natively (no adapter needed)
    - Scales to zero like Cloud Functions
    - Has better cold start performance for Python
    - Supports websockets and long-running requests

Terraform resources needed:
    - google_cloud_run_v2_service
    - google_firestore_database
    - google_secret_manager_secret
    - google_cloud_scheduler_job (for cache warmer)
    - google_storage_bucket (for trending cache)
"""
