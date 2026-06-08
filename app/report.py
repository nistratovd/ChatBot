import argparse
import asyncio
import csv
import os
import sys
from collections.abc import Sequence
from pathlib import Path

import asyncpg

from app.security import format_plain_value, sanitize_csv_cell

COLUMNS: dict[str, Sequence[str]] = {
    "attempts": (
        "attempt_id",
        "telegram_user_id",
        "username",
        "first_name",
        "last_name",
        "status",
        "started_at",
        "completed_at",
        "answered",
        "total_questions",
        "correct_answers",
        "is_all_correct",
    ),
    "winners": (
        "telegram_user_id",
        "username",
        "first_name",
        "last_name",
        "attempt_id",
        "completed_at",
    ),
    "answers": (
        "answered_at",
        "attempt_id",
        "telegram_user_id",
        "username",
        "first_name",
        "last_name",
        "question_order",
        "question_text",
        "answer_text",
        "is_correct",
    ),
}


QUERIES = {
    "attempts": """
        SELECT
            qa.id AS attempt_id,
            qa.telegram_user_id,
            qa.username,
            qa.first_name,
            qa.last_name,
            CASE WHEN qa.completed_at IS NULL THEN 'in_progress' ELSE 'completed' END AS status,
            qa.started_at,
            qa.completed_at,
            COUNT(ua.id)::int AS answered,
            qa.total_questions,
            qa.correct_answers,
            qa.is_all_correct
        FROM quiz_attempts qa
        LEFT JOIN user_answers ua ON ua.attempt_id = qa.id
        GROUP BY qa.id
        ORDER BY qa.started_at DESC, qa.id DESC
    """,
    "winners": """
        SELECT
            su.telegram_user_id,
            su.username,
            su.first_name,
            su.last_name,
            su.attempt_id,
            su.completed_at
        FROM successful_users su
        ORDER BY su.completed_at ASC, su.telegram_user_id ASC
    """,
    "answers": """
        SELECT
            ua.answered_at,
            ua.attempt_id,
            ua.telegram_user_id,
            qa.username,
            qa.first_name,
            qa.last_name,
            q.sort_order AS question_order,
            q.text AS question_text,
            ao.text AS answer_text,
            ua.is_correct
        FROM user_answers ua
        JOIN quiz_attempts qa ON qa.id = ua.attempt_id
        JOIN questions q ON q.id = ua.question_id
        JOIN answer_options ao ON ao.id = ua.option_id
        ORDER BY ua.answered_at DESC, ua.id DESC
    """,
}


async def main() -> None:
    args = parse_args()
    database_url = get_database_url(args.database_url)
    rows = await fetch_rows(database_url, args.report)
    write_rows(rows, COLUMNS[args.report], args.format)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Показать ответы пользователей и список победителей Telegram Quiz Bot."
    )
    parser.add_argument(
        "report",
        choices=("attempts", "answers", "winners"),
        help=(
            "attempts — все попытки; answers — все ответы; "
            "winners — победители, ответившие правильно на все вопросы"
        ),
    )
    parser.add_argument(
        "--format",
        choices=("table", "csv"),
        default="table",
        help="Формат вывода: table для просмотра в терминале или csv для выгрузки.",
    )
    parser.add_argument(
        "--database-url",
        help="PostgreSQL DSN. Если не указан, используется DATABASE_URL из окружения или .env.",
    )
    return parser.parse_args()


def get_database_url(cli_database_url: str | None) -> str:
    if cli_database_url:
        return cli_database_url

    database_url = os.getenv("DATABASE_URL") or read_env_file().get("DATABASE_URL")
    if not database_url:
        raise SystemExit("Не задан DATABASE_URL. Укажите переменную окружения или --database-url.")
    return database_url


def read_env_file(path: Path = Path(".env")) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        clean_line = line.strip()
        if not clean_line or clean_line.startswith("#") or "=" not in clean_line:
            continue
        key, value = clean_line.split("=", maxsplit=1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


async def fetch_rows(database_url: str, report: str) -> list[asyncpg.Record]:
    conn = await asyncpg.connect(dsn=database_url, command_timeout=10)
    try:
        return await conn.fetch(QUERIES[report])
    finally:
        await conn.close()


def write_rows(rows: Sequence[asyncpg.Record], columns: Sequence[str], output_format: str) -> None:
    if output_format == "csv":
        write_csv(rows, columns)
        return
    write_table(rows, columns)


def write_csv(rows: Sequence[asyncpg.Record], columns: Sequence[str]) -> None:
    writer = csv.DictWriter(sys.stdout, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({column: sanitize_csv_cell(row[column]) for column in columns})


def write_table(rows: Sequence[asyncpg.Record], columns: Sequence[str]) -> None:
    prepared_rows = [tuple(format_plain_value(row[column]) for column in columns) for row in rows]
    widths = [len(column) for column in columns]
    for row in prepared_rows:
        widths = [max(width, len(value)) for width, value in zip(widths, row, strict=True)]

    header = " | ".join(column.ljust(width) for column, width in zip(columns, widths, strict=True))
    separator = "-+-".join("-" * width for width in widths)
    print(header)
    print(separator)
    for row in prepared_rows:
        print(" | ".join(value.ljust(width) for value, width in zip(row, widths, strict=True)))


if __name__ == "__main__":
    asyncio.run(main())
