"""
AWS Lambda handler for Overseer Lite.

This is the entry point for AWS Lambda. It configures the shared app
with AWS-specific providers (DynamoDB, Secrets Manager) and wraps
the FastAPI app with Mangum for Lambda compatibility.
"""
from mangum import Mangum

print("DEBUG: Starting providers.aws.handler module load...", flush=True)

# =============================================================================
# Lazy imports for cold start optimization
# =============================================================================

_initialized = False


def _ensure_initialized():
    """Lazy-initialize all providers on first request."""
    global _initialized
    if _initialized:
        return
    _initialized = True

    print("DEBUG: Initializing AWS providers...", flush=True)

    from shared.app import registry
    from providers.aws.config import get_settings
    from providers.aws import database as aws_database
    from shared.tmdb import TMDBClient
    import shared.plex as plex_module
    import shared.tvdb as tvdb_module
    import shared.webpush as webpush_module

    # Load settings
    settings = get_settings()

    # Configure TVDB with API key
    tvdb_module.configure(settings.tvdb_api_key)

    # Create TMDB client
    tmdb_client = TMDBClient(
        api_key=settings.tmdb_api_key,
        base_url=settings.tmdb_base_url
    )

    # Register all providers
    registry.configure(
        settings_fn=get_settings,
        database=aws_database,
        tmdb_client=tmdb_client,
        plex_module=plex_module,
        tvdb_module=tvdb_module,
        webpush_module=webpush_module,
    )

    print("DEBUG: AWS providers initialized", flush=True)


# Import the shared app
from shared.app import app


# Add initialization middleware that runs on first request
@app.middleware("http")
async def ensure_initialized_middleware(request, call_next):
    _ensure_initialized()
    return await call_next(request)


print("DEBUG: Module load complete, handler ready", flush=True)

# Lambda handler - lifespan="off" since we handle init lazily
handler = Mangum(app, lifespan="off")
