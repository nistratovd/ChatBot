from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """Настройки подключения к PostgreSQL."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = Field(alias="DATABASE_URL")
    db_pool_min_size: int = Field(default=5, alias="DB_POOL_MIN_SIZE", ge=1)
    db_pool_max_size: int = Field(default=30, alias="DB_POOL_MAX_SIZE", ge=1)


class Settings(DatabaseSettings):
    """Настройки приложения, читаемые из переменных окружения."""

    bot_token: SecretStr = Field(alias="BOT_TOKEN")
    webhook_secret: SecretStr = Field(default=SecretStr("change-me"), alias="WEBHOOK_SECRET")


@lru_cache
def get_database_settings() -> DatabaseSettings:
    return DatabaseSettings()


@lru_cache
def get_settings() -> Settings:
    return Settings()
