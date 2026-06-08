from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from app.models import AnswerOption


def question_keyboard(options: list[AnswerOption]) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(
                text=option.text,
                callback_data=f"answer:{option.question_id}:{option.id}",
            )
        ]
        for option in options
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


RESTART_BUTTON_TEXT = "🔄 Перезапуск"


def restart_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=RESTART_BUTTON_TEXT)]],
        resize_keyboard=True,
        is_persistent=True,
    )


def remove_restart_keyboard() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()
