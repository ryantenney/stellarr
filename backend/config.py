from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    app_secret_key: str = "change-me-in-production"
    preshared_password: str = "changeme"
    tmdb_api_key: str = ""
    tmdb_base_url: str = "https://api.themoviedb.org/3"
    database_path: str = "/app/data/overseer.db"
    feed_token: str = ""  # Optional token for RSS/list endpoint protection

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
