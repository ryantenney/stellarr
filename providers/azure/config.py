"""
Azure-specific configuration loading (Key Vault).

TODO: Implement Azure Key Vault integration.

Azure Key Vault uses:
- azure-keyvault-secrets + azure-identity client libraries
- Managed Identity (automatic in Azure Functions)
- Secret names like: https://{vault-name}.vault.azure.net/secrets/{name}

Example implementation:
    from azure.identity import DefaultAzureCredential
    from azure.keyvault.secrets import SecretClient

    credential = DefaultAzureCredential()
    vault_url = f"https://{vault_name}.vault.azure.net"
    client = SecretClient(vault_url=vault_url, credential=credential)

    # Get individual secrets
    secret = client.get_secret("app-secret-key")
    value = secret.value

    # Or store all config as a single JSON secret
    config_secret = client.get_secret("overseer-lite-config")
    config = json.loads(config_secret.value)
"""
import os
from functools import lru_cache

from shared.config import Settings


@lru_cache()
def get_settings() -> Settings:
    """Load settings from environment variables or Azure Key Vault.

    Azure Functions supports Key Vault references in app settings:
        @Microsoft.KeyVault(SecretUri=https://myvault.vault.azure.net/secrets/mysecret/)

    This means secrets can be loaded as regular environment variables
    without any code changes. Alternatively, use the Key Vault SDK directly.
    """
    settings = Settings()

    # Azure Functions can reference Key Vault secrets directly in app settings.
    # If using Key Vault SDK, load secrets here:
    #
    # vault_name = os.environ.get('AZURE_KEY_VAULT_NAME')
    # if vault_name:
    #     from azure.identity import DefaultAzureCredential
    #     from azure.keyvault.secrets import SecretClient
    #     credential = DefaultAzureCredential()
    #     vault_url = f"https://{vault_name}.vault.azure.net"
    #     client = SecretClient(vault_url=vault_url, credential=credential)
    #
    #     # Load all config from a single JSON secret
    #     config_secret = client.get_secret("overseer-lite-config")
    #     import json
    #     config = json.loads(config_secret.value)
    #     settings.app_secret_key = config.get('APP_SECRET_KEY', '')
    #     settings.preshared_password = config.get('PRESHARED_PASSWORD', '')
    #     settings.tmdb_api_key = config.get('TMDB_API_KEY', '')
    #     settings.feed_token = config.get('FEED_TOKEN', '')
    #     settings.plex_webhook_token = config.get('PLEX_WEBHOOK_TOKEN', '')
    #     settings.plex_server_name = config.get('PLEX_SERVER_NAME', '')
    #     settings.tvdb_api_key = config.get('TVDB_API_KEY', '')
    #     settings.vapid_private_key = config.get('VAPID_PRIVATE_KEY', '')

    return settings
