from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Japango"
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/japanese_lms"
    neon_auth_base_url: str = ""
    neon_auth_jwks_url: str = ""
    kanji_api_base_url: str = "https://kanjiapi.dev/v1"
    jisho_api_url: str = "https://jisho.org/api/v1/search/words"
    translation_api_url: str = "https://api.mymemory.translated.net/get"
    http_timeout_seconds: float = 15.0
    translation_timeout_seconds: float = 5.0

    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
