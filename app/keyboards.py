from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.models import AnswerOption

RESTART_CALLBACK_DATA = "restart_quiz"


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


def restart_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 Перезапуск",
                    callback_data=RESTART_CALLBACK_DATA,
                )
            ]
        ]
    )
