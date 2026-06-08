from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True, frozen=True)
class Question:
    id: int
    sort_order: int
    text: str
    photo_url: str | None
    photo_file_id: str | None
    display_number: int | None


@dataclass(slots=True, frozen=True)
class AnswerOption:
    id: int
    question_id: int
    text: str
    is_correct: bool
    sort_order: int


@dataclass(slots=True, frozen=True)
class Attempt:
    id: int
    telegram_user_id: int
    completed_at: datetime | None
    total_questions: int
    correct_answers: int
    is_all_correct: bool


@dataclass(slots=True, frozen=True)
class AllowedUser:
    telegram_user_id: int
    username: str | None
    first_name: str | None
    last_name: str | None
    note: str | None
    created_at: datetime
    updated_at: datetime
