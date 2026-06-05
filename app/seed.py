import argparse
import asyncio
import socket
from pathlib import Path

import asyncpg
from pydantic import ValidationError

from app.database import create_pool
from app.repository import apply_schema, seed_questions


async def main() -> None:
    args = parse_args()
    pool = await connect_to_database(args.database_url)
    try:
        await apply_schema(pool)
        await seed_questions(pool, args.path)
    finally:
        await pool.close()
    print(f"Вопросы загружены из {args.path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Загрузить вопросы Telegram Quiz Bot из JSON.")
    parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=Path("app/data/questions.example.json"),
        help="Путь к JSON-файлу с вопросами.",
    )
    parser.add_argument(
        "--database-url",
        help="PostgreSQL DSN. Если не указан, используется DATABASE_URL из окружения или .env.",
    )
    return parser.parse_args()


async def connect_to_database(database_url: str | None) -> asyncpg.Pool:
    try:
        return await create_pool(database_url=database_url, application_name="telegram_quiz_seed")
    except (OSError, asyncpg.PostgresError, ValidationError) as exc:
        raise SystemExit(build_connection_error(exc)) from exc


def build_connection_error(exc: BaseException) -> str:
    hint = (
        "Не удалось подключиться к PostgreSQL для загрузки вопросов.\n"
        f"Причина: {exc}\n\n"
        "Проверьте, что PostgreSQL запущен и DATABASE_URL указывает на доступный хост.\n"
        "Если запускаете команду внутри Docker Compose, используйте:\n"
        "  docker compose up -d postgres\n"
        "  docker compose run --rm bot python -m app.seed app/data/questions.example.json\n\n"
        "Если запускаете команду с хоста, сервисное имя `postgres` не резолвится. "
        "Передайте локальный адрес БД, например:\n"
        "  python -m app.seed app/data/questions.example.json "
        "--database-url postgresql://quiz:quiz_password@127.0.0.1:5432/quiz_bot"
    )
    if isinstance(exc, socket.gaierror):
        return f"{hint}\n\nОшибка DNS означает, что имя хоста из DATABASE_URL сейчас недоступно."
    if isinstance(exc, ValidationError):
        return f"{hint}\n\nНе найден DATABASE_URL. Заполните .env или передайте --database-url."
    return hint


if __name__ == "__main__":
    asyncio.run(main())
