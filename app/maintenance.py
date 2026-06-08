import argparse
import asyncio
import socket

import asyncpg
from pydantic import ValidationError

from app.database import create_pool
from app.repository import QuizRepository, apply_schema, reset_database
from app.security import mask_sensitive_text


async def main() -> None:
    args = parse_args()
    if args.command == "reset-db" and not args.yes:
        raise SystemExit(
            "Команда очистки удаляет данные без восстановления. "
            "Добавьте --yes, чтобы подтвердить запуск."
        )
    if args.command == "allow-users" and args.action == "clear" and not args.yes:
        raise SystemExit(
            "Команда очистки списка доступа удаляет всех разрешённых пользователей. "
            "Добавьте --yes, чтобы подтвердить запуск."
        )

    pool = await connect_to_database(args.database_url)
    try:
        await apply_schema(pool)
        if args.command == "reset-db":
            await reset_database(pool, include_questions=args.with_questions)
            print_reset_result(include_questions=args.with_questions)
        elif args.command == "allow-users":
            await handle_allow_users(args, QuizRepository(pool))
    finally:
        await pool.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Сервисные команды Telegram Quiz Bot для тестирования."
    )
    parser.add_argument(
        "--database-url",
        help="PostgreSQL DSN. Если не указан, используется DATABASE_URL из окружения или .env.",
    )
    subparsers = parser.add_subparsers(dest="command")

    reset_parser = subparsers.add_parser(
        "reset-db",
        description="Очистить данные квиза в PostgreSQL перед тестовым запуском.",
        help="очистить попытки, ответы и победителей; вопросы оставить по умолчанию",
    )
    reset_parser.add_argument(
        "--database-url",
        default=argparse.SUPPRESS,
        help="PostgreSQL DSN. Совместимость со старым форматом команды.",
    )
    reset_parser.add_argument(
        "--with-questions",
        action="store_true",
        help="дополнительно удалить вопросы и варианты ответов.",
    )
    reset_parser.add_argument(
        "--yes",
        action="store_true",
        help="обязательное подтверждение необратимой очистки.",
    )

    allow_parser = subparsers.add_parser(
        "allow-users",
        description="Редактировать список пользователей закрытого тестирования.",
        help="добавить, удалить или посмотреть пользователей с доступом к опросу",
    )
    allow_parser.add_argument(
        "--database-url",
        default=argparse.SUPPRESS,
        help="PostgreSQL DSN. Можно передать как до, так и после allow-users.",
    )
    allow_subparsers = allow_parser.add_subparsers(dest="action")

    allow_subparsers.add_parser("list", help="показать пользователей с доступом")

    add_parser = allow_subparsers.add_parser("add", help="добавить или обновить пользователя")
    add_parser.add_argument("telegram_user_id", type=int, help="Telegram user ID пользователя")
    add_parser.add_argument("--username", help="Telegram username без @")
    add_parser.add_argument("--first-name", help="имя пользователя")
    add_parser.add_argument("--last-name", help="фамилия пользователя")
    add_parser.add_argument("--note", help="внутренний комментарий, например группа тестирования")

    remove_parser = allow_subparsers.add_parser("remove", help="удалить пользователя из списка")
    remove_parser.add_argument("telegram_user_id", type=int, help="Telegram user ID пользователя")

    clear_parser = allow_subparsers.add_parser("clear", help="очистить список и снова открыть опрос для всех")
    clear_parser.add_argument(
        "--yes",
        action="store_true",
        help="обязательное подтверждение очистки списка доступа.",
    )

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        raise SystemExit(2)
    if args.command == "allow-users" and args.action is None:
        allow_parser.print_help()
        raise SystemExit(2)
    return args


async def handle_allow_users(args: argparse.Namespace, repo: QuizRepository) -> None:
    if args.action == "list":
        users = await repo.list_allowed_users()
        if not users:
            print("Список доступа пуст: опрос открыт для всех пользователей.")
            return
        for user in users:
            username = f"@{user.username}" if user.username else "-"
            full_name = " ".join(
                part for part in (user.first_name, user.last_name) if part
            ) or "-"
            note = user.note or "-"
            print(f"{user.telegram_user_id}\t{username}\t{full_name}\t{note}")
        return

    if args.action == "add":
        user = await repo.add_allowed_user(
            user_id=args.telegram_user_id,
            username=normalize_username(args.username),
            first_name=args.first_name,
            last_name=args.last_name,
            note=args.note,
        )
        username = f"@{user.username}" if user.username else "без username"
        print(f"Пользователь {user.telegram_user_id} ({username}) добавлен в список доступа.")
        return

    if args.action == "remove":
        removed = await repo.remove_allowed_user(args.telegram_user_id)
        if removed:
            print(f"Пользователь {args.telegram_user_id} удалён из списка доступа.")
        else:
            print(f"Пользователь {args.telegram_user_id} не найден в списке доступа.")
        return

    if args.action == "clear":
        deleted_count = await repo.clear_allowed_users()
        print(f"Список доступа очищен, удалено записей: {deleted_count}.")
        return

    raise SystemExit(f"Неизвестное действие allow-users: {args.action}")


def normalize_username(username: str | None) -> str | None:
    if username is None:
        return None
    return username.removeprefix("@")


def print_reset_result(*, include_questions: bool) -> None:
    if include_questions:
        print("База квиза полностью очищена: вопросы, варианты, попытки и ответы удалены.")
    else:
        print("Тестовые данные очищены: попытки, ответы и победители удалены; вопросы сохранены.")


async def connect_to_database(database_url: str | None) -> asyncpg.Pool:
    try:
        return await create_pool(database_url=database_url, application_name="telegram_quiz_maintenance")
    except (OSError, asyncpg.PostgresError, ValidationError) as exc:
        raise SystemExit(build_connection_error(exc)) from exc


def build_connection_error(exc: BaseException) -> str:
    hint = (
        "Не удалось подключиться к PostgreSQL для сервисной очистки.\n"
        f"Причина: {mask_sensitive_text(str(exc))}\n\n"
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
