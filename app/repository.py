import asyncio
import json
from collections.abc import Iterable
from pathlib import Path

import asyncpg
from aiogram.types import User

from app.models import AnswerOption, Attempt, Question


class QuizRepository:
    """Быстрый асинхронный слой доступа к PostgreSQL."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def has_completed_quiz(self, user_id: int) -> bool:
        return await self.pool.fetchval(
            "SELECT EXISTS(SELECT 1 FROM quiz_attempts WHERE telegram_user_id=$1 AND completed_at IS NOT NULL)",
            user_id,
        )

    async def get_or_create_active_attempt(self, user: User) -> Attempt | None:
        completed = await self.has_completed_quiz(user.id)
        if completed:
            return None

        async with self.pool.acquire() as conn, conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock($1)", user.id)
            row = await conn.fetchrow(
                """
                SELECT id, telegram_user_id, completed_at, total_questions, correct_answers, is_all_correct
                FROM quiz_attempts
                WHERE telegram_user_id=$1 AND completed_at IS NULL
                ORDER BY started_at DESC
                LIMIT 1
                """,
                user.id,
            )
            if row is None:
                total_questions = await _count_active_questions(conn)
                row = await conn.fetchrow(
                    """
                    INSERT INTO quiz_attempts (
                        telegram_user_id, username, first_name, last_name, total_questions
                    )
                    VALUES ($1, $2, $3, $4, $5)
                    RETURNING id, telegram_user_id, completed_at, total_questions, correct_answers, is_all_correct
                    """,
                    user.id,
                    user.username,
                    user.first_name,
                    user.last_name,
                    total_questions,
                )
            else:
                row = await _refresh_unanswered_attempt_total(conn, row)
            return _attempt_from_row(row)

    async def get_next_question(self, attempt_id: int) -> Question | None:
        row = await self.pool.fetchrow(
            """
            SELECT q.id, q.sort_order, q.text, q.photo_url, q.photo_file_id
            FROM questions q
            WHERE q.is_active = TRUE
              AND NOT EXISTS (
                  SELECT 1 FROM user_answers ua
                  WHERE ua.attempt_id=$1 AND ua.question_id=q.id
              )
            ORDER BY q.sort_order ASC
            LIMIT 1
            """,
            attempt_id,
        )
        return _question_from_row(row) if row else None

    async def get_options(self, question_id: int) -> list[AnswerOption]:
        rows = await self.pool.fetch(
            """
            SELECT id, question_id, text, is_correct, sort_order
            FROM answer_options
            WHERE question_id=$1
            ORDER BY sort_order ASC, id ASC
            """,
            question_id,
        )
        return [_option_from_row(row) for row in rows]

    async def save_answer(
        self,
        *,
        attempt_id: int,
        user: User,
        question_id: int,
        option_id: int,
    ) -> bool | None:
        """Сохраняет ответ. Возвращает correctness или None, если ответ уже есть/некорректен."""

        async with self.pool.acquire() as conn, conn.transaction():
            active_attempt = await conn.fetchval(
                """
                SELECT EXISTS(
                    SELECT 1 FROM quiz_attempts
                    WHERE id=$1 AND telegram_user_id=$2 AND completed_at IS NULL
                )
                """,
                attempt_id,
                user.id,
            )
            if not active_attempt:
                return None

            next_question_id = await conn.fetchval(
                """
                SELECT q.id
                FROM questions q
                WHERE q.is_active = TRUE
                  AND NOT EXISTS (
                      SELECT 1 FROM user_answers ua
                      WHERE ua.attempt_id=$1 AND ua.question_id=q.id
                  )
                ORDER BY q.sort_order ASC
                LIMIT 1
                """,
                attempt_id,
            )
            if next_question_id != question_id:
                return None

            option = await conn.fetchrow(
                """
                SELECT id, is_correct FROM answer_options
                WHERE id=$1 AND question_id=$2
                """,
                option_id,
                question_id,
            )
            if option is None:
                return None

            inserted = await conn.fetchrow(
                """
                INSERT INTO user_answers (
                    attempt_id, telegram_user_id, question_id, option_id, is_correct
                )
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (attempt_id, question_id) DO NOTHING
                RETURNING is_correct
                """,
                attempt_id,
                user.id,
                question_id,
                option_id,
                option["is_correct"],
            )
            if inserted is None:
                return None

            if inserted["is_correct"]:
                await conn.execute(
                    "UPDATE quiz_attempts SET correct_answers = correct_answers + 1 WHERE id=$1",
                    attempt_id,
                )
            return bool(inserted["is_correct"])

    async def complete_attempt_if_finished(self, attempt_id: int, user: User) -> bool:
        async with self.pool.acquire() as conn, conn.transaction():
            stats = await conn.fetchrow(
                """
                SELECT
                    qa.total_questions,
                    qa.correct_answers,
                    COUNT(ua.id)::int AS answered_count
                FROM quiz_attempts qa
                LEFT JOIN user_answers ua ON ua.attempt_id = qa.id
                WHERE qa.id=$1 AND qa.telegram_user_id=$2 AND qa.completed_at IS NULL
                GROUP BY qa.id
                """,
                attempt_id,
                user.id,
            )
            if stats is None or stats["answered_count"] < stats["total_questions"]:
                return False

            is_all_correct = stats["total_questions"] > 0 and (
                stats["correct_answers"] == stats["total_questions"]
            )
            await conn.execute(
                """
                UPDATE quiz_attempts
                SET completed_at=NOW(), is_all_correct=$2
                WHERE id=$1 AND completed_at IS NULL
                """,
                attempt_id,
                is_all_correct,
            )
            if is_all_correct:
                await conn.execute(
                    """
                    INSERT INTO successful_users (
                        telegram_user_id, attempt_id, username, first_name, last_name, completed_at
                    )
                    VALUES ($1, $2, $3, $4, $5, NOW())
                    ON CONFLICT (telegram_user_id) DO NOTHING
                    """,
                    user.id,
                    attempt_id,
                    user.username,
                    user.first_name,
                    user.last_name,
                )
            return True


async def _count_active_questions(conn: asyncpg.Connection) -> int:
    return await conn.fetchval("SELECT COUNT(*) FROM questions WHERE is_active = TRUE")


async def _refresh_unanswered_attempt_total(
    conn: asyncpg.Connection,
    row: asyncpg.Record,
) -> asyncpg.Record:
    answered_count = await conn.fetchval(
        "SELECT COUNT(*) FROM user_answers WHERE attempt_id=$1",
        row["id"],
    )
    if answered_count:
        return row

    total_questions = await _count_active_questions(conn)
    if total_questions == row["total_questions"]:
        return row

    refreshed = await conn.fetchrow(
        """
        UPDATE quiz_attempts
        SET total_questions=$2
        WHERE id=$1 AND completed_at IS NULL
        RETURNING id, telegram_user_id, completed_at, total_questions, correct_answers, is_all_correct
        """,
        row["id"],
        total_questions,
    )
    return refreshed or row


async def apply_schema(pool: asyncpg.Pool, sql_path: Path = Path("app/sql/001_init.sql")) -> None:
    schema_sql = await asyncio.to_thread(sql_path.read_text, encoding="utf-8")
    async with pool.acquire() as conn:
        await conn.execute(schema_sql)


async def seed_questions(pool: asyncpg.Pool, json_path: Path) -> None:
    questions_json = await asyncio.to_thread(json_path.read_text, encoding="utf-8")
    questions = json.loads(questions_json)
    async with pool.acquire() as conn, conn.transaction():
        for question in questions:
            question_id = await conn.fetchval(
                """
                INSERT INTO questions (sort_order, text, photo_url, photo_file_id)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (sort_order) DO UPDATE
                SET text=EXCLUDED.text,
                    photo_url=EXCLUDED.photo_url,
                    photo_file_id=EXCLUDED.photo_file_id,
                    is_active=TRUE
                RETURNING id
                """,
                question["sort_order"],
                question["text"],
                question.get("photo_url"),
                question.get("photo_file_id"),
            )
            await conn.execute("DELETE FROM answer_options WHERE question_id=$1", question_id)
            await _insert_options(conn, question_id, question["options"])

        await _refresh_empty_active_attempts_total(conn)


async def _refresh_empty_active_attempts_total(conn: asyncpg.Connection) -> None:
    total_questions = await _count_active_questions(conn)
    await conn.execute(
        """
        UPDATE quiz_attempts
        SET total_questions=$1
        WHERE completed_at IS NULL
          AND NOT EXISTS (
              SELECT 1 FROM user_answers ua
              WHERE ua.attempt_id=quiz_attempts.id
          )
        """,
        total_questions,
    )


async def _insert_options(
    conn: asyncpg.Connection,
    question_id: int,
    options: Iterable[dict[str, object]],
) -> None:
    await conn.executemany(
        """
        INSERT INTO answer_options (question_id, text, is_correct, sort_order)
        VALUES ($1, $2, $3, $4)
        """,
        [
            (question_id, option["text"], option["is_correct"], option.get("sort_order", index))
            for index, option in enumerate(options, start=1)
        ],
    )


def _question_from_row(row: asyncpg.Record) -> Question:
    return Question(
        id=row["id"],
        sort_order=row["sort_order"],
        text=row["text"],
        photo_url=row["photo_url"],
        photo_file_id=row["photo_file_id"],
    )


def _option_from_row(row: asyncpg.Record) -> AnswerOption:
    return AnswerOption(
        id=row["id"],
        question_id=row["question_id"],
        text=row["text"],
        is_correct=row["is_correct"],
        sort_order=row["sort_order"],
    )


def _attempt_from_row(row: asyncpg.Record) -> Attempt:
    return Attempt(
        id=row["id"],
        telegram_user_id=row["telegram_user_id"],
        completed_at=row["completed_at"],
        total_questions=row["total_questions"],
        correct_answers=row["correct_answers"],
        is_all_correct=row["is_all_correct"],
    )
