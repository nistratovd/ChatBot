import asyncpg

from app.config import get_database_settings


async def create_pool(
    *,
    database_url: str | None = None,
    min_size: int | None = None,
    max_size: int | None = None,
    application_name: str = "telegram_quiz_bot",
) -> asyncpg.Pool:
    if database_url is None:
        settings = get_database_settings()
        database_url = settings.database_url
        min_size = min_size or settings.db_pool_min_size
        max_size = max_size or settings.db_pool_max_size
    else:
        min_size = min_size or 5
        max_size = max_size or 30

    return await asyncpg.create_pool(
        dsn=database_url,
        min_size=min_size,
        max_size=max_size,
        command_timeout=10,
        server_settings={"application_name": application_name},
    )
