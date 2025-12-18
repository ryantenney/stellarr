import os
import json
import boto3
import time
from functools import lru_cache
from pydantic_settings import BaseSettings

print("DEBUG: config.py loading...", flush=True)


def get_secret(secret_arn: str) -> dict:
    """Retrieve a secret from AWS Secrets Manager."""
    client = boto3.client('secretsmanager', region_name=os.environ.get('AWS_REGION_NAME', 'us-east-1'))
    response = client.get_secret_value(SecretId=secret_arn)
    return json.loads(response['SecretString'])


class Settings(BaseSettings):
    # App settings (loaded from Secrets Manager)
    app_secret_key: str = ""
    preshared_password: str = ""
    tmdb_api_key: str = ""
    feed_token: str = ""

    # Database settings (loaded from Secrets Manager)
    db_host: str = ""
    db_port: int = 5432
    db_name: str = "overseer"
    db_user: str = ""
    db_password: str = ""

    # TMDB
    tmdb_base_url: str = "https://api.themoviedb.org/3"

    class Config:
        env_file = ".env"

    def load_from_secrets_manager(self):
        """Load configuration from AWS Secrets Manager."""
        # Load app config
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
        else:
            print("DEBUG: WARNING - APP_SECRET_ARN not set", flush=True)

        # Load DB config
        db_secret_arn = os.environ.get('DB_SECRET_ARN')
        if db_secret_arn:
            print(f"DEBUG: Loading DB config from Secrets Manager: {db_secret_arn[:50]}...", flush=True)
            start = time.time()
            db_config = get_secret(db_secret_arn)
            print(f"DEBUG: DB config loaded in {time.time() - start:.2f}s", flush=True)
            self.db_host = db_config.get('host', '')
            self.db_port = int(db_config.get('port', 5432))
            self.db_name = db_config.get('database', 'overseer')
            self.db_user = db_config.get('username', '')
            self.db_password = db_config.get('password', '')
            print(f"DEBUG: DB config: host={self.db_host}, port={self.db_port}, db={self.db_name}, user={self.db_user}", flush=True)
        else:
            print("DEBUG: WARNING - DB_SECRET_ARN not set", flush=True)

    @property
    def database_url(self) -> str:
        """Get PostgreSQL connection URL."""
        return f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"


@lru_cache()
def get_settings() -> Settings:
    settings = Settings()
    # Load from Secrets Manager if running in Lambda
    if os.environ.get('AWS_LAMBDA_FUNCTION_NAME'):
        settings.load_from_secrets_manager()
    return settings
