"""
Azure Functions handler for Overseer Lite.

TODO: Implement Azure Functions entry point.

Azure Functions supports HTTP-triggered functions with ASGI apps via
the azure-functions package. FastAPI integrates well with Azure Functions.

Option 1: Azure Functions (HTTP trigger with ASGI)
    Azure Functions v2 for Python supports ASGI apps natively:

    # function_app.py
    import azure.functions as func
    from shared.app import app as fastapi_app, registry
    from providers.azure.config import get_settings
    from providers.azure import database as azure_database
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
            database=azure_database,
            tmdb_client=tmdb_client,
            plex_module=plex_module,
            tvdb_module=tvdb_module,
            webpush_module=webpush_module,
        )

    _init()

    app = func.AsgiFunctionApp(app=fastapi_app, http_auth_level=func.AuthLevel.ANONYMOUS)

Option 2: Azure Container Apps (recommended for FastAPI)
    Azure Container Apps is similar to Cloud Run - runs containers with
    scale-to-zero. Use uvicorn directly:

    # Dockerfile
    FROM python:3.12-slim
    COPY shared/ /app/shared/
    COPY providers/ /app/providers/
    COPY requirements.txt /app/
    RUN pip install -r /app/requirements.txt
    CMD ["uvicorn", "providers.azure.handler:app", "--host", "0.0.0.0", "--port", "8080"]

Terraform resources needed:
    - azurerm_linux_function_app or azurerm_container_app
    - azurerm_cosmosdb_account + azurerm_cosmosdb_sql_database
    - azurerm_key_vault + azurerm_key_vault_secret
    - azurerm_storage_account (for function code + trending cache)
    - azurerm_cdn_frontdoor_profile (CDN)
    - azurerm_dns_zone (DNS)
"""
