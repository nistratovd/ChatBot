import argparse
import asyncio
import socket

import asyncpg
from pydantic import ValidationError

from app.database import create_pool
from app.repository import apply_schema, reset_database


async def main() -> None:
    args = parse_args()
    if not args.yes:
        raise SystemExit(
            "Команда очистки удаляет данные без восстановления. "
            "Добавьте --yes, чтобы подтвердить запуск."
        )

    pool = await connect_to_database(args.database_url)
    try:
        await apply_schema(pool)
        await reset_database(pool, include_questions=args.with_questions)
    finally:
        await pool.close()

    if args.with_questions:
        print("База квиза полностью очищена: вопросы, варианты, попытки и ответы удалены.")
    else:
        print("Тестовые данные очищены: попытки, ответы и победители удалены; вопросы сохранены.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Сервисные команды Telegram Quiz Bot для тестирования."
    )
    subparsers = parser.add_subparsers(dest="command")

    reset_parser = subparsers.add_parser(
        "reset-db",
        description="Очистить данные квиза в PostgreSQL перед тестовым запуском.",
        help="очистить попытки, ответы и победителей; вопросы оставить по умолчанию",
    )
    reset_parser.add_argument(
        "--with-questions",
        action="store_true",
        help="дополнительно удалить вопросы и варианты ответов.",
    )
    reset_parser.add_argument(
        "--database-url",
        help="PostgreSQL DSN. Если не указан, используется DATABASE_URL из окружения или .env.",
    )
    reset_parser.add_argument(
        "--yes",
        action="store_true",
        help="обязательное подтверждение необратимой очистки.",
    )

    args = parser.parse_args()
    if args.command != "reset-db":
        parser.print_help()
        raise SystemExit(2)
    return args


async def connect_to_database(database_url: str | None) -> asyncpg.Pool:
    try:
        return await create_pool(database_url=database_url, application_name="telegram_quiz_maintenance")
    except (OSError, asyncpg.PostgresError, ValidationError) as exc:
        raise SystemExit(build_connection_error(exc)) from exc


def build_connection_error(exc: BaseException) -> str:
    hint = (
        "Не удалось подключиться к PostgreSQL для сервисной очистки.\n"
        f"Причина: {exc}\n\n"
        "Проверьте, что PostgreSQL запущен и DATABASE_URL указывает на доступный хост.\n"
        "Если запускаете команду внутри Docker Compose, используйте:\n"
        "  docker compose up -d postgres\n"
        "  docker compose run --rm bot python -m app.maintenance reset-db --yes\n\n"
        "Если запускаете команду с хоста, сервисное имя `postgres` не резолвится. "
        "Передайте локальный адрес БД, например:\n"
        "  python -m app.maintenance reset-db --yes "
        "--database-url postgresql://quiz:quiz_password@127.0.0.1:5432/quiz_bot"
    )
    if isinstance(exc, socket.gaierror):
        return f"{hint}\n\nОшибка DNS означает, что имя хоста из DATABASE_URL сейчас недоступно."
    if isinstance(exc, ValidationError):
        return f"{hint}\n\nНе найден DATABASE_URL. Заполните .env или передайте --database-url."
    return hint


if __name__ == "__main__":
    asyncio.run(main())
