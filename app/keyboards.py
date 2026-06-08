from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

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
